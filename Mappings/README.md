# ADNI Agentic JSONata Generation

Stage 2 of the EAI pipeline. A ReAct (Reason-Act-Observe) loop uses Llama 3.1
8B via Ollama to author JSONata mapping expressions that transform ADNI CSV
rows into HL7 FHIR R4 resources. Each candidate expression is executed against
a 16-row ADNI sample and gated by a deterministic 4-layer validation stack;
failures feed repair feedback back to the LLM up to `MAX_ITERS` (default 4),
with best-attempt fail-soft retention so work is never discarded on a hard
failure.

The LLM-authored expressions saved here are re-used deterministically by
[Stage 3 (Transform)](../Transform/) against the full 16,421-row dataset — no
LLM involved.

## Overview

The pipeline (`pipeline/adni_react_pipeline.py`) builds a LangGraph `StateGraph` that
produces four FHIR resource types sequentially:

```
prepare → Patient → Encounter → Condition → Observation (9 categories) → finalize
```

For each resource type (and each Observation category), the graph runs the
ReAct cycle:

```
generate  →  execute  →  validate  ──PASS──►  advance
                          (issues)  ──retry──► generate (with feedback, until MAX_ITERS)
```

- **generate** — the LLM authors (or repairs) a JSONata expression from the
  field spec, the `JSONATA_RULES` lessons, and prior validation feedback.
- **execute** — the expression runs against the sample CSV rows via
  `node eval_jsonata.js` (the same Node `jsonata` engine Stage 3 reuses).
