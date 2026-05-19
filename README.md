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
streamlit run specforge/streamlit_wrapper.py
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
