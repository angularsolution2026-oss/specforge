#!/usr/bin/env python3
"""Streamlit wrapper for specforge CLI.

Run:
    streamlit run specforge/streamlit_wrapper.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
TASK_GRAPH = REPO_ROOT / ".ai" / "planning" / "TASK_GRAPH.md"
SPECFORGE_RUNS = APP_DIR / "out" / "runs"
SPECFORGE_CONTRACTS = APP_DIR / "out" / "contracts"


def list_tasks() -> list[str]:
    if not TASK_GRAPH.exists():
        return ["P0-000"]
    ids: list[str] = []
    text = TASK_GRAPH.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        m = re.match(r"^\|\s*`?(P\d+-\d+|GOV-[A-Z0-9-]+)`?\s*\|", line)
        if m:
            tid = m.group(1)
            if tid not in ids:
                ids.append(tid)
    return ids or ["P0-000"]


def run_specforge(args: list[str]) -> tuple[int, str]:
    cmd = [sys.executable, "-m", "specforge", "--repo-root", str(REPO_ROOT), *args]
    proc = subprocess.run(
        cmd,
        cwd=str(APP_DIR),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
    return int(proc.returncode), output


def read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


st.set_page_config(page_title="Specforge Wrapper", layout="wide")
st.title("Specforge Streamlit Wrapper")
st.caption(f"Repo: `{REPO_ROOT}`")

if "output" not in st.session_state:
    st.session_state.output = ""
if "last_cmd" not in st.session_state:
    st.session_state.last_cmd = ""
if "last_exit" not in st.session_state:
    st.session_state.last_exit = 0

task_ids = list_tasks()

with st.sidebar:
    st.header("Execution")
    task_id = st.selectbox("Task ID", task_ids, index=0)
    strict = st.checkbox("Lint strict", value=True)
    sync = st.checkbox("Reconcile sync", value=False)
    run_mode = st.selectbox("Run mode", ["none", "dry-run", "execute"], index=1)
    st.divider()
    st.caption("`doctor` runs sequential fail-fast pipeline.")


def execute(label: str, args: list[str]) -> None:
    st.session_state.last_cmd = "python -m specforge --repo-root <repo> " + " ".join(args)
    with st.spinner(f"Running: {label} ..."):
        code, out = run_specforge(args)
    st.session_state.last_exit = code
    st.session_state.output = f"[exit={code}]\n{out}"


col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Core")
    if st.button("Ingest", use_container_width=True):
        execute("ingest", ["ingest"])
    if st.button("Normalize", use_container_width=True):
        execute("normalize", ["normalize"])
    if st.button("Lint", use_container_width=True):
        cmd = ["lint"]
        if strict:
            cmd.append("--strict")
        execute("lint", cmd)

with col2:
    st.subheader("Task")
    if st.button("Plan", use_container_width=True):
        execute("plan", ["plan", "--task-id", task_id])
    if st.button("Prompt", use_container_width=True):
        execute("prompt", ["prompt", "--task-id", task_id])
    if st.button("Reconcile", use_container_width=True):
        cmd = ["reconcile", "--task-id", task_id]
        if sync:
            cmd.append("--sync")
        execute("reconcile", cmd)

with col3:
    st.subheader("Pipeline")
    if st.button("Run", use_container_width=True):
        if run_mode == "none":
            st.warning("Select `dry-run` or `execute` to run task step.")
        else:
            execute("run", ["run", "--task-id", task_id, "--mode", run_mode])
    if st.button("Doctor", type="primary", use_container_width=True):
        cmd = ["doctor", "--task-id", task_id]
        if sync:
            cmd.append("--sync")
        if run_mode != "none":
            cmd.extend(["--run-mode", run_mode])
        execute("doctor", cmd)

st.divider()

if st.session_state.last_cmd:
    st.code(st.session_state.last_cmd, language="powershell")

st.subheader("Output")
st.code(st.session_state.output or "(No output yet)", language="text")

st.subheader("Latest Reports")
left, right = st.columns(2)

with left:
    lint_report = read_json(SPECFORGE_CONTRACTS / "lint_report.json")
    st.markdown("**Lint Report**")
    if lint_report is None:
        st.info("No lint report.")
    else:
        st.json(lint_report)

with right:
    doctor_report = read_json(SPECFORGE_RUNS / f"{task_id}.doctor_report.json")
    st.markdown(f"**Doctor Report ({task_id})**")
    if doctor_report is None:
        st.info("No doctor report for selected task.")
    else:
        st.json(doctor_report)
