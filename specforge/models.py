from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RouteContract:
    route: str
    source: str
    priority: str = ""
    sprint: str = ""


@dataclass(frozen=True)
class ApiContract:
    endpoint: str
    method: str
    source: str


@dataclass(frozen=True)
class TaskPacket:
    task_id: str
    lane_id: str
    owner: str
    objective: str
    allowed_files: list[str]
    forbidden_files: list[str]
    required_gates: list[str]
    refs: list[str]


def to_json(data: Any) -> Any:
    if hasattr(data, "__dataclass_fields__"):
        return asdict(data)
    if isinstance(data, list):
        return [to_json(x) for x in data]
    if isinstance(data, dict):
        return {k: to_json(v) for k, v in data.items()}
    return data
