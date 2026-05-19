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
python -m specforge.cli --repo-root .. --out-root ../tmp/specforge-out ingest
python -m specforge.cli normalize --repo-root ..
python -m specforge.cli lint --repo-root ..
python -m specforge.cli lint --repo-root .. --strict
python -m specforge.cli lint --repo-root .. --profile standalone
python -m specforge.cli lint --repo-root .. --profile core
python -m specforge.cli lint --repo-root .. --profile governed --strict
python -m specforge.cli plan --repo-root .. --task-id P0-000
python -m specforge.cli prompt --repo-root .. --task-id P0-000
python -m specforge.cli run --repo-root .. --task-id P0-000 --mode dry-run
python -m specforge.cli run --repo-root .. --task-id P0-000 --mode dry-run --allow-executor-on-block
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
  events/
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

## Lint profiles

- `standalone`: default for specforge tool-repo smoke checks.
- `core`: universal schema/contract/drift checks only.
- `governed`: strict AI governance checks for target repositories.
- governed profile always enforces required governance contracts; `--strict` additionally makes WARN-only runs return non-zero.

## Output root isolation

- Use `--out-root <path>` to isolate artifacts per target/run.
- If omitted, output defaults to `specforge/out/` for backward compatibility.

## Run safety behavior

- `execute`: blocked when preflight blockers exist.
- `dry-run` (default): blocked when preflight blockers exist.
- escape hatch: `--allow-executor-on-block` allows dry-run executor invocation while still recording blockers.
- `--preflight-strict`: enforces strict preflight blockers regardless of mode.

## Stable error codes

- `0`: OK
- `1`: GENERAL_FAILURE
- `10`: INPUT_ERROR
- `20`: CONTRACT_ERROR
- `30`: GOVERNANCE_ERROR
- `40`: PREFLIGHT_BLOCKED
- `50`: EXECUTOR_ERROR
- `60`: INTERNAL_ERROR

## Evidence contract (reconcile)

Evidence groups:

- manifest (`manifest.json`)
- quality gate proof (`quality-gates.json` or `lint_report.json`)
- command proof (`command-log.txt` or `run_report.json`)
- change proof (`changed-files.json` or `git-diff.patch` or `diff.patch`)

Semantic validation distinguishes:

- `missing`: missing required evidence groups
- `invalid`: malformed/incompatible evidence
- `weak`: non-fatal low-confidence evidence

## Standalone Tool Repo vs Target Repo

This repository is the Specforge tool itself. It does not need to contain product folders such as `.ai`, `docs/spec`, or `data/seeds`.

Specforge inspects a target repository through `--repo-root`.

- Standalone tool-repo smoke tests:
  - `python -m pip install -e .[dev,ui]`
  - `python -m pytest`
  - `python -m specforge --repo-root . ingest`
  - `python -m specforge --repo-root . normalize`
  - `python -m specforge --repo-root . lint --profile standalone`
- Governed target-repo execution:
  - `python -m specforge --repo-root <path-to-target-repo> doctor --task-id P0-000 --profile governed`

Notes:

- `lint --profile standalone` in standalone mode is expected to run as a smoke test.
- `lint --profile governed --strict` is expected to fail in standalone mode with governance-focused findings.
- Use a fixture target repo or a real governed repo to validate governed PASS behavior.

## Target repo fixture guidance

Governed target repos should provide:

- `.ai/registry/CANONICAL_AUTHORITY.json`
- `.ai/registry/FILE_OWNERSHIP_MAP.json`
- `.ai/tasks/TASK_GRAPH.json`
- `.ai/state/checkpoints.json`
- `docs/spec/*` as available
- `data/seeds/*` as available
- `tools/ai_executor.py` for `run`

## CI Behavior

GitHub Actions CI validates the standalone tool repository by running:

- `python -m pytest`
- `python -m specforge --repo-root . ingest`
- `python -m specforge --repo-root . normalize`
- `python -m specforge --repo-root . lint --profile standalone`

CI intentionally does not run `lint --profile governed --strict` against the standalone tool repo to avoid false failures when governance fixtures are absent.
