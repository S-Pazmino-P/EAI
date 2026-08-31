# ADNI Deterministic Transform

Stage 3 of the EAI pipeline. Re-executes the JSONata mapping expressions
already authored by [Stage 2 (`Mappings/`)](../Mappings/) against the full
ADNIMERGE CSV — deterministically, with no LLM and no network calls. The same
Node/JSONata executor (`eval_jsonata.js`) the pipeline uses is invoked per
row, so the engine semantics (singleton-collapse, `$merge`, `$lookup`, etc.)
match Stage 2 exactly. Patient resources are de-duplicated by identifier, and
all per-type resources are written as JSON files plus a combined FHIR Bundle.

## Overview

`transform_adni_csv.py` runs three phases:

```
PHASE 1/3 LOADING   → read CSV, coerce types per schema.json (same logic as the pipeline's prepare())
PHASE 2/3 TRANSFORM → apply saved llm_*.jsonata mappings via node eval_jsonata.js
PHASE 3/3 WRITING   → assemble per-type JSON + a combined Bundle
```

- **Loading** — `load_rows()` coerces each cell per `schema.json` (missing/empty
  → `null`, `integer`/`number` coerced, everything else left as a string). This
  is identical to `adni_react_pipeline.py`'s `prepare()`, so a mapping written
  against the pipeline's row shape behaves the same way here.
- **Transform** — for Patient/Encounter/Condition, one mapping file each. For
  Observation, per-category `llm_observation_*.jsonata` files are preferred
  (results concatenated); if none are found, it falls back to the combined
  `llm_observation.jsonata` with a warning. Patient resources are
  de-duplicated by identifier value via `normalize_resources()`.
- **Writing** — per-type `out_*.json` files plus a combined `bundle.json`
  (`resourceType: Bundle`, `type: collection`).

## Project Structure

```
.
├── transform_adni_csv.py   # Full-dataset transform (no LLM)
├── schema.json             # ADNI schema (same structure as Mappings/)
├── mappings/               # Copy of Stage 2 JSONata outputs (llm_*.jsonata)
├── environment.yml         # Conda environment (Python + Node.js)
├── requirements.txt        # Stdlib-only Python (pip fallback)
├── sample/                 # Synthetic ADNIMERGE sample (no real ADNI data)
│   ├── adnimerge_synthetic.csv  # 48-row synthetic input (12 subjects)
│   └── README.md           # Sample documentation
└── transformed/            # Output directory (gitignored; ADNI DUA-restricted)
```

## Inputs

