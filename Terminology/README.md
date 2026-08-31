# ADNI Terminology Mapping Agent

A hybrid agent system that maps ADNI (Alzheimer's Disease Neuroimaging Initiative) clinical fields to standard terminologies (LOINC/SNOMED) using a combination of deterministic FHIR terminology services and LLM-based semantic evaluation.

## Overview

ADNI collects extensive clinical data with 62 unique fields. This project automates the mapping of these fields to standardized codes through:

1. **LLM Search Term Generation** - Generates multiple search queries for each field
2. **FHIR Terminology Expansion** - Queries LOINC value sets via OntoServer
3. **Deterministic Scoring** - Ranks candidates using rule-based scoring
4. **LLM Evaluation** - Context-aware semantic evaluation of top candidates

## Project Structure

```
.
├── agent/                      # Main agent code
│   ├── hybrid/                 # Hybrid pipeline
│   │   ├── llm_terms.py        # LLM search term generation
│   │   ├── scorer.py           # Deterministic scoring
│   │   ├── evaluator.py        # LLM candidate evaluation
│   │   ├── thresholds.py       # Decision thresholds
│   │   ├── runner.py           # Pipeline orchestrator
│   │   └── report_generator.py # Mapping report generation
│   ├── terminology/            # FHIR terminology client
│   │   ├── client.py           # TerminologyClient (expand/lookup/subsumes)
│   │   └── models.py           # Pydantic models
│   └── run.py                  # CLI entry point
├── artifacts/agent/            # Generated outputs
├── fields.json                 # ADNI field definitions (62 fields)
├── config.yaml                 # Configuration (Ollama + OntoServer)
└── environment.yml             # Conda environment
```

## Configuration

### Ollama (LLM)
```yaml
ollama:
  base_url: "http://localhost:11434"
  model: "llama3.1:latest"
  temperature: 0.0
```

### FHIR Terminology Server
```yaml
terminology_server:
  base_url: "https://ontoserver.mii-termserv.de/fhir"
  timeout_seconds: 15
```

## Usage

### Setup
```bash
conda env create -f environment.yml
conda activate adni-agent
```

### Run All Fields
```bash
python -m agent.run
```

### Run Single Field
```bash
python -m agent.run --field MMSE
python -m agent.run --field PIB
python -m agent.run --field FDG
```

### Check Status
```bash
python -m agent.run --status
```

## Output

### Per-Field Outputs
Each field generates:
- `{FIELD}.conceptmap.json` - FHIR ConceptMap resource
- `{FIELD}.audit.json` - Detailed audit trail with:
  - Search terms used
  - Expansion results
  - Top candidates with scores
  - LLM evaluation
  - Decision report

### Generated Reports
After running all fields, the following are generated:
- `mapping-report.md` - Complete mapping table for all 62 fields
- `adni-codesystem.json` - FHIR CodeSystem for unmapped fields

## Decision Logic

| Decision | Threshold | Description |
|----------|-----------|-------------|
| `mapped` | Score >= 0.8 | High confidence mapping |
| `human_review` | 0.6 <= Score < 0.8 | Requires manual review |
| `no_mapping` | Score < 0.6 | No suitable match found |

## Scoring (Deterministic)

| Factor | Weight | Description |
|--------|--------|-------------|
| System match | 0.3 | Same code system |
| Not LP-prefix | 0.2 | Standard LOINC (not local) |
| Numeric code | 0.2 | Official LOINC number |
| Has properties | 0.2 | Additional metadata |
| Display match | 0.1 | Field name in display |

## LLM Evaluation

The evaluator considers:
1. **Semantic Match** - Exact, HIGH, MEDIUM, LOW, NONE
2. **Method Compatibility** - PET vs CSF vs plasma vs blood
3. **Clinical Validity** - Would ADNI researchers accept this?

When a "perfect fit" is found (score 1.0), a detailed report is generated in the audit JSON.

## Field Categories

- **62 total fields** in ADNI
- **43 fields** use agent path (require terminology mapping)
  - `quantitative-observation` - Lab values, imaging metrics
  - `assessment-instrument` - Cognitive tests, questionnaires
- **19 fields** are metadata/identifiers (skip agent, go directly to ADNI codesystem)
  - RID, PTID, SITE, VISCODE, EXAMDATE, COLPROT, ORIGPROT, FLDSTRENG, FSVERSION, IMAGEUID, ICV

## Example Mappings

| ADNI Field | LOINC Code | Description |
|------------|------------|-------------|
| MMSE | 72107-6 | Mini-Mental State Examination |
| PIB | LP428286-1 | Amyloid plaques probability score |
| FDG | - | No suitable LOINC code (brain PET) - added to ADNI codesystem |

## Unmapped Fields

Fields without standard LOINC/SNOMED mappings are automatically added to the ADNI custom codesystem:
- Demographics (PTGENDER, PTETHCAT, PTRACCAT, PTMARRY)
- Identifiers (RID, PTID, SITE, VISCODE, IMAGEUID)
- MRI volumes (Ventricles, Hippocampus, WholeBrain, Entorhinal, Fusiform, MidTemp)
- PET tracers (AV45, FBB - when no mapping found)
- Cognitive tests (ADAS11, ADAS13, ADASQ4, etc.)

The mapping report (`mapping-report.md`) provides the complete categorization of all 62 fields.
