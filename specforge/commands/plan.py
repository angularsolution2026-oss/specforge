from __future__ import annotations

import re
from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..models import TaskPacket, to_json
from ..utils import now_iso, read_text, write_json


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


def cmd_plan(args: Namespace) -> int:
    paths = resolve_paths(Path(args.repo_root))
    ensure_out_dirs(paths)
    task_id = args.task_id
    lanes_path = paths.repo_root / ".ai" / "tasks" / f"{task_id}.parallel-lanes.md"
    if not lanes_path.exists():
        raise SystemExit(f"Missing lanes file: {lanes_path}")
    text = read_text(lanes_path)
    packets: list[TaskPacket] = []
    for lane_id, sec in _extract_lane_sections(text):
        owner = _extract_field(sec, "Assigned agents") or "Unassigned"
        obj = _extract_field(sec, "Objective") or f"Execute lane {lane_id} for {task_id}"
        allowed = _extract_list(sec, "Allowed files")
        forbidden = _extract_list(sec, "Forbidden files")
        packets.append(
            TaskPacket(
                task_id=task_id,
                lane_id=lane_id,
                owner=owner,
                objective=obj,
                allowed_files=allowed,
                forbidden_files=forbidden,
                required_gates=["tier1"],
                refs=[
                    ".ai/core/orchestration.md",
                    ".ai/governance/AGENT_HANDOFF_PROTOCOL.md",
                    ".ai/core/quality-gates.md",
                ],
            )
        )

    out = paths.plans_dir / f"{task_id}.task_packets.json"
    payload = {"generated_at": now_iso(), "task_id": task_id, "packet_count": len(packets), "packets": to_json(packets)}
    write_json(out, payload)
    print(f"WROTE={out}")
    print(f"PACKETS={len(packets)}")
    return 0
