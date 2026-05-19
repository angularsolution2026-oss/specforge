from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..utils import now_iso, run, write_json


def cmd_run(args: Namespace) -> int:
    paths = resolve_paths(Path(args.repo_root))
    ensure_out_dirs(paths)

    task_id = args.task_id
    mode = args.mode
    cmd = [sys.executable, "tools/ai_executor.py", "--task", task_id, "--mode", mode]
    code, output = run(cmd, cwd=paths.repo_root)

    report = {
        "generated_at": now_iso(),
        "task_id": task_id,
        "mode": mode,
        "command": " ".join(cmd),
        "exit_code": code,
        "output": output,
    }
    out = paths.runs_dir / f"{task_id}.{mode}.run_report.json"
    write_json(out, report)
    print(f"WROTE={out}")
    print(f"EXIT_CODE={code}")
    return code
