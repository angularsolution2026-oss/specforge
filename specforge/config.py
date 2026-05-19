from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    repo_root: Path
    app_root: Path
    out_root: Path
    inventory_dir: Path
    contracts_dir: Path
    plans_dir: Path
    prompts_dir: Path
    runs_dir: Path
    reconcile_dir: Path


def resolve_paths(repo_root: Path) -> AppPaths:
    app_root = Path(__file__).resolve().parents[1]
    out_root = app_root / "out"
    return AppPaths(
        repo_root=repo_root.resolve(),
        app_root=app_root,
        out_root=out_root,
        inventory_dir=out_root / "inventory",
        contracts_dir=out_root / "contracts",
        plans_dir=out_root / "plans",
        prompts_dir=out_root / "prompts",
        runs_dir=out_root / "runs",
        reconcile_dir=out_root / "reconcile",
    )


def ensure_out_dirs(paths: AppPaths) -> None:
    for p in (
        paths.out_root,
        paths.inventory_dir,
        paths.contracts_dir,
        paths.plans_dir,
        paths.prompts_dir,
        paths.runs_dir,
        paths.reconcile_dir,
    ):
        p.mkdir(parents=True, exist_ok=True)
