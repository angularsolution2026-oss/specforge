from __future__ import annotations

import json
import re
from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..models import PlanTaskPacket, TaskGraph
from ..utils import now_iso, read_text, write_json
from ..validators import validate_task_packet_bundle


def _extract_lane_sections(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^## Lane ([A-Z]).*$", text, flags=re.M))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1), text[start:end]))
    return out


def _extract_list(section: str, heading: str) -> list[str]:
    marker = f"### {heading}"
    i = section.find(marker)
    if i < 0:
        return []
    tail = section[i + len(marker) :]
    j = tail.find("\n### ")
    if j >= 0:
        tail = tail[:j]
    out: list[str] = []
    for ln in tail.splitlines():
        if "|" not in ln or "---" in ln:
            continue
        cells = [c.strip().strip("`") for c in ln.strip("|").split("|")]
        if not cells:
            continue
        if cells[0].lower() in {"path", "file"}:
            continue
        out.append(cells[0])
    return out


def _extract_field(section: str, field: str) -> str:
    for ln in section.splitlines():
        if "|" not in ln:
            continue
        cells = [c.strip().strip("* ") for c in ln.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] == field:
            return cells[1]
    return ""


def _load_checkpoint_status(repo_root: Path, task_id: str, checkpoint: str) -> str:
    cp = repo_root / ".ai/state/checkpoints.json"
    if not cp.exists() or not checkpoint:
        return ""
    data = json.loads(read_text(cp))
    return (
        data.get("tasks", {})
        .get(task_id, {})
        .get("checkpoints", {})
        .get(checkpoint, {})
        .get("status", "")
    )


def cmd_plan(args: Namespace) -> int:
    paths = resolve_paths(Path(args.repo_root))
    ensure_out_dirs(paths)
    task_id = args.task_id
    packets: list[PlanTaskPacket] = []
    source = ""

    task_graph_path = paths.repo_root / ".ai/tasks/TASK_GRAPH.json"
    if task_graph_path.exists():
        graph = TaskGraph.model_validate(json.loads(read_text(task_graph_path)))
        source = ".ai/tasks/TASK_GRAPH.json"
        task = next((t for t in graph.tasks if t.task_id == task_id), None)
        if task is None:
            raise SystemExit(f"Task ID {task_id} not found in {task_graph_path}")
        lane_id = "A"
        packets.append(
            PlanTaskPacket(
                task_id=task.task_id,
                title=task.title,
                lane_id=lane_id,
                owner=task.owner or "Unassigned",
                objective=task.objective or f"Implement {task.task_id}: {task.title}",
                dependencies=task.dependencies,
                checkpoint_required=task.checkpoint_required,
                checkpoint_status=_load_checkpoint_status(paths.repo_root, task.task_id, task.checkpoint_required),
                allowed_files=task.allowed_files,
                forbidden_files=task.forbidden_files,
                required_context=task.required_context,
                required_gates=task.required_gates,
                stop_conditions=task.stop_conditions or [
                    "Stop if checkpoint is not approved.",
                    "Stop if ownership conflict is detected.",
                    "Stop if required files are missing.",
                ],
                evidence_required=task.evidence_required or [
                    "test_output",
                    "lint_report",
                    "changed_files_manifest",
                ],
                validation_commands=task.validation_commands or [
                    "python -m specforge --repo-root . lint --strict",
                ],
                refs=task.refs,
            )
        )
    else:
        lanes_path = paths.repo_root / ".ai" / "tasks" / f"{task_id}.parallel-lanes.md"
        if not lanes_path.exists():
            raise SystemExit(f"Missing task graph and lanes file for task {task_id}")
        source = str(lanes_path.relative_to(paths.repo_root)).replace("\\", "/")
        text = read_text(lanes_path)
        for lane_id, sec in _extract_lane_sections(text):
            owner = _extract_field(sec, "Assigned agents") or "Unassigned"
            obj = _extract_field(sec, "Objective") or f"Execute lane {lane_id} for {task_id}"
            allowed = _extract_list(sec, "Allowed files")
            forbidden = _extract_list(sec, "Forbidden files")
            packets.append(
                PlanTaskPacket(
                    task_id=task_id,
                    title=f"Lane {lane_id}",
                    lane_id=lane_id,
                    owner=owner,
                    objective=obj,
                    dependencies=[],
                    checkpoint_required="CP-0",
                    checkpoint_status=_load_checkpoint_status(paths.repo_root, task_id, "CP-0"),
                    allowed_files=allowed,
                    forbidden_files=forbidden,
                    required_context=[
                        ".ai/core/orchestration.md",
                        ".ai/governance/AGENT_HANDOFF_PROTOCOL.md",
                    ],
                    required_gates=["tier1"],
                    stop_conditions=[
                        "Stop if checkpoint is not approved.",
                        "Stop on ownership conflict.",
                    ],
                    evidence_required=["lint_report", "verification_footer"],
                    validation_commands=["python -m specforge --repo-root . lint --strict"],
                    refs=[
                        ".ai/core/orchestration.md",
                        ".ai/governance/AGENT_HANDOFF_PROTOCOL.md",
                        ".ai/core/quality-gates.md",
                    ],
                )
            )

    payload = {
        "generated_at": now_iso(),
        "task_id": task_id,
        "source": source,
        "packet_count": len(packets),
        "packets": [p.model_dump() for p in packets],
    }
    val_findings = validate_task_packet_bundle(payload)
    if val_findings:
        payload["validation_findings"] = val_findings

    out = paths.plans_dir / f"{task_id}.task_packets.json"
    write_json(out, payload)
    print(f"WROTE={out}")
    print(f"PACKETS={len(packets)}")
    print(f"SOURCE={source}")
    return 0
