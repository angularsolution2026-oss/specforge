from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .utils import extract_table_routes, extract_tree_routes, read_text
from .validators import validate_contract_bundle


def load_json(path: Path) -> Any:
    return json.loads(read_text(path))


def add_finding(
    findings: list[dict[str, Any]],
    *,
    severity: str,
    check: str,
    message: str,
    profile: str,
    rule_group: str,
    hint: str = "",
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "severity": severity,
        "check": check,
        "message": message,
        "profile": profile,
        "rule_group": rule_group,
    }
    if hint:
        payload["hint"] = hint
    payload.update(extra)
    findings.append(payload)


def run_core_rules(paths, findings: list[dict[str, Any]], profile: str) -> bool:
    required = [
        "route_contracts.json",
        "api_contracts.json",
        "enum_registry.json",
        "gate_matrix.json",
        "checkpoint_policy.json",
        "seed_schema_manifest.json",
    ]
    for name in required:
        p = paths.contracts_dir / name
        if not p.exists():
            add_finding(
                findings,
                severity="FAIL",
                check="missing_contract",
                message=f"Missing required contract: {name}",
                file=name,
                profile=profile,
                rule_group="core",
            )

    if findings:
        return False

    findings.extend(validate_contract_bundle(paths.contracts_dir))
    for f in findings:
        if "rule_group" not in f:
            f["rule_group"] = "core"
            f["profile"] = profile

    routes = load_json(paths.contracts_dir / "route_contracts.json")
    apis = load_json(paths.contracts_dir / "api_contracts.json")

    route_values = [r.get("route", "") for r in routes if isinstance(r, dict)]
    dupes = sorted({x for x in route_values if route_values.count(x) > 1})
    for d in dupes:
        add_finding(findings, severity="WARN", check="duplicate_route", message=f"Duplicate route {d}", value=d, profile=profile, rule_group="core")

    api_values = [f"{x.get('method','')} {x.get('endpoint','')}" for x in apis if isinstance(x, dict)]
    if not api_values:
        add_finding(findings, severity="WARN", check="api_contract_empty", message="No API contracts found", profile=profile, rule_group="core")

    spec06 = paths.repo_root / "docs/spec/06-app-router-structure.md"
    website = paths.repo_root / "docs/spec/website-structure.md"
    if spec06.exists() or website.exists():
        source_routes: set[str] = set()
        for p in (spec06, website):
            if not p.exists():
                continue
            txt = read_text(p)
            source_routes.update(extract_table_routes(txt))
            source_routes.update(extract_tree_routes(txt))
        source_routes = {
            r
            for r in source_routes
            if r.startswith("/") and not r.startswith("/api") and "/page" not in r and " " not in r and "http" not in r.lower()
        }
        contract_routes = {r.get("route", "") for r in routes if isinstance(r, dict)}
        missing_routes = sorted(r for r in source_routes if r not in contract_routes)
        if missing_routes:
            add_finding(
                findings,
                severity="WARN",
                check="route_drift_missing_in_contracts",
                message="Source routes missing in route_contracts.json",
                count=len(missing_routes),
                sample=missing_routes[:10],
                profile=profile,
                rule_group="core",
            )

    spec00 = paths.repo_root / "docs/spec/00-master-instruction.md"
    api_source_text = ""
    for p in (spec06, spec00):
        if p.exists():
            api_source_text += "\n" + read_text(p)
    if api_source_text.strip():
        source_apis = set(re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/api/[a-zA-Z0-9_/\-\[\]]+)", api_source_text))
        contract_apis = {(a.get("method", ""), a.get("endpoint", "")) for a in apis if isinstance(a, dict)}
        missing_apis = sorted(source_apis - contract_apis)
        if missing_apis:
            add_finding(
                findings,
                severity="WARN",
                check="api_drift_missing_in_contracts",
                message="Source APIs missing in api_contracts.json",
                count=len(missing_apis),
                sample=[f"{m} {e}" for m, e in missing_apis[:10]],
                profile=profile,
                rule_group="core",
            )

    enum_registry = load_json(paths.contracts_dir / "enum_registry.json")
    if isinstance(enum_registry, dict) and not enum_registry:
        add_finding(findings, severity="WARN", check="enum_registry_empty", message="enum_registry.json is empty", profile=profile, rule_group="core")
    parser_diag = paths.contracts_dir / "parser_diagnostics.json"
    if parser_diag.exists():
        diag = load_json(parser_diag)
        confidence = float(diag.get("confidence", 1.0)) if isinstance(diag, dict) else 1.0
        if confidence < 0.7:
            add_finding(
                findings,
                severity="WARN",
                check="parser_confidence_low",
                message="Route parser confidence is low; review unknown_fragments in parser_diagnostics.json",
                confidence=confidence,
                profile=profile,
                rule_group="core",
            )
    return True


