# specforge

`specforge` is a Python control-plane utility for:

1. Ingesting repository specs/governance into a machine-readable inventory.
2. Normalizing key contracts (routes, APIs, enums, gates, checkpoints).
3. Linting consistency and contract integrity.
4. Generating task packets and AI prompts.
5. Running task orchestration hooks.
6. Reconciling status/evidence snapshots.

## Quick start

```powershell
cd specforge
python -m specforge.cli ingest --repo-root ..
python -m specforge.cli normalize --repo-root ..
python -m specforge.cli lint --repo-root ..
python -m specforge.cli lint --repo-root .. --strict
python -m specforge.cli plan --repo-root .. --task-id P0-000
python -m specforge.cli prompt --repo-root .. --task-id P0-000
python -m specforge.cli run --repo-root .. --task-id P0-000 --mode dry-run
python -m specforge.cli reconcile --repo-root .. --task-id P0-000
python -m specforge.cli reconcile --repo-root .. --task-id P0-000 --sync
python -m specforge.cli doctor --repo-root .. --task-id P0-000
python -m specforge.cli doctor --repo-root .. --task-id P0-000 --run-mode dry-run
```

## Streamlit wrapper

```powershell
pip install -e .[ui]
streamlit run streamlit_wrapper.py
```

For tests:

```powershell
pip install -e .[dev]
pytest
```

The wrapper supports:

- ingest
- normalize
- lint (`strict` option)
- plan / prompt / reconcile
- run (`dry-run` / `execute`)
- doctor (sequential fail-fast pipeline)

## Output structure

Generated artifacts are written under:

```text
specforge/out/
  inventory/
  contracts/
  plans/
  prompts/
  runs/
  reconcile/
```

## Contract model files

`normalize` emits:

- `route_contracts.json`
- `api_contracts.json`
- `enum_registry.json`
- `gate_matrix.json`
- `checkpoint_policy.json`
- `seed_schema_manifest.json`

These are intentionally stable JSON interfaces for downstream automation.

## Standalone Tool Repo vs Target Repo

This repository is the Specforge tool itself. It does not need to contain product folders such as `.ai`, `docs/spec`, or `data/seeds`.

Specforge inspects a target repository through `--repo-root`.

- Standalone tool-repo smoke tests:
  - `python -m pip install -e .[dev,ui]`
  - `python -m pytest`
  - `python -m specforge --repo-root . ingest`
  - `python -m specforge --repo-root . normalize`
  - `python -m specforge --repo-root . lint`
- Governed target-repo execution:
  - `python -m specforge --repo-root <path-to-target-repo> doctor --task-id P0-000`

Notes:
- `lint` in standalone mode is expected to run as a smoke test.
- `lint --strict` may fail in standalone mode because governance files are intentionally absent.
- Use a fixture target repo or a real governed repo to validate strict PASS behavior.

## CI Behavior

GitHub Actions CI validates the standalone tool repository by running:

- `python -m pytest`
- `python -m specforge --repo-root . ingest`
- `python -m specforge --repo-root . normalize`
- `python -m specforge --repo-root . lint`

CI intentionally does not run `lint --strict` against the standalone tool repo to avoid false failures when governance fixtures are absent.
