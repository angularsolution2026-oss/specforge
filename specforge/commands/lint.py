from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..errors import CONTRACT_ERROR, GOVERNANCE_ERROR, OK
from ..events import emit_event
from ..lint_rules import run_core_rules, run_governed_rules, run_project_rules
from ..utils import now_iso, write_json


def cmd_lint(args: Namespace) -> int:
    paths = resolve_paths(Path(args.repo_root))
    ensure_out_dirs(paths)
    strict = bool(getattr(args, "strict", False))
    profile = str(getattr(args, "profile", "standalone"))
    findings: list[dict] = []

    emit_event(paths, event_type="command_started", command="lint", severity="INFO", message="lint started", data={"profile": profile, "strict": strict})

    if not run_core_rules(paths, findings, profile):
        status = "FAIL"
    else:
        if profile == "governed":
            run_governed_rules(paths, findings, profile, strict=True if strict else True)
            run_project_rules(paths, findings, profile)
        elif profile == "standalone":
            # keep noise low for the tool repository itself
            pass
        elif profile == "core":
            pass
        else:
            findings.append(
                {
                    "severity": "FAIL",
                    "check": "invalid_profile",
                    "message": f"Unknown profile '{profile}'",
                    "profile": profile,
                    "rule_group": "core",
                }
            )

        has_fail = any(f["severity"] == "FAIL" for f in findings)
        has_warn = any(f["severity"] == "WARN" for f in findings)
        if has_fail:
            status = "FAIL"
        elif has_warn:
            status = "WARN"
        else:
            status = "PASS"

    if any(f.get("severity") == "FAIL" for f in findings):
        if any(f.get("rule_group") == "governed" for f in findings):
            code = GOVERNANCE_ERROR
        else:
            code = CONTRACT_ERROR
    else:
        code = OK

    report = {
        "generated_at": now_iso(),
        "status": status,
        "strict": strict,
        "profile": profile,
        "findings": findings,
        "reason_code": code,
    }
    out = paths.contracts_dir / "lint_report.json"
    write_json(out, report)
    print(f"STATUS={status}")
    print(f"FINDINGS={len(findings)}")
    print(f"WROTE={out}")

    emit_event(
        paths,
        event_type="command_completed",
        command="lint",
        severity="FAIL" if code else "INFO",
        reason_code=str(code),
        message=f"lint completed with status={status}",
        data={"profile": profile, "strict": strict, "status": status, "finding_count": len(findings)},
    )
    return code
