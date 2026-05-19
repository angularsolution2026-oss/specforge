import json
from argparse import Namespace
from pathlib import Path

from specforge.commands.lint import cmd_lint
from specforge.commands.normalize import cmd_normalize
from specforge.commands.reconcile import cmd_reconcile, evaluate_evidence
from specforge.commands.run import cmd_run
from specforge.commands import lint as lint_mod
from specforge.commands import reconcile as rec_mod
from specforge.commands import run as run_mod
from specforge.config import AppPaths, ensure_out_dirs, resolve_paths
from specforge.errors import GOVERNANCE_ERROR, OK, PREFLIGHT_BLOCKED
from specforge.utils import read_text


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _prepare_min_contracts(paths):
    _write_json(paths.contracts_dir / "route_contracts.json", [{"route": "/", "source": "x"}])
    _write_json(paths.contracts_dir / "api_contracts.json", [{"method": "GET", "endpoint": "/api/ping", "source": "x"}])
    _write_json(paths.contracts_dir / "enum_registry.json", {"x": []})
    _write_json(paths.contracts_dir / "gate_matrix.json", {"generated_at": "x", "source": "x", "tiers_detected": []})
    _write_json(paths.contracts_dir / "checkpoint_policy.json", {"generated_at": "x", "source": "x", "tasks": {}})
    _write_json(
        paths.contracts_dir / "seed_schema_manifest.json",
        {"generated_at": "x", "source": "x", "is_demo_rules_present": True, "seed_files": ["a.json"]},
    )


def _mk_paths(tmp_path: Path, repo: Path) -> AppPaths:
    app_root = tmp_path / "app"
    out_root = app_root / "out"
    return AppPaths(
        repo_root=repo,
        app_root=app_root,
        out_root=out_root,
        inventory_dir=out_root / "inventory",
        contracts_dir=out_root / "contracts",
        plans_dir=out_root / "plans",
        prompts_dir=out_root / "prompts",
        runs_dir=out_root / "runs",
        reconcile_dir=out_root / "reconcile",
        events_dir=out_root / "events",
    )


