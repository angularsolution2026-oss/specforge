from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .utils import read_text


class RouteContractModel(BaseModel):
    route: str
    source: str
    priority: str = ""
    sprint: str = ""


class ApiContractModel(BaseModel):
    endpoint: str
    method: str
    source: str


class GateMatrixModel(BaseModel):
    generated_at: str
    source: str
    tiers_detected: list[str]


class CheckpointPolicyModel(BaseModel):
    generated_at: str
    source: str
    tasks: dict[str, dict[str, Any]]


class SeedSchemaManifestModel(BaseModel):
    generated_at: str
    source: str
    is_demo_rules_present: bool
    seed_files: list[str]


def _load_json(path: Path) -> Any:
    import json

    return json.loads(read_text(path))


def validate_contract_bundle(contracts_dir: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def record_error(file: str, err: str) -> None:
        findings.append({"severity": "FAIL", "check": "pydantic_validation", "file": file, "message": err})

    try:
        routes = _load_json(contracts_dir / "route_contracts.json")
        for item in routes:
            RouteContractModel.model_validate(item)
    except (ValidationError, Exception) as exc:
        record_error("route_contracts.json", str(exc))

    try:
        apis = _load_json(contracts_dir / "api_contracts.json")
        for item in apis:
            ApiContractModel.model_validate(item)
    except (ValidationError, Exception) as exc:
        record_error("api_contracts.json", str(exc))

    try:
        GateMatrixModel.model_validate(_load_json(contracts_dir / "gate_matrix.json"))
    except (ValidationError, Exception) as exc:
        record_error("gate_matrix.json", str(exc))

    try:
        CheckpointPolicyModel.model_validate(_load_json(contracts_dir / "checkpoint_policy.json"))
    except (ValidationError, Exception) as exc:
        record_error("checkpoint_policy.json", str(exc))

    try:
        SeedSchemaManifestModel.model_validate(_load_json(contracts_dir / "seed_schema_manifest.json"))
    except (ValidationError, Exception) as exc:
        record_error("seed_schema_manifest.json", str(exc))

    return findings