- **validate** — a layered, authority-ordered check stack scores the output
  and decides retry vs. proceed (see [Validation stack](#validation-stack)).

## Project Structure

```
.
├── pipeline/
│   ├── adni_react_pipeline.py   # Main pipeline (LangGraph StateGraph)
│   └── eval_jsonata.js          # Node/JSONata executor (shared with Stage 3)
├── inputs/
│   ├── schema.json              # ADNI CSV column definitions (types + enums)
│   ├── terminology.md           # LOINC/SNOMED/ADNI code reference (from Stage 1)
│   └── adnimerge_small.csv      # 16-row ADNI sample input (NOT shipped — see "Data availability")
├── results/
│   ├── llm_*.jsonata            # LLM-authored mapping expressions (shipped)
│   ├── out_*.json               # FHIR resources produced for the 16-row sample (NOT shipped)
│   └── timing_summary.json      # Per-node timing from the last run
├── environment.yml              # Conda environment (Python + Node.js)
├── requirements.txt             # pip alternative to the conda env
├── package.json                 # Node dependency (jsonata ^2.2.2)
└── README.md
```

All paths in `adni_react_pipeline.py` resolve relative to the script's own
location, so it can be invoked from any working directory. Inputs are read
from `inputs/` and outputs are written to `results/`. A placeholder
(`inputs/adnimerge_small.csv.placeholder`) marks where the sample CSV must be
placed before running.

## Architecture

### Sequential resource production

| Resource | Notes |
|----------|-------|
| Patient | Single generate→execute→validate cycle. |
| Encounter | Single cycle. |
| Condition | Single cycle; conditional output (DX present). |
| Observation | Nested loop over 9 metadata categories (genetic, pet, csf, cognitive, memory, ecog-participant, ecog-studypartner, mri-volumetric, composite), each with its own ReAct retry loop. |

### Best-attempt retention (fail-soft)

`_validate` never discards work on a hard failure: each successfully executed
candidate is scored by issue count; the lowest-issue candidate is retained in
`best_*` state fields. On the final iteration the best candidate is restored
rather than aborting, so a remaining validation issue is reported in logs but
does not crash the run. There is no deterministic fallback for Observation —
whatever the LLM produced (passing, or after exhausting `MAX_ITERS`, failing)
is stored.

### Retry gate

`_retry_or_proceed` gates on deterministic checks rather than the LLM critic:
`iteration >= MAX_ITERS` → proceed; `exec_error` → retry;
`__last_issues__` non-empty → retry; otherwise proceed. Programmatic-clean
output is accepted even if the critic says FAIL — the `"fail"` edge key is a
defensive duplicate of the proceed target and is never returned in practice.

## Configuration

### LLM

| Setting | Value | Location |
|---------|-------|----------|
| Model | `llama3.1` (8B, via Ollama) | `pipeline/adni_react_pipeline.py` |
| Temperature | 0.4 | `pipeline/adni_react_pipeline.py` |
| Ollama base URL | `http://localhost:11434` (default) | `langchain_ollama` default |

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MAX_ITERS` | `4` | ReAct retry budget per resource/category (1 initial + 3 retries). |
| `FHIR_VALIDATOR_JAR` | (empty) | Path to the HAPI/HL7 FHIR R4 validator JAR. Enables the optional authoritative validator layer; deterministic FHIR/ADNI checks stay active regardless. |
| `FHIR_VALIDATOR_VERSION` | `4.0.1` | FHIR R4 version passed to the HAPI validator. |

## Usage

### Setup

```bash
conda env create -f environment.yml
conda activate adni-mappings        # Python + Node.js in one env
npm install                         # installs jsonata ^2.2.2

# Start Ollama and pull the model (used by Stages 1 and 2)
ollama pull llama3.1
```

A pip/venv fallback is provided for users who prefer not to use conda:

```bash
pip install -r requirements.txt      # Python deps
# Install Node.js >= 18 separately, then:
npm install
```

### Run the pipeline

```bash
# Place the 16-row ADNI sample at inputs/adnimerge_small.csv (see "Data availability")
python pipeline/adni_react_pipeline.py
```

### Optional: enable the HAPI FHIR R4 validator

```bash
export FHIR_VALIDATOR_JAR=/path/to/validator-cli.jar
python pipeline/adni_react_pipeline.py
```

## Outputs

All pipeline outputs are written to `results/`.

| File | Description |
|------|-------------|
| `results/llm_patient.jsonata` | LLM-authored Patient mapping expression. |
| `results/llm_encounter.jsonata` | LLM-authored Encounter mapping expression. |
| `results/llm_condition.jsonata` | LLM-authored Condition mapping expression. |
| `results/llm_observation.jsonata` | Combined Observation mapping expression (assembled from per-category expressions in `finalize`). |
| `results/llm_observation_{unit}.jsonata` | Per-category Observation expressions (imaging-1..3, plain-1..6, string-numeric-ABETA/ADAS11/PTAU/TAU). |
| `results/out_*.json` | FHIR resources produced for the 16-row sample (not shipped — derived/restricted). |
| `results/timing_summary.json` | Per-node call count, total/avg time (ms) from the last run. |

The `llm_*.jsonata` files are the inputs to [Stage 3](../Transform/), which
re-executes them against the full dataset deterministically.

## Validation stack

`_validate` runs a layered, authority-ordered check pipeline. Deterministic
checks own resource structure, duplicate suppression, and imaging placement;
the LLM critic supplies repair wording only and never overrides a
deterministic failure.

1. **`_normalize_resources`** — contract-defined repairs: strip literal
   `"undefined"` values, set missing `resourceType`, drop duplicate IDs, drop
   standalone imaging-metadata Observations (FSVERSION/FLDSTRENG/IMAGEUID),
   and deterministically enrich MRI Observations with `method`/`extension`/
   `derivedFrom` from the source row.
2. **`_programmatic`** — structural checks: `resourceType` match, well-formed
   IDs, no literal `undefined`, allowed coding systems (`ALLOWED_SYS`), and
   per-target shape rules (Patient identifier, Condition `code.coding`,
   expected Observation IDs).
3. **`_validate_with_hapi`** — optional authoritative HAPI/HL7 FHIR R4
   validator, enabled only when `FHIR_VALIDATOR_JAR` is set.
4. **LLM critic** — `Verdict` structured output supplies repair wording only;
   deterministic + FHIR results remain authoritative.

## Further documentation

- [`inputs/terminology.md`](inputs/terminology.md) — LOINC/SNOMED/ADNI code
  reference produced by [Stage 1](../Terminology/).

## Data availability

**This directory contains no ADNI data.** `inputs/adnimerge_small.csv` (the
16-row sample input) and `results/out_*.json` (derived FHIR outputs) are not
shipped; a placeholder (`inputs/adnimerge_small.csv.placeholder`) marks where
the sample CSV must be placed. ADNI data are de-identified and distributed
through the [LONI Image and Data Archive (IDA)](https://ida.loni.usc.edu) under
the
[ADNI Data Use Agreement](https://adni.loni.usc.edu/wp-content/themes/adni_2023/documents/ADNI_Data_Use_Agreement.pdf),
which prohibits redistribution of participant-level data (raw or derived).
Researchers can request access at
[adni.loni.usc.edu/data-samples/adni-data](https://adni.loni.usc.edu/data-samples/adni-data/).
