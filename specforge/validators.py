from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, Field, ValidationError, field_validator

from .models import CanonicalAuthority, FileOwnershipMap, TaskGraph
from .utils import read_text


TASK_ID_PATTERN = re.compile(r"^(P\d+-\d+|GOV-[A-Za-z0-9-]+)$")


class RouteContractModel(BaseModel):
    route: str
    source: str
    priority: str = ""
    sprint: str = ""

    @field_validator("route")
    @classmethod
    def route_must_start_with_slash(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("route must start with '/'")
        if any(c.isspace() for c in value):
            raise ValueError("route must not contain whitespace")
        return value

    @field_validator("source")
    @classmethod
    def source_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source must not be empty")
        return value


class ApiContractModel(BaseModel):
    endpoint: str
    method: str
    source: str

    @field_validator("method")
    @classmethod
    def method_allowed(cls, value: str) -> str:
        allowed = {"GET", "POST", "PUT", "PATCH", "DELETE"}
        if value not in allowed:
            raise ValueError(f"method must be one of {sorted(allowed)}")
        return value

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_api(cls, value: str) -> str:
        if not value.startswith("/api/"):
            raise ValueError("endpoint must start with /api/")
        return value

    @field_validator("source")
    @classmethod
    def source_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source must not be empty")
        return value


class TaskPacketModel(BaseModel):
    task_id: str
    lane_id: str
    owner: str = ""
    objective: str = ""
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)
    required_gates: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)

    @field_validator("task_id")
    @classmethod
    def task_id_pattern(cls, value: str) -> str:
        if not TASK_ID_PATTERN.match(value):
            raise ValueError("task_id must match P0-000 style or GOV-xxx")
        return value

    @field_validator("lane_id")
    @classmethod
    def lane_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("lane_id must not be empty")
        return value


class GateMatrixModel(BaseModel):
    generated_at: str
    source: str
    tiers_detected: list[str]

    @field_validator("generated_at", "source")
    @classmethod
    def required_string(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value


class CheckpointPolicyModel(BaseModel):
    generated_at: str
    source: str
    tasks: dict[str, dict[str, Any]]


class SeedSchemaManifestModel(BaseModel):
    generated_at: str
    source: str
    is_demo_rules_present: bool
    seed_files: list[str]

    @field_validator("seed_files")
    @classmethod
    def seed_files_json(cls, values: list[str]) -> list[str]:
        for v in values:
            if v and not v.endswith(".json"):
                raise ValueError("each seed file should end with .json")
        return values


def _load_json(path: Path) -> Any:
    return json.loads(read_text(path))


def _record(findings: list[dict[str, str]], file: str, err: str) -> None:
    findings.append({"severity": "FAIL", "check": "pydantic_validation", "file": file, "message": err})


def validate_canonical_authority(payload: Any) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        CanonicalAuthority.model_validate(payload)
    except ValidationError as exc:
        _record(findings, "canonical_authority.json", str(exc))
    return findings


def validate_file_ownership_map(payload: Any) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        FileOwnershipMap.model_validate(payload)
    except ValidationError as exc:
        _record(findings, "ownership_contracts.json", str(exc))
    return findings


def validate_task_graph(payload: Any) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        TaskGraph.model_validate(payload)
    except ValidationError as exc:
        _record(findings, "task_graph_contracts.json", str(exc))
    return findings


def validate_task_packet_bundle(payload: Any) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    packets = payload.get("packets", []) if isinstance(payload, dict) else []
    if not isinstance(packets, list):
        _record(findings, "task_packets", "packets must be a list")
        return findings
    for i, packet in enumerate(packets):
        try:
            TaskPacketModel.model_validate(packet)
        except ValidationError as exc:
            _record(findings, f"task_packets[{i}]", str(exc))
    return findings


def validate_runtime_preflight(preflight: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    required = [
        "task_packet_exists",
        "checkpoint_ok",
        "allowed_forbidden_conflict",
        "ownership_conflict",
        "strict_lint_pass",
    ]
    for key in required:
        if key not in preflight:
            _record(findings, "run_preflight", f"missing preflight key: {key}")
    return findings


def validate_contract_bundle(contracts_dir: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    checks: list[tuple[str, Any]] = [
        ("route_contracts.json", RouteContractModel),
        ("api_contracts.json", ApiContractModel),
    ]

    for fname, model in checks:
        try:
            items = _load_json(contracts_dir / fname)
            for i, item in enumerate(items):
                model.model_validate(item)
        except (ValidationError, Exception) as exc:
            _record(findings, fname, str(exc))

    try:
        GateMatrixModel.model_validate(_load_json(contracts_dir / "gate_matrix.json"))
    except (ValidationError, Exception) as exc:
        _record(findings, "gate_matrix.json", str(exc))

    try:
        CheckpointPolicyModel.model_validate(_load_json(contracts_dir / "checkpoint_policy.json"))
    except (ValidationError, Exception) as exc:
        _record(findings, "checkpoint_policy.json", str(exc))

    try:
        SeedSchemaManifestModel.model_validate(_load_json(contracts_dir / "seed_schema_manifest.json"))
    except (ValidationError, Exception) as exc:
        _record(findings, "seed_schema_manifest.json", str(exc))

    optional = [
        ("canonical_authority.json", validate_canonical_authority),
        ("ownership_contracts.json", validate_file_ownership_map),
        ("task_graph_contracts.json", validate_task_graph),
    ]
    for fname, fn in optional:
        p = contracts_dir / fname
        if p.exists():
            findings.extend(fn(_load_json(p)))
    return findings
