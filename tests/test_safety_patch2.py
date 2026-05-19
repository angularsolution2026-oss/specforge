import json
from argparse import Namespace
from pathlib import Path

from specforge.commands import lint as lint_mod
from specforge.commands.normalize import cmd_normalize
from specforge.commands.reconcile import evaluate_evidence
from specforge.commands.run import checkpoint_is_approved, evaluate_runtime_preflight
from specforge.config import AppPaths, resolve_paths
from specforge.utils import extract_routes
from specforge.utils import read_text, write_json


def _base_packet(status):
    return {
        "task_id": "P0-000",
        "lane_id": "A",
        "checkpoint_required": "CP-0",
        "checkpoint_status": status,
        "allowed_files": ["specforge/commands/run.py"],
        "forbidden_files": [],
    }


def test_run_execute_blocks_missing_checkpoint():
    pre = evaluate_runtime_preflight([_base_packet("")], lint_status="PASS", denied_patterns=[], mode="execute")
    assert pre["checkpoint_ok"] is False
    assert pre["checkpoint_failures"]
    assert "checkpoint not approved" in pre["blockers"]


def test_run_execute_blocks_pending_checkpoint():
    pre = evaluate_runtime_preflight([_base_packet("pending")], lint_status="PASS", denied_patterns=[], mode="execute")
    assert pre["checkpoint_ok"] is False
    assert "checkpoint not approved" in pre["blockers"]


def test_run_execute_allows_approved_checkpoint_preflight():
    pre = evaluate_runtime_preflight([_base_packet("approved")], lint_status="PASS", denied_patterns=[], mode="execute")
    assert checkpoint_is_approved("CP-0", "approved") is True
    assert pre["checkpoint_ok"] is True
    assert "checkpoint not approved" not in pre["blockers"]


def test_reconcile_random_evidence_is_insufficient(tmp_path: Path):
    ev = tmp_path / ".ai/evidence/P0-000"
    ev.mkdir(parents=True)
    (ev / "random.txt").write_text("x", encoding="utf-8")
    result = evaluate_evidence(ev)
    assert result["sufficient"] is False
    assert len(result["missing"]) >= 1


def test_reconcile_structured_evidence_is_sufficient(tmp_path: Path):
    ev = tmp_path / ".ai/evidence/P0-000"
    ev.mkdir(parents=True)
    (ev / "manifest.json").write_text("{}", encoding="utf-8")
    (ev / "quality-gates.json").write_text("{}", encoding="utf-8")
    (ev / "command-log.txt").write_text("ok", encoding="utf-8")
    (ev / "git-diff.patch").write_text("diff", encoding="utf-8")
    result = evaluate_evidence(ev)
    assert result["sufficient"] is True
    assert result["missing"] == []
    assert result["invalid"] == []


def test_reconcile_invalid_manifest_is_not_sufficient(tmp_path: Path):
    ev = tmp_path / ".ai/evidence/P0-000"
    ev.mkdir(parents=True)
    (ev / "manifest.json").write_text("{bad", encoding="utf-8")
    (ev / "quality-gates.json").write_text("{}", encoding="utf-8")
    (ev / "command-log.txt").write_text("ok", encoding="utf-8")
    (ev / "git-diff.patch").write_text("diff", encoding="utf-8")
    result = evaluate_evidence(ev)
    assert result["sufficient"] is False
    assert "manifest.json" in result["invalid"]


def test_reconcile_empty_manifest_is_weak(tmp_path: Path):
    ev = tmp_path / ".ai/evidence/P0-000"
    ev.mkdir(parents=True)
    (ev / "manifest.json").write_text("{}", encoding="utf-8")
    (ev / "quality-gates.json").write_text('{"status":"PASS"}', encoding="utf-8")
    (ev / "command-log.txt").write_text("ran", encoding="utf-8")
    (ev / "git-diff.patch").write_text("diff", encoding="utf-8")
    result = evaluate_evidence(ev)
    assert result["sufficient"] is True
    assert "manifest.json:empty_object" in result["weak"]


def test_normalize_captures_root_route(tmp_path: Path):
    (tmp_path / "docs/spec").mkdir(parents=True)
    (tmp_path / "docs/spec/00-master-instruction.md").write_text("| route | note |\n|---|---|\n| / | homepage |\n", encoding="utf-8")
    (tmp_path / "docs/spec/website-structure.md").write_text("/\n", encoding="utf-8")
    (tmp_path / "data/seeds").mkdir(parents=True)
    rc = cmd_normalize(Namespace(repo_root=str(tmp_path)))
    assert rc == 0
    paths = resolve_paths(tmp_path)
    routes = json.loads(read_text(paths.contracts_dir / "route_contracts.json"))
    assert any(r.get("route") == "/" for r in routes)


