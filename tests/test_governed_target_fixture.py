import json
from argparse import Namespace
from pathlib import Path

from specforge.commands.lint import cmd_lint
from specforge.commands.normalize import cmd_normalize
from specforge.commands.plan import cmd_plan
from specforge.commands.prompt import cmd_prompt
from specforge.commands.reconcile import cmd_reconcile
from specforge.config import resolve_paths
from specforge.utils import read_text


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "target"
    _write(
        repo / ".ai/registry/CANONICAL_AUTHORITY.json",
        json.dumps(
            {
                "canonical_spec_root": "FINAL_SPEC",
                "deprecated_spec_roots": ["docs/spec"],
                "conflict_rule": "CANONICAL_SPEC_ROOT_ALWAYS_WINS",
                "agent_required_read_order": [],
            }
        ),
    )
    _write(
        repo / ".ai/registry/FILE_OWNERSHIP_MAP.json",
        json.dumps(
            {
                "generated_at": "2026-05-19T00:00:00",
                "owners": [{"path": "specforge/commands/*.py", "owner": "tooling", "write_policy": "allowed"}],
            }
        ),
    )
    _write(
        repo / ".ai/tasks/TASK_GRAPH.json",
        json.dumps(
            {
                "generated_at": "2026-05-19T00:00:00",
                "tasks": [
                    {
                        "task_id": "P0-000",
                        "title": "Fixture Task",
                        "status": "pending",
                        "dependencies": [],
                        "checkpoint_required": "CP-0",
                        "allowed_files": ["src/**"],
                        "forbidden_files": [],
                        "required_context": ["docs/spec/00-master-instruction.md"],
                        "required_gates": ["tier1"],
                        "checkpoint_status": "approved",
                        "owner": "tooling",
                        "objective": "verify fixture flow",
                        "stop_conditions": ["stop-x"],
                        "evidence_required": ["manifest"],
                        "validation_commands": ["python -m specforge --repo-root . lint --strict"],
                        "refs": [],
                    }
                ],
            }
        ),
    )
    _write(
        repo / ".ai/state/checkpoints.json",
        json.dumps(
            {
                "tasks": {
                    "P0-000": {
                        "checkpoints": {
                            "CP-0": {"status": "approved"},
                        }
                    }
                }
            }
        ),
    )
    _write(repo / ".ai/evidence/P0-000/manifest.json", json.dumps({"task_id": "P0-000", "status": "PASS"}))
    _write(repo / ".ai/evidence/P0-000/quality-gates.json", json.dumps({"status": "PASS", "gates": []}))
    _write(repo / ".ai/evidence/P0-000/command-log.txt", "run lint --strict")
    _write(repo / ".ai/evidence/P0-000/git-diff.patch", "diff --git a/x b/x")

    _write(repo / "docs/spec/00-master-instruction.md", "POST /api/lead\n| route | note |\n|---|---|\n| / | home |\n")
    _write(repo / "docs/spec/06-app-router-structure.md", "GET /api/ping\n| route | note |\n|---|---|\n| /home | h |\n")
    _write(repo / "docs/spec/website-structure.md", "/\n├── /home\n")
    _write(repo / "docs/spec/05-database-schema.md", "`status` | enum")
    _write(repo / "data/seeds/README.md", "demo guard")
    _write(
        repo / "data/seeds/inventory-lots.demo.json",
        json.dumps({"inventory_lots": [{"status": "available"}]}),
    )
    return repo


def test_governed_target_strict_flow(tmp_path: Path):
    repo = _fixture_repo(tmp_path)
    assert cmd_normalize(Namespace(repo_root=str(repo))) == 0
    paths = resolve_paths(repo)
    assert (paths.contracts_dir / "route_contracts.json").exists()
    assert (paths.contracts_dir / "api_contracts.json").exists()
    assert (paths.contracts_dir / "canonical_authority.json").exists()
    assert (paths.contracts_dir / "ownership_contracts.json").exists()
    assert (paths.contracts_dir / "task_graph_contracts.json").exists()

    assert cmd_lint(Namespace(repo_root=str(repo), strict=True)) == 0
    assert cmd_plan(Namespace(repo_root=str(repo), task_id="P0-000")) == 0
    assert cmd_prompt(Namespace(repo_root=str(repo), task_id="P0-000")) == 0
    assert cmd_reconcile(Namespace(repo_root=str(repo), task_id="P0-000", sync=False)) == 0
    rec = json.loads(read_text(paths.reconcile_dir / "P0-000.reconcile_report.json"))
    assert rec["evidence"]["sufficient"] is True
