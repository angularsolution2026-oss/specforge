import json
from argparse import Namespace
from pathlib import Path

from specforge.commands.prompt import cmd_prompt
from specforge.config import ensure_out_dirs, resolve_paths
from specforge.utils import read_text, write_json


def test_prompt_includes_stop_conditions(tmp_path: Path):
    paths = resolve_paths(tmp_path)
    ensure_out_dirs(paths)
    task_id = "P0-000"
    write_json(
        paths.plans_dir / f"{task_id}.task_packets.json",
        {
            "task_id": task_id,
            "packets": [
                {
                    "task_id": task_id,
                    "title": "t",
                    "lane_id": "A",
                    "owner": "o",
                    "objective": "x",
                    "dependencies": [],
                    "checkpoint_required": "CP-0",
                    "checkpoint_status": "pending",
                    "allowed_files": ["specforge/commands/*.py"],
                    "forbidden_files": ["docs/spec/*"],
                    "required_context": [],
                    "required_gates": [],
                    "stop_conditions": ["Stop X"],
                    "evidence_required": [],
                    "validation_commands": [],
                    "refs": [],
                }
            ],
        },
    )
    rc = cmd_prompt(Namespace(repo_root=str(tmp_path), task_id=task_id))
    assert rc == 0
    text = read_text(paths.prompts_dir / f"{task_id}.MASTER_PROMPT.md")
    assert "Stop if checkpoint is not approved." in text
    assert "Do not edit outside allowed_files." in text
