# EAI — ADNI to FHIR via LLM-Powered ETL

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22215565.svg)](https://doi.org/10.5281/zenodo.22215565)

An Extract, AI-Process, Integrate (EAI) pipeline that transforms the ADNI
(Alzheimer's Disease Neuroimaging Initiative) dataset into HL7 FHIR R4
resources using a locally-deployed large language model (Llama 3.1 8B via
Ollama). The pipeline is designed for on-premises deployment, keeping
sensitive patient data behind the institutional firewall.

Accompanies the manuscript: *"FHIR-EAI: Transforming ADNI dataset to FHIR
using LLM-Powered ETL with Ontoserver."*

---

## Three-stage architecture

| Stage | Directory | What it does | LLM? | Scale |
|-------|-----------|--------------|------|-------|
| 1 — Terminology Mapping | `Terminology/` | Maps 62 ADNI fields to LOINC/SNOMED CT via OntoServer; 19 unmapped fields → ADNI custom CodeSystem | Yes (Llama 3.1, temp 0.0) | 62 fields |
| 2 — Agentic JSONata Generation | `Mappings/` | ReAct loop authors JSONata mapping expressions; 4-layer validation; fail-soft at MAX_ITERS=4 | Yes (Llama 3.1 8B, temp 0.4) | 16-row sample |
| 3 — Transform | `Transform/` | Re-executes saved JSONata against the full CSV deterministically (no LLM) | No | Full 16,421-row dataset |

Stage 2 uses the LLM to **author** mappings on a small sample (cost, privacy);
Stage 3 applies those mappings to the full dataset deterministically (fast,
cheap, reproducible).

## Repository layout

```
EAI/
├── Terminology/          # Stage 1 — terminology mapping agent
│   ├── agent/            # Hybrid agent (LLM search + deterministic scoring)
│   ├── artifacts/agent/  # Pre-computed ConceptMaps + ADNI CodeSystem (shipped)
│   ├── config.yaml       # Defaults (cert paths blanked; see config.local.yaml)
│   ├── environment.yml   # Conda environment
│   ├── fields.json       # 62 ADNI field definitions
│   └── README.md         # Stage 1 documentation
├── Mappings/             # Stage 2 — agentic JSONata generation
│   ├── adni_react_pipeline.py   # Main pipeline (LangGraph ReAct loop)
│   ├── eval_jsonata.js          # Node/JSONata executor (shared with Stage 3)
│   ├── llm_*.jsonata            # LLM-authored mapping expressions
│   ├── terminology.md          # LOINC/SNOMED/ADNI code reference
│   ├── schema.json             # ADNI schema for the pipeline
│   ├── package.json            # Node dependency (jsonata)
│   ├── environment.yml         # Conda environment (Python + Node.js)
│   ├── requirements.txt        # pip alternative to the conda env
│   └── *.md                    # Evaluation post-mortems + status logs
└── Transform/            # Stage 3 — deterministic transform
    ├── transform_adni_csv.py   # Full-dataset transform (no LLM)
    ├── schema.json             # ADNI schema (same structure as Mappings/)
    ├── mappings/               # Copy of Stage 2 JSONata outputs
    ├── environment.yml         # Conda environment (Python + Node.js)
    ├── requirements.txt        # Stdlib-only Python (pip fallback)
    ├── sample/                 # Synthetic FHIR sample (no real ADNI data)
    └── README.md               # Stage 3 documentation
```

## Hardware & runtime

- **CPU:** Intel Core i7-11800H @ 2.30GHz (8c/16t, up to 4.6 GHz)
- **GPU:** NVIDIA GeForce RTX 3060 Laptop, 6 GB VRAM (Ollama/llama3.1)
- **RAM:** 32 GB, NVMe SSD
- **OS:** Ubuntu 22.04 (Linux 6.8)
- **LLM:** Llama 3.1 (8B) served locally via Ollama, temperature 0.4 (Stage 2) / 0.0 (Stage 1)

Stage 3 (Transform) is CPU-bound; the GPU is idle.

## Prerequisites

- [Ollama](https://ollama.ai) installed and running locally
- [Node.js](https://nodejs.org/) >= 18
- Python >= 3.10
- [Conda](https://docs.conda.io/) (for all stages)

```bash
# Pull the LLM model (used by Stages 1 and 2)
ollama pull llama3.1
```

## Stage 1 — Terminology Mapping

Maps ADNI clinical fields to standard terminologies (LOINC/SNOMED CT) using a
hybrid agent: LLM-generated search queries, FHIR terminology expansion against
[OntoServer](https://ontoserver.mii-termserv.de), deterministic scoring, and
LLM-based semantic evaluation.

```bash
cd Terminology
conda env create -f environment.yml
conda activate adni-agent

# OntoServer requires client certificates. Create config.local.yaml:
#   terminology_server:
#     client_cert_path: "/path/to/your/cert.crt"
#     client_key_path: "/path/to/your/key.pem"

python -m agent.run                  # Run all 62 fields
python -m agent.run --field MMSE     # Run a single field
python -m agent.run --status        # Check completion status
```

Pre-computed outputs (ConceptMaps, ADNI CodeSystem, mapping report) are in
`Terminology/artifacts/agent/` so Stages 2/3 can run without re-hitting
OntoServer.

See `Terminology/README.md` for details.

## Stage 2 — Agentic JSONata Generation

Uses a ReAct (Reason–Act–Observe) loop with Llama 3.1 8B to author JSONata
mapping expressions that transform ADNI CSV rows into FHIR resources. The
pipeline runs on a 16-row sample (`adnimerge_small.csv`, **not included** —
obtain via ADNI LONI-IDA). MAX_ITERS=4 (1 initial + 3 retries) with fail-soft;
a 4-layer validation stack (normalize / programmatic+terminology whitelist /
optional HAPI R4 / LLM critic) gates each candidate.

```bash
cd Mappings
conda env create -f environment.yml
conda activate adni-mappings         # Python + Node.js in one env
npm install                          # installs jsonata ^2.2.2

# Place adnimerge_small.csv here (16-row ADNI sample, obtained via LONI-IDA)
python adni_react_pipeline.py
```

The `requirements.txt` is kept as a pip/venv fallback for users who prefer not
to use conda (run `pip install -r requirements.txt` and install
[Node.js](https://nodejs.org/) >= 18 separately).

Outputs: `llm_*.jsonata` mapping files + `out_*.json` (sample results) +
`timing_summary.json` (per-node timing).

## Stage 3 — Transform (full dataset)

Re-executes the saved JSONata mappings against the full ADNIMERGE CSV
deterministically — no LLM, no network calls. Patient de-duplication
(16,421 rows → 2,430 unique). Produces FHIR resources as per-type JSON files
plus a combined bundle.

```bash
cd Transform
conda env create -f environment.yml
conda activate adni-transform         # Python + Node.js in one env

# Place ADNIMERGE_07Jan2026.csv here (obtained via LONI-IDA)

# Requires eval_jsonata.js + node_modules/jsonata from Stage 2:
# (run `npm install` in ../Mappings first if you haven't)
python transform_adni_csv.py \
    --csv ADNIMERGE_07Jan2026.csv \
    --schema schema.json \
    --mappings-dir ../Mappings \
    --out-dir ./transformed
```

The `requirements.txt` is kept as a pip/venv fallback (Transform itself is
Python-stdlib-only; you still need [Node.js](https://nodejs.org/) >= 18 and
`node_modules/jsonata` from Stage 2).

Runtime: ~59 seconds for 16,421 rows (Patient 2,430 / Encounter 16,421 /
Condition 11,458 / Observation 345,870 / Total 376,179).

## Data availability

**This repository contains no ADNI data.** ADNI data are de-identified and
distributed through the [LONI Image and Data Archive
(IDA)](https://ida.loni.usc.edu) under the [ADNI Data Use
Agreement](https://adni.loni.usc.edu/wp-content/themes/adni_2023/documents/ADNI_Data_Use_Agreement.pdf),
which prohibits redistribution of participant-level data (raw or derived).
Researchers can request access at
[adni.loni.usc.edu/data-samples/adni-data](https://adni.loni.usc.edu/data-samples/adni-data/).

A small **synthetic** FHIR sample (no real ADNI data) is included in
`Transform/sample/` for testing downstream tooling.

## License

[MIT](LICENSE)
