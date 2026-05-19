from argparse import Namespace
from pathlib import Path

from specforge.commands.lint import cmd_lint
from specforge.commands.normalize import cmd_normalize
from specforge.errors import CONTRACT_ERROR, GOVERNANCE_ERROR, OK
from specforge.utils import read_text


def _mk_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs/spec").mkdir(parents=True, exist_ok=True)
    (repo / "data/seeds").mkdir(parents=True, exist_ok=True)
    (repo / "docs/spec/website-structure.md").write_text("/home\n", encoding="utf-8")
    return repo


def test_lint_warn_only_non_strict_returns_ok(tmp_path: Path):
    repo = _mk_repo(tmp_path)
    out_root = tmp_path / "out-a"
    assert cmd_normalize(Namespace(repo_root=str(repo), out_root=str(out_root))) == 0
    rc = cmd_lint(Namespace(repo_root=str(repo), out_root=str(out_root), strict=False, profile="core"))
    assert rc == OK


def test_lint_warn_only_strict_returns_nonzero(tmp_path: Path):
    repo = _mk_repo(tmp_path)
    out_root = tmp_path / "out-b"
    assert cmd_normalize(Namespace(repo_root=str(repo), out_root=str(out_root))) == 0
    rc = cmd_lint(Namespace(repo_root=str(repo), out_root=str(out_root), strict=True, profile="core"))
    assert rc == CONTRACT_ERROR


def test_governed_strict_missing_governance_returns_governance_error(tmp_path: Path):
    repo = _mk_repo(tmp_path)
    out_root = tmp_path / "out-c"
    assert cmd_normalize(Namespace(repo_root=str(repo), out_root=str(out_root))) == 0
    rc = cmd_lint(Namespace(repo_root=str(repo), out_root=str(out_root), strict=True, profile="governed"))
    assert rc == GOVERNANCE_ERROR


def test_out_root_isolation_between_runs(tmp_path: Path):
    repo = _mk_repo(tmp_path)
    out1 = tmp_path / "out-1"
    out2 = tmp_path / "out-2"
    assert cmd_normalize(Namespace(repo_root=str(repo), out_root=str(out1))) == 0
    assert cmd_lint(Namespace(repo_root=str(repo), out_root=str(out1), strict=False, profile="core")) == OK
    assert (out1 / "contracts/lint_report.json").exists()
    assert not (out2 / "contracts/lint_report.json").exists()

    assert cmd_normalize(Namespace(repo_root=str(repo), out_root=str(out2))) == 0
    assert cmd_lint(Namespace(repo_root=str(repo), out_root=str(out2), strict=False, profile="core")) == OK
    assert (out2 / "contracts/lint_report.json").exists()
    text1 = read_text(out1 / "contracts/lint_report.json")
    text2 = read_text(out2 / "contracts/lint_report.json")
    assert '"profile": "core"' in text1
    assert '"profile": "core"' in text2

