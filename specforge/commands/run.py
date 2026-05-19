from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..utils import now_iso, read_text, run, write_json
from ..validators import validate_runtime_preflight


def _load_json(path: Path) -> dict:
    return json.loads(read_text(path))


def cmd_run(args: Namespace) -> int:
    paths = resolve_paths(Path(args.repo_root))
    ensure_out_dirs(paths)
    task_id = args.task_id
    mode = args.mode

    packet_path = paths.plans_dir / f"{task_id}.task_packets.json"
    lint_path = paths.contracts_dir / "lint_report.json"
    ownership_path = paths.contracts_dir / "ownership_contracts.json"

    preflight = {
        "task_packet_exists": packet_path.exists(),
        "checkpoint_ok": False,
        "allowed_forbidden_conflict": False,
        "ownership_conflict": False,
        "strict_lint_pass": False,
        "notes": [],
    }

    if packet_path.exists():
        packets = _load_json(packet_path).get("packets", [])
        cp_bad = False
        file_conflict = False
        for p in packets:
            cp_req = p.get("checkpoint_required", "")
            cp_status = p.get("checkpoint_status", "")
            if cp_req and cp_status and cp_status != "approved":
                cp_bad = True
            allowed = set(p.get("allowed_files", []))
            forbidden = set(p.get("forbidden_files", []))
            if allowed & forbidden:
                file_conflict = True
        preflight["checkpoint_ok"] = not cp_bad
        preflight["allowed_forbidden_conflict"] = file_conflict
    else:
        preflight["notes"].append("task_packet_missing")

    if lint_path.exists():
        lint = _load_json(lint_path)
        preflight["strict_lint_pass"] = lint.get("status") == "PASS"
    else:
        preflight["notes"].append("lint_report_missing")

    if ownership_path.exists() and packet_path.exists():
        own = _load_json(ownership_path)
        owners = own.get("owners", []) if isinstance(own, dict) else []
        write_denied_paths = [x.get("path") for x in owners if x.get("write_policy") == "forbidden"]
        packets = _load_json(packet_path).get("packets", [])
        for p in packets:
            for f in p.get("allowed_files", []):
                if any(Path(f).match(rule) for rule in write_denied_paths):
                    preflight["ownership_conflict"] = True
                    break

    preflight_findings = validate_runtime_preflight(preflight)
    blockers: list[str] = []
    if preflight_findings:
        blockers.extend([f["message"] for f in preflight_findings])
    if not preflight["task_packet_exists"]:
        blockers.append("task packet missing")
    if not preflight["checkpoint_ok"]:
        blockers.append("checkpoint not approved")
    if preflight["allowed_forbidden_conflict"]:
        blockers.append("allowed/forbidden file conflict")
    if preflight["ownership_conflict"]:
        blockers.append("ownership conflict detected")
    if mode == "execute" and not preflight["strict_lint_pass"]:
        blockers.append("strict lint is not PASS")

    code = 0
    output = ""
    executed_command = ""
    if blockers and mode == "execute":
        code = 2
        output = "RUN BLOCKED: " + "; ".join(blockers)
    else:
        cmd = [sys.executable, "tools/ai_executor.py", "--task", task_id, "--mode", mode]
        executed_command = " ".join(cmd)
        code, output = run(cmd, cwd=paths.repo_root)

    report = {
        "generated_at": now_iso(),
        "task_id": task_id,
        "mode": mode,
        "preflight": preflight,
        "preflight_findings": preflight_findings,
        "blockers": blockers,
        "command": executed_command,
        "exit_code": code,
        "output": output,
    }
    out = paths.runs_dir / f"{task_id}.{mode}.run_report.json"
    write_json(out, report)
    print(f"WROTE={out}")
    print(f"EXIT_CODE={code}")
    return code
