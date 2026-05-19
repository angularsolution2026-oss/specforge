from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..errors import EXECUTOR_ERROR, OK, PREFLIGHT_BLOCKED
from ..events import emit_event
from ..utils import now_iso, read_text, run, write_json
from ..validators import validate_runtime_preflight


def _load_json(path: Path) -> dict:
    return json.loads(read_text(path))


def checkpoint_is_approved(checkpoint_required: str, checkpoint_status: object) -> bool:
    if not checkpoint_required:
        return True
    if checkpoint_status is None:
        return False
    if not isinstance(checkpoint_status, str):
        return False
    return checkpoint_status.strip() == "approved"


def evaluate_runtime_preflight(
    packets: list[dict],
    lint_status: str,
    denied_patterns: list[str],
    mode: str,
    *,
    preflight_strict: bool = False,
) -> dict:
    checkpoint_failures: list[dict] = []
    file_conflicts: list[dict] = []
    ownership_conflicts: list[dict] = []

    for p in packets:
        task_id = p.get("task_id", "")
        lane_id = p.get("lane_id", "")
        cp_req = p.get("checkpoint_required", "")
        cp_status = p.get("checkpoint_status")
        if not checkpoint_is_approved(cp_req, cp_status):
            checkpoint_failures.append(
                {
                    "task_id": task_id,
                    "lane_id": lane_id,
                    "checkpoint_required": cp_req,
                    "checkpoint_status": cp_status,
                }
            )
        allowed = set(p.get("allowed_files", []))
        forbidden = set(p.get("forbidden_files", []))
        overlap = sorted(allowed & forbidden)
        if overlap:
            file_conflicts.append({"task_id": task_id, "lane_id": lane_id, "overlap": overlap})
        for f in p.get("allowed_files", []):
            if any(Path(f).match(rule) for rule in denied_patterns):
                ownership_conflicts.append({"task_id": task_id, "lane_id": lane_id, "path": f})

    preflight = {
        "task_packet_exists": bool(packets),
        "checkpoint_ok": len(checkpoint_failures) == 0,
        "checkpoint_failures": checkpoint_failures,
        "allowed_forbidden_conflict": len(file_conflicts) > 0,
        "allowed_forbidden_conflicts": file_conflicts,
        "ownership_conflict": len(ownership_conflicts) > 0,
        "ownership_conflicts": ownership_conflicts,
        "strict_lint_pass": lint_status == "PASS",
    }

    blockers: list[str] = []
    if not preflight["task_packet_exists"]:
        blockers.append("task packet missing")
    if not preflight["checkpoint_ok"]:
        blockers.append("checkpoint not approved")
    if preflight["allowed_forbidden_conflict"]:
        blockers.append("allowed/forbidden file conflict")
    if preflight["ownership_conflict"]:
        blockers.append("ownership conflict detected")
    if (mode == "execute" or preflight_strict) and not preflight["strict_lint_pass"]:
        blockers.append("strict lint is not PASS")
    preflight["blockers"] = blockers
    return preflight


def cmd_run(args: Namespace) -> int:
    out_root = Path(args.out_root) if getattr(args, "out_root", None) else None
    paths = resolve_paths(Path(args.repo_root), out_root=out_root)
    ensure_out_dirs(paths)
    task_id = args.task_id
    mode = args.mode
    preflight_strict = bool(getattr(args, "preflight_strict", False))
    allow_executor_on_block = bool(getattr(args, "allow_executor_on_block", False))
    profile = str(getattr(args, "profile", "standalone"))

    emit_event(paths, event_type="command_started", command="run", task_id=task_id, message="run started", data={"mode": mode, "profile": profile})

    packet_path = paths.plans_dir / f"{task_id}.task_packets.json"
    lint_path = paths.contracts_dir / "lint_report.json"
    ownership_path = paths.contracts_dir / "ownership_contracts.json"

    packets: list[dict] = []
    if packet_path.exists():
        packets = _load_json(packet_path).get("packets", [])

    lint_status = ""
    if lint_path.exists():
        lint_status = str(_load_json(lint_path).get("status", ""))

    denied_patterns: list[str] = []
    if ownership_path.exists():
        own = _load_json(ownership_path)
        owners = own.get("owners", []) if isinstance(own, dict) else []
        denied_patterns = [x.get("path") for x in owners if x.get("write_policy") == "forbidden" and x.get("path")]

    preflight = evaluate_runtime_preflight(packets, lint_status, denied_patterns, mode, preflight_strict=preflight_strict)
    preflight_findings = validate_runtime_preflight(preflight)
    blockers: list[str] = list(preflight.get("blockers", []))
    if preflight_findings:
        blockers.extend([f["message"] for f in preflight_findings])

    code = OK
    output = ""
    executed_command = ""
    should_block = bool(blockers) and (mode == "execute" or preflight_strict or not allow_executor_on_block)
    if should_block:
        code = PREFLIGHT_BLOCKED
        output = "RUN BLOCKED: " + "; ".join(blockers)
        emit_event(
            paths,
            event_type="preflight_blocked",
            command="run",
            task_id=task_id,
            severity="FAIL",
            reason_code=str(PREFLIGHT_BLOCKED),
            message=output,
            data={"mode": mode, "preflight_strict": preflight_strict, "allow_executor_on_block": allow_executor_on_block},
        )
    else:
        cmd = [sys.executable, "tools/ai_executor.py", "--task", task_id, "--mode", mode]
        executed_command = " ".join(cmd)
        code, output = run(cmd, cwd=paths.repo_root)
        if code != 0:
            code = EXECUTOR_ERROR

    report = {
        "generated_at": now_iso(),
        "task_id": task_id,
        "mode": mode,
        "profile": profile,
        "preflight_strict": preflight_strict,
        "allow_executor_on_block": allow_executor_on_block,
        "preflight": preflight,
        "preflight_findings": preflight_findings,
        "blockers": blockers,
        "command": executed_command,
        "exit_code": code,
        "error_code": code,
        "output": output,
    }
    out = paths.runs_dir / f"{task_id}.{mode}.run_report.json"
    write_json(out, report)
    print(f"WROTE={out}")
    print(f"EXIT_CODE={code}")

    emit_event(
        paths,
        event_type="command_completed",
        command="run",
        task_id=task_id,
        severity="FAIL" if code else "INFO",
        reason_code=str(code),
        message="run completed",
        data={"mode": mode, "blocked": should_block, "exit_code": code},
    )
    return code
