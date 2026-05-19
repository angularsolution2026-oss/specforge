from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )
    return int(proc.returncode), proc.stdout or ""


def discover_files(root: Path, patterns: Iterable[str]) -> list[Path]:
    out: list[Path] = []
    for pattern in patterns:
        out.extend(root.glob(pattern))
    return sorted({p.resolve() for p in out if p.exists() and p.is_file()})


def extract_routes(text: str) -> list[str]:
    return sorted(set(re.findall(r"/[a-zA-Z0-9\-\[\]/]+", text)))


def extract_table_routes(text: str) -> list[str]:
    routes: set[str] = set()
    for line in text.splitlines():
        if "|" not in line or "---" in line:
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        for c in cells:
            if not c.startswith("/"):
                continue
            if "/page" in c:
                continue
            routes.add(c.rstrip("/") or "/")
    return sorted(routes)


def extract_tree_routes(text: str) -> list[str]:
    routes: set[str] = set()
    # Capture tree lines like:
    # ├── /sa-ban
    # │   └── /sa-ban/[lot-id]
    for line in text.splitlines():
        m = re.search(r"[/][a-zA-Z0-9\-\[\]/]+", line)
        if not m:
            continue
        r = m.group(0).strip()
        if "/page" in r:
            continue
        routes.add(r.rstrip("/") or "/")
    return sorted(routes)
