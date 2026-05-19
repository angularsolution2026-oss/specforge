from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..utils import now_iso, read_text, write_json


def _safe_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(read_text(path))


def cmd_reconcile(args: Namespace) -> int:
    paths = resolve_paths(Path(args.repo_root))
    ensure_out_dirs(paths)
    task_id = args.task_id

    checkpoints = _safe_json(paths.repo_root / ".ai/state/checkpoints.json")
    task_state = read_text(paths.repo_root / ".ai/state/task-state.md") if (paths.repo_root / ".ai/state/task-state.md").exists() else ""
    progress = read_text(paths.repo_root / ".ai/planning/PROGRESS_CHECKLIST.md") if (paths.repo_root / ".ai/planning/PROGRESS_CHECKLIST.md").exists() else ""
    task_graph = read_text(paths.repo_root / ".ai/planning/TASK_GRAPH.md") if (paths.repo_root / ".ai/planning/TASK_GRAPH.md").exists() else ""

    cp0 = (
        checkpoints.get("tasks", {})
        .get(task_id, {})
        .get("checkpoints", {})
        .get("CP-0", {})
        .get("status", "missing")
    )

    report = {
        "generated_at": now_iso(),
        "task_id": task_id,
        "checkpoint_cp0_status": cp0,
        "task_state_mentions_task": task_id in task_state,
        "progress_mentions_task": task_id in progress,
        "task_graph_mentions_task": task_id in task_graph,
        "recommendation": "",
    }
    if cp0 != "approved":
        report["recommendation"] = "Checkpoint CP-0 not approved; keep execute blocked."
    else:
        report["recommendation"] = "Checkpoint approved; verify gates and evidence before completion."

    out = paths.reconcile_dir / f"{task_id}.reconcile_report.json"
    write_json(out, report)

    if getattr(args, "sync", False):
        sync_notes = []
        state_path = paths.repo_root / ".ai/state/task-state.md"
        prog_path = paths.repo_root / ".ai/planning/PROGRESS_CHECKLIST.md"
        stamp = now_iso()
        if state_path.exists():
            state_text = read_text(state_path)
            state_text += (
                f"\n| {stamp[:10]} | SPECFORGE-RECONCILE | {task_id} | "
                f"CP0={cp0}; task_state={report['task_state_mentions_task']}; progress={report['progress_mentions_task']} |\n"
            )
            state_path.write_text(state_text, encoding="utf-8", newline="\n")
            sync_notes.append(str(state_path))
        if prog_path.exists():
            prog_text = read_text(prog_path)
            if task_id not in prog_text:
                prog_text += f"\n- [ ] **{task_id}** — Added by specforge reconcile ({stamp})\n"
                prog_path.write_text(prog_text, encoding="utf-8", newline="\n")
                sync_notes.append(str(prog_path))
        report["sync_notes"] = sync_notes
        write_json(out, report)

    print(f"WROTE={out}")
    print(f"CP0={cp0}")
    if getattr(args, "sync", False):
        print(f"SYNCED={len(report.get('sync_notes', []))}")
    return 0
