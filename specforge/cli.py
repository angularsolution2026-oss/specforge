from __future__ import annotations

import argparse

from .commands import (
    cmd_doctor,
    cmd_ingest,
    cmd_lint,
    cmd_normalize,
    cmd_plan,
    cmd_prompt,
    cmd_reconcile,
    cmd_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="specforge - spec to contracts automation toolkit")
    parser.add_argument("--repo-root", default="..", help="Repository root that contains docs/.ai/tools/data")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest", help="Scan repo and emit machine-readable inventory.")
    sub.add_parser("normalize", help="Generate core contract JSON files.")
    p_lint = sub.add_parser("lint", help="Lint generated contracts and invariants.")
    p_lint.add_argument("--strict", action="store_true", help="Exit non-zero on WARN/FAIL findings.")
    p_lint.add_argument("--profile", choices=["standalone", "core", "governed"], default="standalone")

    p_plan = sub.add_parser("plan", help="Generate task packets from lane plan.")
    p_plan.add_argument("--task-id", required=True)

    p_prompt = sub.add_parser("prompt", help="Generate task-specific master prompt.")
    p_prompt.add_argument("--task-id", required=True)

    p_run = sub.add_parser("run", help="Run orchestration hook through ai_executor.")
    p_run.add_argument("--task-id", required=True)
    p_run.add_argument("--mode", choices=["dry-run", "execute"], default="dry-run")
    p_run.add_argument("--profile", choices=["standalone", "core", "governed"], default="standalone")
    p_run.add_argument("--preflight-strict", action="store_true")
    p_run.add_argument("--allow-executor-on-block", action="store_true")

    p_reconcile = sub.add_parser("reconcile", help="Snapshot task/checkpoint/state consistency.")
    p_reconcile.add_argument("--task-id", required=True)
    p_reconcile.add_argument("--sync", action="store_true", help="Apply limited auto-sync to state/progress files.")

    p_doctor = sub.add_parser("doctor", help="Run full sequential quality pipeline with fail-fast checks.")
    p_doctor.add_argument("--task-id", required=True)
    p_doctor.add_argument("--sync", action="store_true", help="Forward --sync to reconcile.")
    p_doctor.add_argument("--run-mode", choices=["dry-run", "execute"], default=None, help="Optional run step at end.")
    p_doctor.add_argument("--profile", choices=["standalone", "core", "governed"], default="standalone")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "ingest":
        return cmd_ingest(args)
    if args.command == "normalize":
        return cmd_normalize(args)
    if args.command == "lint":
        return cmd_lint(args)
    if args.command == "plan":
        return cmd_plan(args)
    if args.command == "prompt":
        return cmd_prompt(args)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "reconcile":
        return cmd_reconcile(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
