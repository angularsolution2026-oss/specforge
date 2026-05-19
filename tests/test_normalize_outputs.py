from argparse import Namespace
from pathlib import Path

from specforge.commands.normalize import cmd_normalize
from specforge.config import resolve_paths


def test_normalize_emits_expected_files(tmp_path: Path):
    (tmp_path / "docs/spec").mkdir(parents=True)
    (tmp_path / ".ai/core").mkdir(parents=True)
    (tmp_path / ".ai/state").mkdir(parents=True)
    (tmp_path / "data/seeds").mkdir(parents=True)
    (tmp_path / "docs/spec/00-master-instruction.md").write_text("| Route | Note |\n|---|---|\n| /home | x |\n", encoding="utf-8")
    (tmp_path / "docs/spec/06-app-router-structure.md").write_text("GET /api/ping", encoding="utf-8")
    (tmp_path / "docs/spec/website-structure.md").write_text("/about", encoding="utf-8")
    (tmp_path / ".ai/core/quality-gates.md").write_text("Tier 1A", encoding="utf-8")
    (tmp_path / ".ai/state/checkpoints.json").write_text('{"tasks":{}}', encoding="utf-8")
    (tmp_path / "data/seeds/README.md").write_text("demo", encoding="utf-8")
    (tmp_path / "data/seeds/a.demo.json").write_text("{}", encoding="utf-8")

    rc = cmd_normalize(Namespace(repo_root=str(tmp_path)))
    assert rc == 0

    paths = resolve_paths(tmp_path)
    assert (paths.contracts_dir / "route_contracts.json").exists()
    assert (paths.contracts_dir / "api_contracts.json").exists()
    assert (paths.contracts_dir / "gate_matrix.json").exists()
