from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..errors import GENERAL_FAILURE, GOVERNANCE_ERROR, OK
from ..events import emit_event
from ..utils import now_iso, read_text, run, write_json


def _load_json(path: Path) -> dict:
    return json.loads(read_text(path))


def _finalize(paths, task_id: str, status: str, steps: list[dict], artifact_checks: list[dict], governance: list[dict], evidence: list[dict], reason_code: int) -> int:
    report = {
        "generated_at": now_iso(),
        "task_id": task_id,
        "status": status,
        "steps": steps,
        "artifact_checks": artifact_checks,
        "governance_checks": governance,
        "evidence_checks": evidence,
        "final_recommendation": "Ready for controlled execution" if status == "PASS" else "Not ready; fix findings first",
        "reason_code": reason_code,
    }
    out_path = paths.runs_dir / f"{task_id}.doctor_report.json"
    write_json(out_path, report)
    print(f"STATUS={status}")
    print(f"WROTE={out_path}")
    emit_event(
        paths,
        event_type="command_completed",
        command="doctor",
        task_id=task_id,
        severity="FAIL" if reason_code else "INFO",
        reason_code=str(reason_code),
        message=f"doctor completed with status={status}",
        data={"step_count": len(steps)},
    )
    return reason_code


def cmd_doctor(args: Namespace) -> int:
    out_root = Path(args.out_root) if getattr(args, "out_root", None) else None
    paths = resolve_paths(Path(args.repo_root), out_root=out_root)
    ensure_out_dirs(paths)
    task_id = args.task_id
    profile = str(getattr(args, "profile", "standalone"))
    steps: list[dict] = []
    artifact_checks: list[dict] = []
    governance_checks: list[dict] = []
    evidence_checks: list[dict] = []

    emit_event(paths, event_type="command_started", command="doctor", task_id=task_id, message="doctor started", data={"profile": profile})

    out_args = ["--out-root", str(paths.out_root)] if out_root is not None else []
    pipeline = [
        ("ingest", [sys.executable, "-m", "specforge", "--repo-root", str(paths.repo_root), *out_args, "ingest"]),
        ("normalize", [sys.executable, "-m", "specforge", "--repo-root", str(paths.repo_root), *out_args, "normalize"]),
        ("lint_profile", [sys.executable, "-m", "specforge", "--repo-root", str(paths.repo_root), *out_args, "lint", "--profile", profile]),
        ("plan", [sys.executable, "-m", "specforge", "--repo-root", str(paths.repo_root), *out_args, "plan", "--task-id", task_id]),
        ("prompt", [sys.executable, "-m", "specforge", "--repo-root", str(paths.repo_root), *out_args, "prompt", "--task-id", task_id]),
        (
            "reconcile",
            [sys.executable, "-m", "specforge", "--repo-root", str(paths.repo_root), *out_args, "reconcile", "--task-id", task_id]
            + (["--sync"] if args.sync else []),
        ),
    ]

    if args.run_mode:
        pipeline.append(
            (
                f"run_{args.run_mode}",
                [
                    sys.executable,
                    "-m",
                    "specforge",
                    "--repo-root",
                    str(paths.repo_root),
                    *out_args,
                    "run",
                    "--task-id",
                    task_id,
                    "--mode",
                    args.run_mode,
                    "--profile",
                    profile,
                ],
            )
        )

    for step_name, cmd in pipeline:
        code, out = run(cmd, cwd=paths.app_root)
        steps.append({"step": step_name, "command": " ".join(cmd), "exit_code": code, "output": out})
        if code != 0:
            return _finalize(paths, task_id, "FAIL", steps, artifact_checks, governance_checks, evidence_checks, int(code or GENERAL_FAILURE))

    expected = [
        paths.inventory_dir / "repo_inventory.json",
        paths.contracts_dir / "route_contracts.json",
        paths.contracts_dir / "api_contracts.json",
        paths.contracts_dir / "lint_report.json",
        paths.plans_dir / f"{task_id}.task_packets.json",
        paths.prompts_dir / f"{task_id}.MASTER_PROMPT.md",
        paths.reconcile_dir / f"{task_id}.reconcile_report.json",
    ]
    status = "PASS"
    reason_code = OK
    for p in expected:
        exists = p.exists()
        artifact_checks.append({"artifact": str(p), "exists": exists})
        if not exists:
            status = "FAIL"
            reason_code = GOVERNANCE_ERROR

    lint_report = _load_json(paths.contracts_dir / "lint_report.json")
    lint_ok = lint_report.get("status") in {"PASS", "WARN"} if profile in {"standalone", "core"} else lint_report.get("status") == "PASS"
    governance_checks.append({"name": "lint_profile_pass", "pass": lint_ok, "value": lint_report.get("status"), "profile": profile})
    if not lint_ok:
        status = "FAIL"
        reason_code = int(lint_report.get("reason_code", GOVERNANCE_ERROR))

    rec = _load_json(paths.reconcile_dir / f"{task_id}.reconcile_report.json")
    cp_ok = rec.get("checkpoint_cp0_status") == "approved"
    ev_ok = bool(rec.get("evidence", {}).get("sufficient"))
    evidence_checks.append({"name": "checkpoint_cp0_approved", "pass": cp_ok})
    evidence_checks.append({"name": "evidence_sufficient", "pass": ev_ok})
    if profile == "governed" and (not cp_ok or not ev_ok):
        status = "FAIL"
        reason_code = GOVERNANCE_ERROR

    return _finalize(paths, task_id, status, steps, artifact_checks, governance_checks, evidence_checks, reason_code)
