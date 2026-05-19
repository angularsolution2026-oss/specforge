from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable


def now_iso() -> str:
    forced = os.getenv("SPECFORGE_NOW", "").strip()
    if forced:
        return forced
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
    routes: set[str] = set()
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if "http://" in s.lower() or "https://" in s.lower():
            continue
        if s == "/":
            routes.add("/")
            continue
        if "|" in s:
            routes.update(extract_table_routes(s))
            continue
        if any(ch in s for ch in ("├", "└", "│", "─")):
            routes.update(extract_tree_routes(s))
            continue
        m = re.fullmatch(r"/[a-zA-Z0-9\-\[\]/]+/?", s)
        if m:
            r = m.group(0).rstrip("/") or "/"
            routes.add(r)
    return sorted(routes)


def extract_table_routes(text: str) -> list[str]:
    routes: set[str] = set()
    for line in text.splitlines():
        if "|" not in line or "---" in line:
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        for c in cells:
            if "http://" in c.lower() or "https://" in c.lower():
                continue
            if c == "/":
                routes.add("/")
                continue
            if "/page" in c:
                continue
            m = re.fullmatch(r"/[a-zA-Z0-9\-\[\]/]+/?", c)
            if not m:
                continue
            routes.add((m.group(0).rstrip("/")) or "/")
    return sorted(routes)


def extract_tree_routes(text: str) -> list[str]:
    routes: set[str] = set()
    # Capture tree lines like:
    # ├── /sa-ban
    # │   └── /sa-ban/[lot-id]
    for line in text.splitlines():
        s = line.strip()
        if "http://" in s.lower() or "https://" in s.lower():
            continue
        tokens = re.findall(r"(?:^|[\s│├└─>])(/(?:[a-zA-Z0-9\-\[\]/]+)?)", s)
        if not tokens:
            continue
        for tok in tokens:
            r = tok.strip()
            if r == "/":
                routes.add("/")
                continue
            if not re.fullmatch(r"/[a-zA-Z0-9\-\[\]/]+/?", r):
                continue
            if "/page" in r:
                continue
            routes.add(r.rstrip("/") or "/")
    return sorted(routes)