def test_extract_routes_ignores_urls_for_root():
    text = "See https://example.com/ for docs\n/\n/home"
    routes = extract_routes(text)
    assert "/" in routes
    assert "/home" in routes


def _prepare_contract_min(contracts_dir: Path):
    write_json(contracts_dir / "route_contracts.json", [{"route": "/", "source": "x"}])
    write_json(contracts_dir / "api_contracts.json", [{"method": "GET", "endpoint": "/api/ping", "source": "x"}])
    write_json(contracts_dir / "enum_registry.json", {"x": []})
    write_json(contracts_dir / "gate_matrix.json", {"generated_at": "x", "source": "x", "tiers_detected": []})
    write_json(contracts_dir / "checkpoint_policy.json", {"generated_at": "x", "source": "x", "tasks": {"P0-000": {}}})
    write_json(
        contracts_dir / "seed_schema_manifest.json",
        {"generated_at": "x", "source": "x", "is_demo_rules_present": True, "seed_files": ["inventory-lots.demo.json"]},
    )


def test_lint_detects_api_drift(tmp_path: Path, monkeypatch):
    app_root = tmp_path / "app"
    repo_root = tmp_path / "repo"
    contracts = app_root / "out/contracts"
    for p in [contracts, app_root / "out/inventory", app_root / "out/plans", app_root / "out/prompts", app_root / "out/runs", app_root / "out/reconcile"]:
        p.mkdir(parents=True, exist_ok=True)
    (repo_root / "docs/spec").mkdir(parents=True, exist_ok=True)
    (repo_root / "docs/spec/06-app-router-structure.md").write_text("POST /api/lead\n", encoding="utf-8")
    _prepare_contract_min(contracts)
    (app_root / "README.md").write_text("streamlit run streamlit_wrapper.py", encoding="utf-8")
    (app_root / "streamlit_wrapper.py").write_text("#x", encoding="utf-8")

    paths = AppPaths(repo_root=repo_root, app_root=app_root, out_root=app_root / "out", inventory_dir=app_root / "out/inventory", contracts_dir=contracts, plans_dir=app_root / "out/plans", prompts_dir=app_root / "out/prompts", runs_dir=app_root / "out/runs", reconcile_dir=app_root / "out/reconcile")
    monkeypatch.setattr(lint_mod, "resolve_paths", lambda *args, **kwargs: paths)
    lint_mod.cmd_lint(Namespace(repo_root=str(repo_root), strict=False, profile="governed"))
    report = read_text(contracts / "lint_report.json")
    assert "api_drift_missing_in_contracts" in report


def test_lint_detects_seed_enum_mismatch(tmp_path: Path, monkeypatch):
    app_root = tmp_path / "app"
    repo_root = tmp_path / "repo"
    contracts = app_root / "out/contracts"
    for p in [contracts, app_root / "out/inventory", app_root / "out/plans", app_root / "out/prompts", app_root / "out/runs", app_root / "out/reconcile"]:
        p.mkdir(parents=True, exist_ok=True)
    (repo_root / "data/seeds").mkdir(parents=True, exist_ok=True)
    write_json(repo_root / "data/seeds/inventory-lots.demo.json", {"inventory_lots": [{"status": "stale"}]})
    _prepare_contract_min(contracts)
    (app_root / "README.md").write_text("streamlit run streamlit_wrapper.py", encoding="utf-8")
    (app_root / "streamlit_wrapper.py").write_text("#x", encoding="utf-8")

    paths = AppPaths(repo_root=repo_root, app_root=app_root, out_root=app_root / "out", inventory_dir=app_root / "out/inventory", contracts_dir=contracts, plans_dir=app_root / "out/plans", prompts_dir=app_root / "out/prompts", runs_dir=app_root / "out/runs", reconcile_dir=app_root / "out/reconcile")
    monkeypatch.setattr(lint_mod, "resolve_paths", lambda *args, **kwargs: paths)
    lint_mod.cmd_lint(Namespace(repo_root=str(repo_root), strict=False, profile="governed"))
    report = read_text(contracts / "lint_report.json")
    assert "seed_enum_mismatch_inventory_status" in report
