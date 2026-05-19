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
    invalid: list[str] = []
    weak: list[str] = []
    for group, candidates in required.items():
        if not any(c in present for c in candidates):
            missing.append(group)

    def _read_json(p: Path) -> object | None:
        try:
            return json.loads(read_text(p))
        except Exception:
            return None

    def _is_non_empty_text(p: Path) -> bool:
        try:
            return bool(read_text(p).strip())
        except Exception:
            return False

    def _check_manifest(p: Path) -> None:
        data = _read_json(p)
        if data is None or not isinstance(data, dict):
            invalid.append("manifest.json")
            return
        if not data:
            weak.append("manifest.json:empty_object")
            return
        useful = {"task_id", "generated_at", "status", "files", "artifacts", "commands", "evidence"}
        if not any(k in data for k in useful):
            weak.append("manifest.json:missing_useful_keys")

    def _check_quality_gates(p: Path) -> None:
        data = _read_json(p)
        if data is None or not isinstance(data, dict):
            invalid.append(p.name)
            return
        useful = {"status", "gates", "results", "passed", "exit_code"}
        if not any(k in data for k in useful):
            weak.append(f"{p.name}:missing_useful_keys")

    def _check_lint_report(p: Path) -> None:
        data = _read_json(p)
        if data is None or not isinstance(data, dict):
            invalid.append("lint_report.json")
            return
        if "status" not in data:
            weak.append("lint_report.json:missing_status")

    def _check_run_report(p: Path) -> None:
        data = _read_json(p)
        if data is None or not isinstance(data, dict):
            invalid.append("run_report.json")
            return
        if "exit_code" not in data:
            weak.append("run_report.json:missing_exit_code")

    def _check_changed_files(p: Path) -> None:
        data = _read_json(p)
        if data is None:
            invalid.append("changed-files.json")
            return
        if isinstance(data, (list, dict)) and len(data) == 0:
            invalid.append("changed-files.json:empty")

    def _check_patch(p: Path) -> None:
        if not _is_non_empty_text(p):
            invalid.append(p.name)

    def _check_command_log(p: Path) -> None:
        if not _is_non_empty_text(p):
            invalid.append("command-log.txt")

    if evidence_dir.exists():
        manifest = evidence_dir / "manifest.json"
        if manifest.exists():
            _check_manifest(manifest)
        qg = evidence_dir / "quality-gates.json"
        lint = evidence_dir / "lint_report.json"
        if qg.exists():
            _check_quality_gates(qg)
        elif lint.exists():
            _check_lint_report(lint)
        cmdlog = evidence_dir / "command-log.txt"
        runrep = evidence_dir / "run_report.json"
        if cmdlog.exists():
            _check_command_log(cmdlog)
        elif runrep.exists():
            _check_run_report(runrep)
        changed = evidence_dir / "changed-files.json"
        gpatch = evidence_dir / "git-diff.patch"
        dpatch = evidence_dir / "diff.patch"
        if changed.exists():
            _check_changed_files(changed)
        elif gpatch.exists():
            _check_patch(gpatch)
        elif dpatch.exists():
            _check_patch(dpatch)

    sufficient = len(missing) == 0 and len(invalid) == 0
    return {
        "exists": evidence_dir.exists(),
        "file_count": len(files),
        "files": files,
        "required": required,
        "missing": missing,
        "invalid": invalid,
        "weak": weak,
        "sufficient": sufficient,
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
