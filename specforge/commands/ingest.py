from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from ..config import ensure_out_dirs, resolve_paths
from ..utils import now_iso, read_text, write_json


def cmd_ingest(args: Namespace) -> int:
    out_root = Path(args.out_root) if getattr(args, "out_root", None) else None
    paths = resolve_paths(Path(args.repo_root), out_root=out_root)
    ensure_out_dirs(paths)

    include_dirs = ["docs/spec", ".ai", "tools", "data/seeds"]
    files: list[dict] = []
    for rel_dir in include_dirs:
        base = paths.repo_root / rel_dir
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            text = read_text(p)
            files.append(
                {
                    "path": str(p.relative_to(paths.repo_root)).replace("\\", "/"),
                    "bytes": p.stat().st_size,
                    "line_count": len(text.splitlines()),
                    "heading_count": sum(1 for ln in text.splitlines() if ln.startswith("#")),
                }
            )

    payload = {
        "generated_at": now_iso(),
        "repo_root": str(paths.repo_root),
        "included": include_dirs,
        "file_count": len(files),
        "files": files,
    }
    out = paths.inventory_dir / "repo_inventory.json"
    write_json(out, payload)
    print(f"WROTE={out}")
    print(f"FILE_COUNT={len(files)}")
    return 0