| Input | Source | Required |
|-------|--------|----------|
| ADNIMERGE CSV (e.g. `ADNIMERGE_07Jan2026.csv`) | [ADNI LONI-IDA](https://ida.loni.usc.edu) (not shipped) | Yes (`--csv`) |
| `schema.json` | This directory | Yes (`--schema`) |
| `llm_*.jsonata` mapping files | [Stage 2](../Mappings/) | Yes (`--mappings-dir`) |
| `eval_jsonata.js` | [Stage 2](../Mappings/) | Yes (default: `<mappings-dir>/eval_jsonata.js`) |
| `node_modules/jsonata` | [Stage 2](../Mappings/) `npm install` | Yes (resolved via the executor's `cwd`) |
| `node` on PATH | Conda env or system Node.js >= 18 | Yes |

The JSONata mappings and executor are produced by Stage 2; this stage applies
them without re-running generation or validation.

## Configuration

### CLI arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--csv` | (required) | Path to the ADNI-shaped CSV to transform. |
| `--schema` | (required) | Path to `schema.json` (defines fields/types). |
| `--mappings-dir` | `.` | Directory containing `llm_patient.jsonata`, `llm_encounter.jsonata`, `llm_condition.jsonata`, and `llm_observation_<category>.jsonata` files. |
| `--eval-js` | `<mappings-dir>/eval_jsonata.js` | Path to the Node/JSONata executor. |
| `--out-dir` | `./transformed` | Output directory for per-type JSON + the combined Bundle. |

## Usage

### Setup

```bash
conda env create -f environment.yml
conda activate adni-transform        # Python + Node.js in one env

# Stage 2 must have run `npm install` so node_modules/jsonata exists:
#   cd ../Mappings && npm install
```

A pip/venv fallback is provided for users who prefer not to use conda.
Transform itself is Python-stdlib-only (no installable `pip` packages); you
still need [Node.js](https://nodejs.org/) >= 18 and `node_modules/jsonata`
from Stage 2:

```bash
# No pip install needed — transform_adni_csv.py uses only the standard library
# (argparse, csv, glob, json, os, subprocess, sys, time).
```

### Run the transform

```bash
# Place ADNIMERGE_07Jan2026.csv here (obtained via LONI-IDA)
python transform_adni_csv.py \
    --csv ADNIMERGE_07Jan2026.csv \
    --schema schema.json \
    --mappings-dir ../Mappings \
    --out-dir ./transformed
```

### Run against the bundled mappings copy

A copy of Stage 2's mappings is shipped in `mappings/` for convenience. To use
it, point `--mappings-dir` at this directory (and `--eval-js` at Stage 2's
executor, since `node_modules/jsonata` lives there):

```bash
python transform_adni_csv.py \
    --csv ADNIMERGE_07Jan2026.csv \
    --schema schema.json \
    --mappings-dir ./mappings \
    --eval-js ../Mappings/eval_jsonata.js \
    --out-dir ./transformed
```

### Try it without ADNI data

A synthetic 48-row ADNIMERGE CSV is shipped in `sample/` (see [Synthetic
sample](#synthetic-sample)) so the full transform can be exercised without
ADNI access. Using the bundled mappings copy and Stage 2's executor:

```bash
python transform_adni_csv.py \
    --csv sample/adnimerge_synthetic.csv \
    --schema schema.json \
    --mappings-dir ./mappings \
    --eval-js ../Mappings/eval_jsonata.js \
    --out-dir ./transformed
```

This produces 12 Patients, 48 Encounters, 48 Conditions, and 1,757
Observations (1,865 resources total) in `transformed/`.

## Outputs

| File | Description |
|------|-------------|
| `out_patient.json` | Patient resources (de-duplicated by identifier). |
| `out_encounter.json` | Encounter resources (one per CSV row). |
| `out_condition.json` | Condition resources (rows where DX is present). |
| `out_observation.json` | Observation resources (concatenated across categories). |
| `bundle.json` | Combined FHIR Bundle (`resourceType: Bundle`, `type: collection`) wrapping all of the above. |

All outputs are written to `--out-dir` (default `./transformed`, which is
gitignored — see [Data availability](#data-availability)).

## Runtime

~59 seconds for 16,421 rows on the reference hardware (see the top-level
[`README.md`](../README.md)):

| Resource | Count |
|----------|-------|
| Patient | 2,430 (de-duplicated from 16,421) |
| Encounter | 16,421 |
| Condition | 11,458 |
| Observation | 345,870 |
| **Total** | **376,179** |

## Synthetic sample

A small **synthetic** ADNIMERGE input (48 rows across 12 subjects, no real
ADNI data — all subject identifiers use the `SYNTHETIC-001`–`SYNTHETIC-012`
prefix and all clinical values are fabricated) is shipped in
`sample/adnimerge_synthetic.csv`. It carries the same column shape as a real
ADNIMERGE CSV, so `transform_adni_csv.py` can be run end-to-end without ADNI
access (see [Try it without ADNI data](#try-it-without-adni-data) below). The
resulting FHIR output mirrors the real pipeline's shape (identifier-based
references, `type.text: "PTID"` on subjects, SNOMED/LOINC codings). See
[`sample/README.md`](sample/README.md) for details.

## Data availability

**This directory contains no ADNI data.** `ADNIMERGE_07Jan2026.csv` (the full
input) and `transformed/` (the derived FHIR outputs) are not shipped. ADNI
data are de-identified and distributed through the
[LONI Image and Data Archive (IDA)](https://ida.loni.usc.edu) under the
[ADNI Data Use Agreement](https://adni.loni.usc.edu/wp-content/themes/adni_2023/documents/ADNI_Data_Use_Agreement.pdf),
which prohibits redistribution of participant-level data (raw or derived).
Researchers can request access at
[adni.loni.usc.edu/data-samples/adni-data](https://adni.loni.usc.edu/data-samples/adni-data/).

The `mappings/` directory contains copies of the LLM-authored JSONata
expressions from Stage 2 (shipped for reproducibility); the synthetic sample
in `sample/adnimerge_synthetic.csv` contains no real ADNI data — all
identifiers and clinical values are fabricated.
