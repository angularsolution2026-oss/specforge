from argparse import Namespace
from pathlib import Path

from specforge.commands import lint as lint_mod
from specforge.config import AppPaths
from specforge.utils import write_json, read_text


def test_lint_detects_streamlit_readme_path_mismatch(tmp_path: Path, monkeypatch):
    app_root = tmp_path / "app"
    repo_root = tmp_path / "repo"
    out = app_root / "out"
    contracts = out / "contracts"
    for p in [contracts, out / "inventory", out / "plans", out / "prompts", out / "runs", out / "reconcile", repo_root]:
        p.mkdir(parents=True, exist_ok=True)

    (app_root / "README.md").write_text("streamlit run specforge/streamlit_wrapper.py", encoding="utf-8")
    # intentionally do not create app_root/specforge/streamlit_wrapper.py

    write_json(contracts / "route_contracts.json", [{"route": "/", "source": "x"}])
    write_json(contracts / "api_contracts.json", [{"method": "GET", "endpoint": "/api/ping", "source": "x"}])
    write_json(contracts / "enum_registry.json", {})
    write_json(contracts / "gate_matrix.json", {"generated_at": "x", "source": "x", "tiers_detected": []})
    write_json(contracts / "checkpoint_policy.json", {"generated_at": "x", "source": "x", "tasks": {"P0-000": {}}})
    write_json(
        contracts / "seed_schema_manifest.json",
        {"generated_at": "x", "source": "x", "is_demo_rules_present": True, "seed_files": ["a.json"]},
    )

    paths = AppPaths(
        repo_root=repo_root,
        app_root=app_root,
        out_root=out,
        inventory_dir=out / "inventory",
        contracts_dir=contracts,
        plans_dir=out / "plans",
        prompts_dir=out / "prompts",
        runs_dir=out / "runs",
        reconcile_dir=out / "reconcile",
    )
    monkeypatch.setattr(lint_mod, "resolve_paths", lambda _: paths)

    rc = lint_mod.cmd_lint(Namespace(repo_root=str(repo_root), strict=False))
    assert rc in (0, 1)
    report = read_text(contracts / "lint_report.json")
    assert "streamlit_readme_path_mismatch" in report