def run_governed_rules(paths, findings: list[dict[str, Any]], profile: str, strict: bool) -> None:
    ca = paths.contracts_dir / "canonical_authority.json"
    own = paths.contracts_dir / "ownership_contracts.json"
    tg = paths.contracts_dir / "task_graph_contracts.json"
    sev_missing = "FAIL" if strict else "WARN"
    msg = "Governed profile requires governance contracts from target repository."
    for p, check in (
        (ca, "canonical_authority_missing"),
        (own, "ownership_contract_missing"),
        (tg, "task_graph_json_missing"),
    ):
        if not p.exists():
            add_finding(findings, severity=sev_missing, check=check, message=msg, profile=profile, rule_group="governed")

    if tg.exists():
        tg_json = load_json(tg)
        tasks = tg_json.get("tasks", []) if isinstance(tg_json, dict) else []
        task_ids = {t.get("task_id", "") for t in tasks if isinstance(t, dict)}
        for t in tasks:
            if not isinstance(t, dict):
                continue
            tid = t.get("task_id", "")
            for dep in t.get("dependencies", []):
                if dep not in task_ids:
                    add_finding(
                        findings,
                        severity="FAIL" if strict else "WARN",
                        check="task_graph_dependency_unknown",
                        message=f"Task {tid} depends on unknown task {dep}",
                        task_id=tid,
                        dependency=dep,
                        profile=profile,
                        rule_group="governed",
                    )
            allowed = set(t.get("allowed_files", []))
            forbidden = set(t.get("forbidden_files", []))
            overlap = sorted(allowed & forbidden)
            if overlap:
                add_finding(
                    findings,
                    severity="FAIL",
                    check="task_allowed_file_conflicts_with_forbidden_file",
                    message=f"Task {tid} has allowed/forbidden overlap",
                    task_id=tid,
                    overlap=overlap,
                    profile=profile,
                    rule_group="governed",
                )
            if not t.get("checkpoint_required"):
                add_finding(
                    findings,
                    severity="WARN",
                    check="checkpoint_policy_missing_for_task",
                    message=f"Task {tid} missing checkpoint_required",
                    task_id=tid,
                    profile=profile,
                    rule_group="governed",
                )


def run_project_rules(paths, findings: list[dict[str, Any]], profile: str) -> None:
    checkpoints = load_json(paths.contracts_dir / "checkpoint_policy.json")
    if isinstance(checkpoints, dict):
        tasks = checkpoints.get("tasks", {})
        if "P0-000" not in tasks:
            add_finding(findings, severity="WARN", check="missing_p0_checkpoint_policy", message="Missing P0-000 checkpoint policy", profile=profile, rule_group="project")

    readme = paths.app_root / "README.md"
    wrapper_root = paths.app_root / "streamlit_wrapper.py"
    wrapper_pkg = paths.app_root / "specforge" / "streamlit_wrapper.py"
    if readme.exists():
        text = read_text(readme)
        mentions_pkg = "streamlit run specforge/streamlit_wrapper.py" in text
        mentions_root = "streamlit run streamlit_wrapper.py" in text
        mismatch = (mentions_pkg and not wrapper_pkg.exists()) or (mentions_root and not wrapper_root.exists())
        if mismatch:
            add_finding(
                findings,
                severity="FAIL",
                check="streamlit_readme_path_mismatch",
                message="README Streamlit command does not match wrapper file location",
                profile=profile,
                rule_group="project",
            )

    inv_demo = paths.repo_root / "data/seeds/inventory-lots.demo.json"
    if inv_demo.exists():
        try:
            inv = load_json(inv_demo)
            lots = inv.get("inventory_lots", []) if isinstance(inv, dict) else []
            statuses = {x.get("status", "") for x in lots if isinstance(x, dict)}
            allowed_status = {"available", "holding", "deposited", "sold", "hidden"}
            unknown = sorted(s for s in statuses if s and s not in allowed_status)
            if unknown:
                add_finding(
                    findings,
                    severity="WARN",
                    check="seed_enum_mismatch_inventory_status",
                    message="inventory_lots.demo has unknown status values",
                    values=unknown,
                    profile=profile,
                    rule_group="project",
                )
        except Exception as exc:
            add_finding(
                findings,
                severity="WARN",
                check="seed_enum_mismatch_inventory_status",
                message=f"Failed parsing seed file: {exc}",
                profile=profile,
                rule_group="project",
            )
