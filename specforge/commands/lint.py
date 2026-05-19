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


def _add(findings: list[dict], severity: str, check: str, message: str, **extra: object) -> None:
    payload = {"severity": severity, "check": check, "message": message}
    payload.update(extra)
    findings.append(payload)


def _standalone_strict_hint(check: str) -> str:
    hints = {
        "canonical_authority_missing": "Create .ai/registry/CANONICAL_AUTHORITY.json in target repo, or run non-strict mode for standalone smoke tests.",
        "ownership_contract_missing": "Create .ai/registry/FILE_OWNERSHIP_MAP.json in target repo, or run non-strict mode for standalone smoke tests.",
        "task_graph_json_missing": "Create .ai/tasks/TASK_GRAPH.json in target repo, or run non-strict mode for standalone smoke tests.",
    }
    return hints.get(check, "")


def cmd_lint(args: Namespace) -> int:
    paths = resolve_paths(Path(args.repo_root))
    ensure_out_dirs(paths)
    strict = bool(getattr(args, "strict", False))
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
            _add(findings, "FAIL", "missing_contract", f"Missing required contract: {name}", file=name)

    if not findings:
        findings.extend(validate_contract_bundle(paths.contracts_dir))

        routes = _load_json(paths.contracts_dir / "route_contracts.json")
        apis = _load_json(paths.contracts_dir / "api_contracts.json")
        checkpoints = _load_json(paths.contracts_dir / "checkpoint_policy.json")
        seed_manifest = _load_json(paths.contracts_dir / "seed_schema_manifest.json")

        ca = paths.contracts_dir / "canonical_authority.json"
        own = paths.contracts_dir / "ownership_contracts.json"
        tg = paths.contracts_dir / "task_graph_contracts.json"

        if not ca.exists():
            sev = "FAIL" if strict else "WARN"
            msg = "Strict governance files are missing. This is expected for standalone specforge tool repo, but must be fixed in a governed target repo."
            _add(findings, sev, "canonical_authority_missing", msg, hint=_standalone_strict_hint("canonical_authority_missing"))
        else:
            ca_json = _load_json(ca)
            canonical_root = ca_json.get("canonical_spec_root", "") if isinstance(ca_json, dict) else ""
            if canonical_root and canonical_root != "FINAL_SPEC":
                _add(
                    findings,
                    "WARN",
                    "deprecated_spec_root_used_as_authority",
                    f"canonical_spec_root is '{canonical_root}', expected FINAL_SPEC",
                )

        if not own.exists():
            sev = "FAIL" if strict else "WARN"
            msg = "Strict governance files are missing. This is expected for standalone specforge tool repo, but must be fixed in a governed target repo."
            _add(findings, sev, "ownership_contract_missing", msg, hint=_standalone_strict_hint("ownership_contract_missing"))

        if not tg.exists():
            sev = "FAIL" if strict else "WARN"
            msg = "Strict governance files are missing. This is expected for standalone specforge tool repo, but must be fixed in a governed target repo."
            _add(findings, sev, "task_graph_json_missing", msg, hint=_standalone_strict_hint("task_graph_json_missing"))
        else:
            tg_json = _load_json(tg)
            tasks = tg_json.get("tasks", []) if isinstance(tg_json, dict) else []
            task_ids = {t.get("task_id", "") for t in tasks if isinstance(t, dict)}
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                tid = t.get("task_id", "")
                deps = t.get("dependencies", [])
                for dep in deps:
                    if dep not in task_ids:
                        _add(
                            findings,
                            "FAIL" if strict else "WARN",
                            "task_graph_dependency_unknown",
                            f"Task {tid} depends on unknown task {dep}",
                            task_id=tid,
                            dependency=dep,
                        )
                allowed = set(t.get("allowed_files", []))
                forbidden = set(t.get("forbidden_files", []))
                overlap = sorted(allowed & forbidden)
                if overlap:
                    _add(
                        findings,
                        "FAIL",
                        "task_allowed_file_conflicts_with_forbidden_file",
                        f"Task {tid} has allowed/forbidden overlap",
                        task_id=tid,
                        overlap=overlap,
                    )
                if not t.get("checkpoint_required"):
                    _add(
                        findings,
                        "WARN",
                        "checkpoint_policy_missing_for_task",
                        f"Task {tid} missing checkpoint_required",
                        task_id=tid,
                    )

            # parallel overlap check (same dependency-set implies parallel bucket)
            buckets: dict[str, list[dict]] = {}
            for t in tasks:
                deps = tuple(sorted(t.get("dependencies", []))) if isinstance(t, dict) else tuple()
                buckets.setdefault("|".join(deps), []).append(t)
            for _, bucket in buckets.items():
                for i in range(len(bucket)):
                    for j in range(i + 1, len(bucket)):
                        ti = bucket[i]
                        tj = bucket[j]
                        ai = set(ti.get("allowed_files", []))
                        aj = set(tj.get("allowed_files", []))
                        overlap = sorted(ai & aj)
                        if overlap:
                            _add(
                                findings,
                                "WARN",
                                "task_allowed_files_overlap_between_parallel_tasks",
                                f"Parallel tasks {ti.get('task_id')} and {tj.get('task_id')} share allowed files",
                                overlap=overlap[:10],
                            )

        if isinstance(seed_manifest, dict):
            is_demo_guard = bool(seed_manifest.get("is_demo_rules_present"))
            seed_files = seed_manifest.get("seed_files", [])
            uses_demo = any(".demo." in f or f.endswith(".demo.json") for f in seed_files)
            if uses_demo and not is_demo_guard:
                _add(
                    findings,
                    "WARN",
                    "seed_demo_file_used_without_demo_guard",
                    "Demo seed file present but demo guard is not detected",
                )

        # streamlit README path check
        readme = paths.app_root / "README.md"
        wrapper_root = paths.app_root / "streamlit_wrapper.py"
        wrapper_pkg = paths.app_root / "specforge" / "streamlit_wrapper.py"
        if readme.exists():
            text = read_text(readme)
            mentions_pkg = "streamlit run specforge/streamlit_wrapper.py" in text
            mentions_root = "streamlit run streamlit_wrapper.py" in text
            mismatch = (mentions_pkg and not wrapper_pkg.exists()) or (mentions_root and not wrapper_root.exists())
            if mismatch:
                _add(
                    findings,
                    "FAIL",
                    "streamlit_readme_path_mismatch",
                    "README Streamlit command does not match wrapper file location",
                )

        route_values = [r.get("route", "") for r in routes if isinstance(r, dict)]
        dupes = sorted({x for x in route_values if route_values.count(x) > 1})
        for d in dupes:
            _add(findings, "WARN", "duplicate_route", f"Duplicate route {d}", value=d)

        api_values = [f"{x.get('method','')} {x.get('endpoint','')}" for x in apis if isinstance(x, dict)]
        if not api_values:
            _add(findings, "WARN", "api_contract_empty", "No API contracts found")

        if isinstance(checkpoints, dict):
            tasks = checkpoints.get("tasks", {})
            if "P0-000" not in tasks:
                _add(findings, "WARN", "missing_p0_checkpoint_policy", "Missing P0-000 checkpoint policy")

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
                if r.startswith("/")
                and not r.startswith("/api")
                and "/page" not in r
                and " " not in r
                and "http" not in r.lower()
            }
            contract_routes = {r.get("route", "") for r in routes if isinstance(r, dict)}
            missing_routes = sorted(r for r in source_routes if r not in contract_routes)
            if missing_routes:
                _add(
                    findings,
                    "WARN",
                    "route_drift_missing_in_contracts",
                    "Source routes missing in route_contracts.json",
                    count=len(missing_routes),
                    sample=missing_routes[:10],
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
                _add(
                    findings,
                    "WARN",
                    "api_drift_missing_in_contracts",
                    "Source APIs missing in api_contracts.json",
                    count=len(missing_apis),
                    sample=[f"{m} {e}" for m, e in missing_apis[:10]],
                )

        enum_registry = _load_json(paths.contracts_dir / "enum_registry.json")
        if isinstance(enum_registry, dict) and not enum_registry:
            _add(findings, "WARN", "enum_registry_empty", "enum_registry.json is empty")

        inv_demo = paths.repo_root / "data/seeds/inventory-lots.demo.json"
        if inv_demo.exists():
            try:
                inv = _load_json(inv_demo)
                lots = inv.get("inventory_lots", []) if isinstance(inv, dict) else []
                statuses = {x.get("status", "") for x in lots if isinstance(x, dict)}
                allowed_status = {"available", "holding", "deposited", "sold", "hidden"}
                unknown = sorted(s for s in statuses if s and s not in allowed_status)
                if unknown:
                    _add(
                        findings,
                        "WARN",
                        "seed_enum_mismatch_inventory_status",
                        "inventory_lots.demo has unknown status values",
                        values=unknown,
                    )
            except Exception as exc:
                _add(findings, "WARN", "seed_enum_mismatch_inventory_status", f"Failed parsing seed file: {exc}")

    has_fail = any(f["severity"] == "FAIL" for f in findings)
    has_warn = any(f["severity"] == "WARN" for f in findings)
    status = "FAIL" if has_fail else ("WARN" if has_warn else "PASS")

    report = {"generated_at": now_iso(), "status": status, "strict": strict, "findings": findings}
    out = paths.contracts_dir / "lint_report.json"
    write_json(out, report)
    print(f"STATUS={status}")
    print(f"FINDINGS={len(findings)}")
    print(f"WROTE={out}")
    return 1 if has_fail else 0
