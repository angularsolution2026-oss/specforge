from __future__ import annotations

import json
import re
from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..models import ApiContract, CanonicalAuthority, FileOwnershipMap, RouteContract, TaskGraph, to_json
from ..utils import extract_routes, now_iso, read_text, write_json


def _parse_route_rows(text: str, source: str) -> list[RouteContract]:
    routes: list[RouteContract] = []
    for line in text.splitlines():
        if "|" not in line or "---" in line:
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        route = ""
        for c in cells:
            if c == "/":
                route = "/"
                break
            for m in re.findall(r"/[a-zA-Z0-9\-\[\]/]+", c):
                route = m
                break
            if route:
                break
        if not route:
            continue
        priority = ""
        sprint = ""
        for c in cells:
            if c.startswith("P") and len(c) <= 3:
                priority = c
            if "1A" in c or "1B" in c or c == "2":
                sprint = c
        routes.append(RouteContract(route=route, source=source, priority=priority, sprint=sprint))
    return routes


def _parse_api_contracts(text: str, source: str) -> list[ApiContract]:
    out: list[ApiContract] = []
    for method, endpoint in re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/api/[a-zA-Z0-9_/\-\[\]]+)", text):
        out.append(ApiContract(method=method, endpoint=endpoint, source=source))
    return out


def _canon_route(route: str) -> str:
    route = route.strip()
    if route != "/" and route.endswith("/"):
        route = route[:-1]
    return route


