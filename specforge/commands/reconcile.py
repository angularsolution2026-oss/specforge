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


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def evaluate_evidence(evidence_dir: Path, repo_root: Path | None = None) -> dict:
    files: list[str] = []
    if evidence_dir.exists():
        for p in sorted(evidence_dir.rglob("*")):
            if not p.is_file():
                continue
            if repo_root is not None:
                files.append(str(p.relative_to(repo_root)).replace("\\", "/"))
            else:
                files.append(p.name)
    present = {Path(x).name for x in files}
    required = {
        "manifest": ["manifest.json"],
        "quality_gate_proof": ["quality-gates.json", "lint_report.json"],
        "command_log": ["command-log.txt", "run_report.json"],
        "change_proof": ["changed-files.json", "git-diff.patch", "diff.patch"],
    }
    missing: list[str] = []
    for group, candidates in required.items():
        if not any(c in present for c in candidates):
            missing.append(group)
    return {
        "exists": evidence_dir.exists(),
        "file_count": len(files),
        "files": files,
        "required": required,
        "missing": missing,
        "sufficient": len(missing) == 0,
    }


def cmd_reconcile(args: Namespace) -> int:
    paths = resolve_paths(Path(args.repo_root))
    ensure_out_dirs(paths)
    task_id = args.task_id

    checkpoints = _safe_json(paths.repo_root / ".ai/state/checkpoints.json")
    current_json = _safe_json(paths.repo_root / ".ai/state/task-state.current.json")
    task_state_md = (
        read_text(paths.repo_root / ".ai/state/task-state.md") if (paths.repo_root / ".ai/state/task-state.md").exists() else ""
    )
    progress = (
        read_text(paths.repo_root / ".ai/planning/PROGRESS_CHECKLIST.md")
        if (paths.repo_root / ".ai/planning/PROGRESS_CHECKLIST.md").exists()
        else ""
    )
    task_graph_md = (
        read_text(paths.repo_root / ".ai/planning/TASK_GRAPH.md") if (paths.repo_root / ".ai/planning/TASK_GRAPH.md").exists() else ""
    )

    cp0 = checkpoints.get("tasks", {}).get(task_id, {}).get("checkpoints", {}).get("CP-0", {}).get("status", "missing")
    state_source = "markdown_fallback"
    state_status = "unknown"
    if current_json:
        state_source = "task-state.current.json"
        if isinstance(current_json, dict):
            if current_json.get("task_id") == task_id:
                state_status = current_json.get("status", "unknown")
            elif task_id in current_json.get("tasks", {}):
                state_status = current_json.get("tasks", {}).get(task_id, {}).get("status", "unknown")

    evidence_dir = paths.repo_root / ".ai/evidence" / task_id
    evidence_eval = evaluate_evidence(evidence_dir, repo_root=paths.repo_root)
    evidence_sufficient = bool(evidence_eval["sufficient"])

    report = {
        "generated_at": now_iso(),
        "task_id": task_id,
        "state_source": state_source,
        "state_status": state_status,
        "checkpoint_cp0_status": cp0,
        "task_state_mentions_task": task_id in task_state_md,
        "progress_mentions_task": task_id in progress,
        "task_graph_mentions_task": task_id in task_graph_md,
        "evidence": {"directory": str(evidence_dir.relative_to(paths.repo_root)).replace("\\", "/"), **evidence_eval},
        "recommendation": "",
    }
    if cp0 != "approved":
        report["recommendation"] = "Checkpoint CP-0 not approved; keep execute blocked."
    elif not evidence_sufficient:
        report["recommendation"] = "Checkpoint approved but evidence missing; do not mark PASS."
    else:
        report["recommendation"] = "Checkpoint approved with evidence present; proceed to gate verification."

    out = paths.reconcile_dir / f"{task_id}.reconcile_report.json"
    write_json(out, report)

    if getattr(args, "sync", False):
        hist_path = paths.repo_root / ".ai/state/task-state.history.jsonl"
        _append_jsonl(
            hist_path,
            {
                "generated_at": now_iso(),
                "task_id": task_id,
                "checkpoint_cp0_status": cp0,
                "evidence_sufficient": evidence_sufficient,
                "recommendation": report["recommendation"],
            },
        )
        report["sync_notes"] = [str(hist_path.relative_to(paths.repo_root)).replace("\\", "/")]
        write_json(out, report)

    print(f"WROTE={out}")
    print(f"CP0={cp0}")
    print(f"EVIDENCE_SUFFICIENT={evidence_sufficient}")
    return 0
