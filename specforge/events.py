from __future__ import annotations

import json
from typing import Any

from .config import AppPaths
from .utils import now_iso


def emit_event(
    paths: AppPaths,
    *,
    event_type: str,
    command: str,
    task_id: str = "",
    severity: str = "INFO",
    reason_code: str = "",
    message: str = "",
    data: dict[str, Any] | None = None,
) -> None:
    if paths.events_dir is None:
        return
    event = {
        "generated_at": now_iso(),
        "event_type": event_type,
        "command": command,
        "task_id": task_id,
        "severity": severity,
        "reason_code": reason_code,
        "message": message,
        "data": data or {},
    }
    out = paths.events_dir / "specforge_events.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
