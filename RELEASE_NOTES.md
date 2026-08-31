# Release Notes

All notable releases of **EAI — ADNI to FHIR via LLM-Powered ETL** are documented
in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-08-31

First public release. Accompanies the manuscript *"FHIR-EAI: Transforming ADNI
dataset to FHIR using LLM-Powered ETL with Ontoserver,"* submitted to *The
Journal of Precision Medicine: Health and Disease.*

EAI is an **Extract, AI-Process, Integrate** pipeline that transforms the ADNI
(Alzheimer's Disease Neuroimaging Initiative) dataset into HL7 FHIR R4
resources using a locally-deployed Llama 3.1 (8B) model via Ollama. It is
designed for on-premises deployment, keeping sensitive patient data behind the
institutional firewall.

### Added — Three-stage architecture

- **Stage 1 — Terminology Mapping (`Terminology/`)**: a hybrid agent (LLM
  search + FHIR terminology expansion against [OntoServer](https://ontoserver.mii-termserv.de)
  + deterministic scoring + LLM semantic evaluation) maps all 62 ADNI fields.
  Result: **27 fields mapped to standard LOINC/SNOMED CT** codes and **35
  fields** (incl. 19 originally unmapped) added to a generated **ADNI custom
  CodeSystem**. LLM at temperature 0.0. Decision thresholds: `mapped` ≥ 0.8,
  `human_review` 0.6–0.8, `no_mapping` < 0.6.
- **Stage 2 — Agentic JSONata Generation (`Mappings/`)**: a LangGraph `StateGraph`
  runs a ReAct (Reason–Act–Observe) loop where Llama 3.1 8B (temperature 0.4)
  authors JSONata mapping expressions on a 16-row ADNI sample. Each candidate
  is gated by a 4-layer validation stack (normalize → programmatic + terminology
  whitelist → optional HAPI R4 validator → LLM critic), with best-attempt
  fail-soft retention at `MAX_ITERS=4` (1 initial + 3 retries). Produces
  Patient → Encounter → Condition → Observation (9 metadata categories).
- **Stage 3 — Transform (`Transform/`)**: re-executes the saved JSONata
  expressions against the full ADNIMERGE CSV **deterministically** — no LLM,
  no network calls — using the same Node/`jsonata` engine as Stage 2. Patient
  de-duplication by identifier; per-type JSON + combined FHIR Bundle output.

### Performance

- **Stage 2 pipeline total**: 609,221 ms (~10.2 min) on the 16-row sample
  (see `Mappings/results/timing_summary.json`); the Observation ReAct loop
  accounts for the bulk (25 generate calls, ~514.7 s).
- **Stage 3 runtime**: ~59 seconds for the full 16,421-row dataset on the
  reference hardware.

| FHIR resource | Count |
|---------------|-------|
| Patient (de-duplicated) | 2,430 |
| Encounter | 16,421 |
| Condition | 11,458 |
| Observation | 345,870 |
| **Total** | **376,179** |

### Shipped artifacts

- Pre-computed **ConceptMaps**, per-field **audit trails**, the **ADNI
  CodeSystem**, and the **mapping report** (`Terminology/artifacts/agent/`) —
  so Stages 2/3 can run without re-hitting OntoServer.
- LLM-authored **JSONata mapping expressions** (`Mappings/results/llm_*.jsonata`,
  mirrored in `Transform/mappings/`).
- **`timing_summary.json`** with per-node call counts and total/average times.
- A **synthetic 48-row ADNIMERGE sample** (`Transform/sample/`) so the full
  transform can be exercised end-to-end without ADNI access (produces 12
  Patients, 48 Encounters, 48 Conditions, 1,757 Observations).
- Citation metadata: `CITATION.cff` and `.zenodo.json` for the Zenodo deposition.

### Tech stack

- **LLM**: Llama 3.1 (8B) served locally via [Ollama](https://ollama.ai)
- **Agent framework**: LangGraph (`StateGraph`, ReAct loop)
- **Standards**: HL7 FHIR R4, JSONata (`jsonata ^2.2.2`)
- **Terminology**: OntoServer (FHIR R4 terminology services)
- **Runtimes**: Python ≥ 3.10, Node.js ≥ 18, [Conda](https://docs.conda.io/)
- **Reference hardware**: Intel Core i7-11800H, NVIDIA RTX 3060 Laptop (6 GB
  VRAM), 32 GB RAM, Ubuntu 22.04. Stage 3 is CPU-bound (GPU idle).

### Known limitations

- **No ADNI data is shipped.** ADNI data are de-identified and distributed
  through the [LONI Image and Data Archive (IDA)](https://ida.loni.usc.edu)
  under the ADNI Data Use Agreement, which prohibits redistribution. The
  16-row sample (`inputs/adnimerge_small.csv`) and full dataset
  (`ADNIMERGE_07Jan2026.csv`) must be obtained via LONI-IDA.
- OntoServer requires client certificates (configure `config.local.yaml`;
  paths are blanked in the shipped `config.yaml`).
- There is no deterministic fallback for Observation mappings — whatever the
  LLM produces (passing, or after exhausting `MAX_ITERS`) is retained.

### References

- Repository: <https://github.com/S-Pazmino-P/EAI>
- License: [MIT](LICENSE)
- Cite this release using [`CITATION.cff`](CITATION.cff).

[1.0.0]: https://github.com/S-Pazmino-P/EAI/releases/tag/v1.0.0
