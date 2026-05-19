from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..utils import now_iso, read_text, write_text


def _load_json(path: Path) -> dict:
    return json.loads(read_text(path))


def cmd_prompt(args: Namespace) -> int:
    out_root = Path(args.out_root) if getattr(args, "out_root", None) else None
    paths = resolve_paths(Path(args.repo_root), out_root=out_root)
    ensure_out_dirs(paths)
    task_id = args.task_id
    plan_path = paths.plans_dir / f"{task_id}.task_packets.json"
    if not plan_path.exists():
        raise SystemExit(f"Missing plan packets. Run plan first: {plan_path}")

    plan = _load_json(plan_path)
    packets = plan.get("packets", [])
    if not packets:
        raise SystemExit(f"Plan has no packets: {plan_path}")

    canonical = {}
    ca_path = paths.contracts_dir / "canonical_authority.json"
    if ca_path.exists():
        canonical = _load_json(ca_path)

    lane_lines: list[str] = []
    for p in packets:
        lane_lines.append(
            f"- lane={p.get('lane_id')} owner={p.get('owner')} checkpoint={p.get('checkpoint_required')} status={p.get('checkpoint_status')}"
        )

    allowed = sorted({f for p in packets for f in p.get("allowed_files", [])})
    forbidden = sorted({f for p in packets for f in p.get("forbidden_files", [])})
    deps = sorted({d for p in packets for d in p.get("dependencies", [])})
    req_ctx = sorted({c for p in packets for c in p.get("required_context", [])})
    gates = sorted({g for p in packets for g in p.get("required_gates", [])})
    checks = sorted({c for p in packets for c in p.get("validation_commands", [])})
    evidence = sorted({e for p in packets for e in p.get("evidence_required", [])})
    stop_conditions = sorted({s for p in packets for s in p.get("stop_conditions", [])})

    body = f"""# SPECFORGE MASTER PROMPT

Generated: {now_iso()}
Task ID: {task_id}

## 1) Role & Directive
You are a senior AI coding agent operating under Specforge governance. Execute only the scoped task packet.

## 2) Mission
Implement task `{task_id}` with strict contract compliance, minimal drift, and verifiable evidence.

## 3) Canonical Authority
canonical_spec_root: `{canonical.get("canonical_spec_root", "UNKNOWN")}`
deprecated_spec_roots: `{canonical.get("deprecated_spec_roots", [])}`
conflict_rule: `{canonical.get("conflict_rule", "CANONICAL_SPEC_ROOT_ALWAYS_WINS")}`

## 4) Task Scope
{chr(10).join(lane_lines)}

## 5) Allowed Files
{chr(10).join(f"- {x}" for x in allowed) if allowed else "- (none specified)"}

## 6) Forbidden Files
{chr(10).join(f"- {x}" for x in forbidden) if forbidden else "- (none specified)"}

## 7) Required Context
{chr(10).join(f"- {x}" for x in req_ctx) if req_ctx else "- (none specified)"}

## 8) Dependencies
{chr(10).join(f"- {x}" for x in deps) if deps else "- (none specified)"}

## 9) Checkpoint Status
{chr(10).join(f"- lane {p.get('lane_id')}: {p.get('checkpoint_required')} => {p.get('checkpoint_status')}" for p in packets)}

## 10) Required Validation Commands
{chr(10).join(f"- {x}" for x in checks) if checks else "- python -m specforge --repo-root . lint --strict"}

## 11) Evidence Requirements
{chr(10).join(f"- {x}" for x in evidence) if evidence else "- lint_report\n- changed_files_manifest\n- test_output"}

## 12) Stop Conditions
{chr(10).join(f"- {x}" for x in stop_conditions) if stop_conditions else "- Stop if constraints cannot be met."}
- Stop if checkpoint is not approved.
- Stop if ownership conflict is detected.
- Stop if required files are missing.

## 13) Rollback Conditions
- Roll back in-progress edits if strict lint fails due to your change set.
- Roll back if edits drift outside allowed_files.

## 14) Anti-Hallucination Rules
- Do not edit outside allowed_files.
- Do not modify docs/spec unless explicitly allowed.
- Do not claim tests passed unless actually run.
- If required input artifacts are missing, stop and report exact missing paths.

## 15) Output Format
- Summary of changes
- Files touched
- Commands run with exit codes
- Evidence manifest JSON block
- Residual risks

## 16) Final Verification Footer
Include:
`VERIFICATION: lint={{pass/fail}} tests={{pass/fail/not-run}} checkpoint={{approved/not-approved}} ownership={{clear/conflict}} evidence={{present/missing}}`
"""

    out = paths.prompts_dir / f"{task_id}.MASTER_PROMPT.md"
    write_text(out, body)
    print(f"WROTE={out}")
    return 0
