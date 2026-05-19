from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..utils import now_iso, read_text, run, write_json


def _load_json(path: Path) -> dict:
    return json.loads(read_text(path))


def cmd_doctor(args: Namespace) -> int:
    paths = resolve_paths(Path(args.repo_root))
    ensure_out_dirs(paths)

    task_id = args.task_id
    steps: list[dict] = []

    # Step 1: ingest
    cmd = [sys.executable, "-m", "specforge", "--repo-root", str(paths.repo_root), "ingest"]
    code, out = run(cmd, cwd=paths.app_root)
    steps.append({"step": "ingest", "command": " ".join(cmd), "exit_code": code, "output": out})
    if code != 0:
        return _finalize(paths, task_id, steps, "FAIL")

    # Step 2: normalize
    cmd = [sys.executable, "-m", "specforge", "--repo-root", str(paths.repo_root), "normalize"]
    code, out = run(cmd, cwd=paths.app_root)
    steps.append({"step": "normalize", "command": " ".join(cmd), "exit_code": code, "output": out})
    if code != 0:
        return _finalize(paths, task_id, steps, "FAIL")

    # Step 3: strict lint
    cmd = [sys.executable, "-m", "specforge", "--repo-root", str(paths.repo_root), "lint", "--strict"]
    code, out = run(cmd, cwd=paths.app_root)
    steps.append({"step": "lint_strict", "command": " ".join(cmd), "exit_code": code, "output": out})
    if code != 0:
        return _finalize(paths, task_id, steps, "FAIL")

    # Step 4: plan
    cmd = [sys.executable, "-m", "specforge", "--repo-root", str(paths.repo_root), "plan", "--task-id", task_id]
    code, out = run(cmd, cwd=paths.app_root)
    steps.append({"step": "plan", "command": " ".join(cmd), "exit_code": code, "output": out})
    if code != 0:
        return _finalize(paths, task_id, steps, "FAIL")

    # Step 5: prompt
    cmd = [sys.executable, "-m", "specforge", "--repo-root", str(paths.repo_root), "prompt", "--task-id", task_id]
    code, out = run(cmd, cwd=paths.app_root)
    steps.append({"step": "prompt", "command": " ".join(cmd), "exit_code": code, "output": out})
    if code != 0:
        return _finalize(paths, task_id, steps, "FAIL")

    # Step 6: reconcile (optional sync)
    cmd = [sys.executable, "-m", "specforge", "--repo-root", str(paths.repo_root), "reconcile", "--task-id", task_id]
    if args.sync:
        cmd.append("--sync")
    code, out = run(cmd, cwd=paths.app_root)
    steps.append({"step": "reconcile", "command": " ".join(cmd), "exit_code": code, "output": out})
    if code != 0:
        return _finalize(paths, task_id, steps, "FAIL")

    # Step 7: optional task run
    if args.run_mode:
        cmd = [
            sys.executable,
            "-m",
            "specforge",
            "--repo-root",
            str(paths.repo_root),
            "run",
            "--task-id",
            task_id,
            "--mode",
            args.run_mode,
        ]
        code, out = run(cmd, cwd=paths.app_root)
        steps.append({"step": f"run_{args.run_mode}", "command": " ".join(cmd), "exit_code": code, "output": out})
        if code != 0:
            return _finalize(paths, task_id, steps, "FAIL")

    # Step 8: artifact consistency check
    status = "PASS"
    checks: list[dict] = []
    expected = [
        paths.inventory_dir / "repo_inventory.json",
        paths.contracts_dir / "route_contracts.json",
        paths.contracts_dir / "api_contracts.json",
        paths.contracts_dir / "lint_report.json",
        paths.plans_dir / f"{task_id}.task_packets.json",
        paths.prompts_dir / f"{task_id}.MASTER_PROMPT.md",
        paths.reconcile_dir / f"{task_id}.reconcile_report.json",
    ]
    for p in expected:
        checks.append({"artifact": str(p), "exists": p.exists()})
        if not p.exists():
            status = "FAIL"

    lint_report = _load_json(paths.contracts_dir / "lint_report.json")
    if lint_report.get("status") != "PASS":
        status = "FAIL"
        checks.append({"artifact": "lint_report.status", "value": lint_report.get("status"), "expected": "PASS"})

    out = {
        "generated_at": now_iso(),
        "task_id": task_id,
        "status": status,
        "steps": steps,
        "artifact_checks": checks,
    }
    out_path = paths.runs_dir / f"{task_id}.doctor_report.json"
    write_json(out_path, out)
    print(f"STATUS={status}")
    print(f"WROTE={out_path}")
    return 0 if status == "PASS" else 1


def _finalize(paths, task_id: str, steps: list[dict], status: str) -> int:
    out = {"generated_at": now_iso(), "task_id": task_id, "status": status, "steps": steps}
    out_path = paths.runs_dir / f"{task_id}.doctor_report.json"
    write_json(out_path, out)
    print(f"STATUS={status}")
    print(f"WROTE={out_path}")
    return 1
