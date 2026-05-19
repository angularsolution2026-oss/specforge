from __future__ import annotations

import json
import re
from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..utils import extract_table_routes, extract_tree_routes, now_iso, read_text, write_json
from ..validators import validate_contract_bundle


def _load_json(path: Path) -> object:
    return json.loads(read_text(path))


def cmd_lint(args: Namespace) -> int:
    paths = resolve_paths(Path(args.repo_root))
    ensure_out_dirs(paths)
    findings: list[dict] = []

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
            findings.append({"severity": "FAIL", "check": "missing_contract", "file": name})

    if not findings:
        routes = _load_json(paths.contracts_dir / "route_contracts.json")
        apis = _load_json(paths.contracts_dir / "api_contracts.json")
        checkpoints = _load_json(paths.contracts_dir / "checkpoint_policy.json")
        enum_registry = _load_json(paths.contracts_dir / "enum_registry.json")
        seed_manifest = _load_json(paths.contracts_dir / "seed_schema_manifest.json")

        findings.extend(validate_contract_bundle(paths.contracts_dir))

        route_values = [r.get("route", "") for r in routes if isinstance(r, dict)]
        dupes = sorted({x for x in route_values if route_values.count(x) > 1})
        for d in dupes:
            findings.append({"severity": "WARN", "check": "duplicate_route", "value": d})

        api_values = [f"{x.get('method','')} {x.get('endpoint','')}" for x in apis if isinstance(x, dict)]
        if not api_values:
            findings.append({"severity": "WARN", "check": "api_contract_empty"})

        if isinstance(checkpoints, dict):
            tasks = checkpoints.get("tasks", {})
            if "P0-000" not in tasks:
                findings.append({"severity": "WARN", "check": "missing_p0_checkpoint_policy"})

        # cross-reference route drift against IA/spec routes
        spec06 = paths.repo_root / "docs/spec/06-app-router-structure.md"
        ia = paths.repo_root / "docs/spec/website-structure.md"
        source_routes: set[str] = set()
        for p in (spec06, ia):
            if p.exists():
                txt = read_text(p)
                source_routes.update(extract_table_routes(txt))
                source_routes.update(extract_tree_routes(txt))
        source_routes = {
            r
            for r in source_routes
            if r.startswith("/")
            and "/page" not in r
            and not r.startswith("/api")
            and "?" not in r
            and not re.search(r"[A-Z]", r)
            and not any(tok in r for tok in ("/App", "/Swagger", "/Broker", "/batch"))
        }
        contract_routes = {r.rstrip("/") or "/" for r in route_values if r}
        vocab: set[str] = set()
        for cr in contract_routes:
            for seg in cr.strip("/").split("/"):
                if not seg:
                    continue
                if seg.startswith("[") and seg.endswith("]"):
                    continue
                vocab.add(seg)

        def plausible(route: str) -> bool:
            segs = [s for s in route.strip("/").split("/") if s]
            if not segs:
                return True
            for s in segs:
                if s.startswith("[") and s.endswith("]"):
                    continue
                if s not in vocab:
                    return False
            return True

        source_routes = {r for r in source_routes if plausible(r)}
        ignored_roots = {"/admin", "/portals", "/broker", "/api"}

        def is_container_root(route: str) -> bool:
            if route in ignored_roots:
                return True
            return any(cr.startswith(route + "/") for cr in contract_routes)

        missing_in_contracts = sorted(
            r for r in source_routes if r and r not in contract_routes and not is_container_root(r)
        )
        if missing_in_contracts:
            findings.append(
                {
                    "severity": "WARN",
                    "check": "route_drift_missing_in_contracts",
                    "count": len(missing_in_contracts),
                    "sample": ", ".join(missing_in_contracts[:8]),
                }
            )

        # API drift from spec text
        spec_text = ""
        for p in (spec06, paths.repo_root / "docs/spec/00-master-instruction.md"):
            if p.exists():
                spec_text += "\n" + read_text(p)
        spec_api = set(re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/api/[a-zA-Z0-9_/\-\[\]]+)", spec_text))
        contract_api = {(x.get("method", ""), x.get("endpoint", "")) for x in apis if isinstance(x, dict)}
        missing_api = sorted(spec_api - contract_api)
        if missing_api:
            findings.append(
                {
                    "severity": "WARN",
                    "check": "api_drift_missing_in_contracts",
                    "count": len(missing_api),
                    "sample": ", ".join([f"{m} {e}" for m, e in missing_api[:6]]),
                }
            )

        # enum registry sanity
        if isinstance(enum_registry, dict) and not enum_registry:
            findings.append({"severity": "WARN", "check": "enum_registry_empty"})

        # seed integrity checks
        seeds_dir = paths.repo_root / "data/seeds"
        declared = set(seed_manifest.get("seed_files", [])) if isinstance(seed_manifest, dict) else set()
        actual = {p.name for p in seeds_dir.glob("*.json")} if seeds_dir.exists() else set()
        if declared != actual:
            findings.append(
                {
                    "severity": "WARN",
                    "check": "seed_manifest_drift",
                    "declared_only": ", ".join(sorted(declared - actual)) or "-",
                    "actual_only": ", ".join(sorted(actual - declared)) or "-",
                }
            )

        inv = seeds_dir / "inventory-lots.demo.json"
        if inv.exists():
            try:
                data = _load_json(inv)
                statuses = sorted({x.get("status", "") for x in data.get("inventory_lots", []) if isinstance(x, dict)})
                allowed = {"available", "holding", "deposited", "sold", "hidden"}
                unknown = [s for s in statuses if s and s not in allowed]
                if unknown:
                    findings.append(
                        {
                            "severity": "WARN",
                            "check": "seed_enum_mismatch_inventory_status",
                            "values": ", ".join(unknown),
                        }
                    )
            except Exception as exc:
                findings.append({"severity": "WARN", "check": "seed_parse_error", "file": "inventory-lots.demo.json", "error": str(exc)})

    status = "PASS"
    if any(f["severity"] == "FAIL" for f in findings):
        status = "FAIL"
    elif findings:
        status = "WARN"

    report = {"generated_at": now_iso(), "status": status, "findings": findings}
    out = paths.contracts_dir / "lint_report.json"
    write_json(out, report)
    print(f"STATUS={status}")
    print(f"FINDINGS={len(findings)}")
    print(f"WROTE={out}")
    if status == "FAIL":
        return 1
    if getattr(args, "strict", False) and findings:
        return 1
    return 0
