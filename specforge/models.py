from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field


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


class CanonicalAuthority(BaseModel):
    canonical_spec_root: str
    deprecated_spec_roots: list[str] = Field(default_factory=list)
    conflict_rule: str
    agent_required_read_order: list[str] = Field(default_factory=list)


class FileOwnerRule(BaseModel):
    path: str
    owner: str
    write_policy: str


class FileOwnershipMap(BaseModel):
    generated_at: str
    owners: list[FileOwnerRule] = Field(default_factory=list)


class TaskNode(BaseModel):
    task_id: str
    title: str
    status: str = "pending"
    dependencies: list[str] = Field(default_factory=list)
    checkpoint_required: str = ""
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    required_gates: list[str] = Field(default_factory=list)
    checkpoint_status: str = ""
    owner: str = ""
    objective: str = ""
    stop_conditions: list[str] = Field(default_factory=list)
    evidence_required: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)


class TaskGraph(BaseModel):
    generated_at: str
    tasks: list[TaskNode] = Field(default_factory=list)


class TaskStateCurrent(BaseModel):
    generated_at: str
    task_id: str
    status: str
    checkpoint_status: str = ""
    evidence_ready: bool = False
    notes: str = ""


class TaskStateHistoryEntry(BaseModel):
    generated_at: str
    task_id: str
    from_status: str = ""
    to_status: str
    actor: str = "specforge"
    note: str = ""


class PlanTaskPacket(BaseModel):
    task_id: str
    title: str
    lane_id: str
    owner: str
    objective: str
    dependencies: list[str] = Field(default_factory=list)
    checkpoint_required: str = ""
    checkpoint_status: str = ""
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    required_gates: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    evidence_required: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)


def to_json(data: Any) -> Any:
    if hasattr(data, "__dataclass_fields__"):
        return asdict(data)
    if isinstance(data, list):
        return [to_json(x) for x in data]
    if isinstance(data, dict):
        return {k: to_json(v) for k, v in data.items()}
    return data
