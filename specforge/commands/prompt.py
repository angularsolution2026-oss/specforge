from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..utils import now_iso, read_text, write_text


def cmd_prompt(args: Namespace) -> int:
    paths = resolve_paths(Path(args.repo_root))
    ensure_out_dirs(paths)
    task_id = args.task_id
    plan_path = paths.plans_dir / f"{task_id}.task_packets.json"
    if not plan_path.exists():
        raise SystemExit(f"Missing plan packets. Run plan first: {plan_path}")
    plan = json.loads(read_text(plan_path))
    packets = plan.get("packets", [])
    packet_lines = []
    for p in packets:
        packet_lines.append(f"- Lane {p.get('lane_id')}: owner={p.get('owner')} allowed_files={len(p.get('allowed_files',[]))}")

    body = f"""# SPECFORGE MASTER PROMPT

Generated: {now_iso()}
Task ID: {task_id}

## Mission
Implement task `{task_id}` with strict contract compliance and minimal drift.

## Required contracts
1. specforge/out/contracts/route_contracts.json
2. specforge/out/contracts/api_contracts.json
3. specforge/out/contracts/gate_matrix.json
4. .ai/core/rules.md
5. .ai/core/done-criteria.md
6. .ai/core/delivery-gate.md

## Lane summary
{chr(10).join(packet_lines)}

## Non-negotiables
1. No edits outside lane allowed_files.
2. No edits to docs/spec without approved decision.
3. Run gates from quality-gates for touched scope.
4. Return verification footer before completion claims.
"""
    out = paths.prompts_dir / f"{task_id}.MASTER_PROMPT.md"
    write_text(out, body)
    print(f"WROTE={out}")
    return 0