def test_lint_profiles_governed_missing_contracts(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    paths = _mk_paths(tmp_path, repo)
    ensure_out_dirs(paths)
    _prepare_min_contracts(paths)
    monkeypatch.setattr(lint_mod, "resolve_paths", lambda *args, **kwargs: paths)
    rc = cmd_lint(Namespace(repo_root=str(tmp_path), strict=True, profile="governed"))
    assert rc == GOVERNANCE_ERROR
    report = json.loads(read_text(paths.contracts_dir / "lint_report.json"))
    assert report["profile"] == "governed"
    assert any(f.get("rule_group") == "governed" for f in report["findings"])


def test_deterministic_now_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SPECFORGE_NOW", "2026-01-01T00:00:00")
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    paths = _mk_paths(tmp_path, repo)
    ensure_out_dirs(paths)
    _prepare_min_contracts(paths)
    monkeypatch.setattr(lint_mod, "resolve_paths", lambda *args, **kwargs: paths)
    rc = cmd_lint(Namespace(repo_root=str(tmp_path), strict=False, profile="core"))
    assert rc == OK
    report = json.loads(read_text(paths.contracts_dir / "lint_report.json"))
    assert report["generated_at"] == "2026-01-01T00:00:00"


def test_run_dry_run_blocked_by_default_and_event_written(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    paths = _mk_paths(tmp_path, repo)
    ensure_out_dirs(paths)
    monkeypatch.setattr(run_mod, "resolve_paths", lambda *args, **kwargs: paths)
    _write_json(
        paths.plans_dir / "P0-000.task_packets.json",
        {"packets": [{"task_id": "P0-000", "lane_id": "A", "checkpoint_required": "CP-0", "checkpoint_status": "pending", "allowed_files": [], "forbidden_files": []}]},
    )
    _write_json(paths.contracts_dir / "lint_report.json", {"status": "PASS"})
    rc = cmd_run(
        Namespace(
            repo_root=str(repo),
            task_id="P0-000",
            mode="dry-run",
            profile="standalone",
            preflight_strict=False,
            allow_executor_on_block=False,
        )
    )
    assert rc == PREFLIGHT_BLOCKED
    report = json.loads(read_text(paths.runs_dir / "P0-000.dry-run.run_report.json"))
    assert report["command"] == ""
    events = read_text(paths.events_dir / "specforge_events.jsonl")
    assert "preflight_blocked" in events


def test_run_dry_run_allow_executor_on_block_with_fake_executor(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True, exist_ok=True)
    (repo / "tools/ai_executor.py").write_text(
        "from pathlib import Path\nPath('executor_marker.txt').write_text('ran', encoding='utf-8')\nprint('ok')\n",
        encoding="utf-8",
    )
    paths = _mk_paths(tmp_path, repo)
    ensure_out_dirs(paths)
    monkeypatch.setattr(run_mod, "resolve_paths", lambda *args, **kwargs: paths)
    _write_json(
        paths.plans_dir / "P0-000.task_packets.json",
        {"packets": [{"task_id": "P0-000", "lane_id": "A", "checkpoint_required": "CP-0", "checkpoint_status": "pending", "allowed_files": [], "forbidden_files": []}]},
    )
    _write_json(paths.contracts_dir / "lint_report.json", {"status": "PASS"})
    rc = cmd_run(
        Namespace(
            repo_root=str(repo),
            task_id="P0-000",
            mode="dry-run",
            profile="standalone",
            preflight_strict=False,
            allow_executor_on_block=True,
        )
    )
    assert rc == OK
    assert (repo / "executor_marker.txt").exists()


def test_evidence_semantic_task_id_mismatch(tmp_path: Path):
    ev = tmp_path / ".ai/evidence/P0-000"
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "manifest.json").write_text(json.dumps({"task_id": "P0-999", "status": "PASS"}), encoding="utf-8")
    (ev / "quality-gates.json").write_text(json.dumps({"status": "PASS", "gates": []}), encoding="utf-8")
    (ev / "command-log.txt").write_text("python -m pytest", encoding="utf-8")
    (ev / "git-diff.patch").write_text("diff --git a/x b/x", encoding="utf-8")
    result = evaluate_evidence(ev, task_id="P0-000")
    assert "manifest.json:task_id_mismatch" in result["invalid"]


def test_reconcile_fsm_invalid_transition_returns_governance_error(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    paths = _mk_paths(tmp_path, repo)
    (repo / ".ai/state").mkdir(parents=True, exist_ok=True)
    (repo / ".ai/evidence/P0-000").mkdir(parents=True, exist_ok=True)
    _write_json(repo / ".ai/state/checkpoints.json", {"tasks": {"P0-000": {"checkpoints": {"CP-0": {"status": "approved"}}}}})
    _write_json(repo / ".ai/state/task-state.current.json", {"task_id": "P0-000", "status": "pending"})
    _write_json(repo / ".ai/evidence/P0-000/manifest.json", {"task_id": "P0-000", "status": "PASS"})
    _write_json(repo / ".ai/evidence/P0-000/quality-gates.json", {"status": "PASS", "gates": []})
    (repo / ".ai/evidence/P0-000/command-log.txt").write_text("python -m pytest", encoding="utf-8")
    (repo / ".ai/evidence/P0-000/git-diff.patch").write_text("diff --git a/a b/a", encoding="utf-8")
    ensure_out_dirs(paths)
    monkeypatch.setattr(rec_mod, "resolve_paths", lambda *args, **kwargs: paths)
    rc = cmd_reconcile(Namespace(repo_root=str(repo), task_id="P0-000", sync=False))
    assert rc == GOVERNANCE_ERROR


def test_normalize_emits_parser_diagnostics(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "docs/spec").mkdir(parents=True, exist_ok=True)
    (repo / "docs/spec/website-structure.md").write_text("/\nunknown route => /abc def\n", encoding="utf-8")
    (repo / "data/seeds").mkdir(parents=True, exist_ok=True)
    rc = cmd_normalize(Namespace(repo_root=str(repo)))
    assert rc == 0
    paths = resolve_paths(repo)
    diag = json.loads(read_text(paths.contracts_dir / "parser_diagnostics.json"))
    assert "confidence" in diag
    assert isinstance(diag.get("unknown_fragments", []), list)