def _try_load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    return json.loads(read_text(path))


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _route_parse_diagnostics(text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    candidates = [ln for ln in lines if "/" in ln and "http://" not in ln.lower() and "https://" not in ln.lower()]
    recognized = extract_routes(text)
    unknown: list[str] = []
    for ln in candidates:
        if not any(r in ln for r in recognized):
            unknown.append(ln[:120])
    candidate_count = len(candidates)
    recognized_count = len(recognized)
    confidence = 1.0 if candidate_count == 0 else max(0.0, min(1.0, recognized_count / candidate_count))
    return {
        "candidate_count": candidate_count,
        "recognized_count": recognized_count,
        "unknown_fragments": unknown[:20],
        "confidence": round(confidence, 3),
    }


def cmd_normalize(args: Namespace) -> int:
    out_root = Path(args.out_root) if getattr(args, "out_root", None) else None
    paths = resolve_paths(Path(args.repo_root), out_root=out_root)
    ensure_out_dirs(paths)
    warnings: list[str] = []

    spec00 = paths.repo_root / "docs/spec/00-master-instruction.md"
    spec06 = paths.repo_root / "docs/spec/06-app-router-structure.md"
    ia = paths.repo_root / "docs/spec/website-structure.md"
    gates = paths.repo_root / ".ai/core/quality-gates.md"
    checkpoints = paths.repo_root / ".ai/state/checkpoints.json"
    seed_readme = paths.repo_root / "data/seeds/README.md"

    route_contracts: list[RouteContract] = []
    api_contracts: list[ApiContract] = []
    enum_registry: dict[str, list[str]] = {}

    for p in (spec00, spec06, ia):
        if not p.exists():
            continue
        txt = read_text(p)
        route_contracts.extend(_parse_route_rows(txt, str(p.relative_to(paths.repo_root)).replace("\\", "/")))
        api_contracts.extend(_parse_api_contracts(txt, str(p.relative_to(paths.repo_root)).replace("\\", "/")))

    ia_routes = []
    parser_diagnostics = {"generated_at": now_iso(), "source": "docs/spec/website-structure.md", "candidate_count": 0, "recognized_count": 0, "unknown_fragments": [], "confidence": 1.0}
    if ia.exists():
        ia_text = read_text(ia)
        ia_routes = extract_routes(ia_text)
        parser_diagnostics = {"generated_at": now_iso(), "source": "docs/spec/website-structure.md", **_route_parse_diagnostics(ia_text)}
    known = {r.route for r in route_contracts}
    for r in ia_routes:
        r = r.strip().strip("`").split(",")[0].strip()
        if any(ch.isspace() for ch in r):
            continue
        if not r.startswith("/"):
            continue
        if r.startswith("/api/"):
            continue
        if r not in known:
            route_contracts.append(RouteContract(route=r, source="docs/spec/website-structure.md"))

    schema_path = paths.repo_root / "docs/spec/05-database-schema.md"
    if schema_path.exists():
        txt = read_text(schema_path)
        enum_keys = sorted(set(re.findall(r"`([a-z_]+)`\s*\|\s*enum", txt, flags=re.I)))
        for k in enum_keys:
            enum_registry[k] = []

    gate_matrix = {"generated_at": now_iso(), "source": ".ai/core/quality-gates.md", "tiers_detected": []}
    if gates.exists():
        gtxt = read_text(gates)
        gate_matrix["tiers_detected"] = sorted(set(re.findall(r"Tier\s+([0-9A-Z\-]+)", gtxt)))

    checkpoint_policy = {"generated_at": now_iso(), "source": ".ai/state/checkpoints.json", "tasks": {}}
    if checkpoints.exists():
        checkpoint_policy["tasks"] = json.loads(read_text(checkpoints)).get("tasks", {})

    seed_schema_manifest = {
        "generated_at": now_iso(),
        "source": "data/seeds",
        "is_demo_rules_present": bool(seed_readme.exists() and "demo" in read_text(seed_readme).lower()),
        "seed_files": [],
    }
    for p in sorted((paths.repo_root / "data/seeds").glob("*.json")):
        seed_schema_manifest["seed_files"].append(p.name)

    dedup_routes: dict[str, RouteContract] = {}
    for r in route_contracts:
        key = _canon_route(r.route)
        dedup_routes.setdefault(key, RouteContract(route=key, source=r.source, priority=r.priority, sprint=r.sprint))
    route_contracts = sorted(dedup_routes.values(), key=lambda x: x.route)

    dedup_apis: dict[tuple[str, str], ApiContract] = {}
    for a in api_contracts:
        dedup_apis.setdefault((a.method, a.endpoint), a)
    api_contracts = sorted(dedup_apis.values(), key=lambda x: (x.method, x.endpoint))

    write_json(paths.contracts_dir / "route_contracts.json", to_json(route_contracts))
    write_json(paths.contracts_dir / "api_contracts.json", to_json(api_contracts))
    write_json(paths.contracts_dir / "enum_registry.json", enum_registry)
    write_json(paths.contracts_dir / "gate_matrix.json", gate_matrix)
    write_json(paths.contracts_dir / "checkpoint_policy.json", checkpoint_policy)
    write_json(paths.contracts_dir / "seed_schema_manifest.json", seed_schema_manifest)
    write_json(paths.contracts_dir / "parser_diagnostics.json", parser_diagnostics)

    ca_path = paths.repo_root / ".ai/registry/CANONICAL_AUTHORITY.json"
    own_path = paths.repo_root / ".ai/registry/FILE_OWNERSHIP_MAP.json"
    tg_path = paths.repo_root / ".ai/tasks/TASK_GRAPH.json"

    canonical = _try_load_json(ca_path)
    if canonical is not None:
        ca_model = CanonicalAuthority.model_validate(canonical)
        write_json(paths.contracts_dir / "canonical_authority.json", ca_model.model_dump())
    else:
        _remove_if_exists(paths.contracts_dir / "canonical_authority.json")
        warnings.append("CANONICAL_AUTHORITY.json missing")

    ownership = _try_load_json(own_path)
    if ownership is not None:
        own_model = FileOwnershipMap.model_validate(ownership)
        write_json(paths.contracts_dir / "ownership_contracts.json", own_model.model_dump())
    else:
        _remove_if_exists(paths.contracts_dir / "ownership_contracts.json")
        warnings.append("FILE_OWNERSHIP_MAP.json missing")

    task_graph = _try_load_json(tg_path)
    if task_graph is not None:
        tg_model = TaskGraph.model_validate(task_graph)
        write_json(paths.contracts_dir / "task_graph_contracts.json", tg_model.model_dump())
    else:
        _remove_if_exists(paths.contracts_dir / "task_graph_contracts.json")
        warnings.append("TASK_GRAPH.json missing")

    print(f"WROTE_DIR={paths.contracts_dir}")
    print(f"ROUTES={len(route_contracts)} APIS={len(api_contracts)} ENUM_KEYS={len(enum_registry)}")
    if warnings:
        print(f"WARNINGS={len(warnings)}")
        for w in warnings:
            print(f"WARN={w}")
    return 0
