# Synthetic ADNIMERGE Sample

This directory contains a **synthetic** ADNIMERGE CSV for exercising
`Transform/transform_adni_csv.py` end-to-end without ADNI data access. It
contains no real ADNI data — all subject identifiers use the `SYNTHETIC-001`–
`SYNTHETIC-012` prefix and all clinical values are fabricated.

## Contents

`adnimerge_synthetic.csv` — a 48-row synthetic ADNIMERGE input:

| Property | Value |
|----------|-------|
| Rows | 48 |
| Columns | 116 (ADNIMERGE schema subset) |
| Subjects | 12 (`SYNTHETIC-001` … `SYNTHETIC-012`) |
| Visits | `bl`, `m6`, `m12`, `m24`, `m36`, `m48` |
| DX mix | Dementia (32), CN (9), MCI (7) |
| Imaging IDs | `IMAGEUID` 9000001–9000048, `IMAGEUID_bl` 9100001–9100048 (fabricated) |

The column layout matches a real ADNIMERGE CSV, so the transform's `load_rows()`
coercion (per `schema.json`) and the Stage 2 JSONata mappings behave the same
way they do on real data.

## Running the transform

From the `Transform/` directory:

```bash
python transform_adni_csv.py \
    --csv sample/adnimerge_synthetic.csv \
    --schema schema.json \
    --mappings-dir ./mappings \
    --eval-js ../Mappings/eval_jsonata.js \
    --out-dir ./transformed
```

This produces (in `transformed/`):

| Resource | Count |
|----------|-------|
| Patient | 12 (de-duplicated from 48) |
| Encounter | 48 |
| Condition | 48 |
| Observation | 1,757 |
| **Total** | **1,865** |

## Validating

```bash
python3 -c "import csv; r=list(csv.DictReader(open('adnimerge_synthetic.csv'))); print(f'{len(r)} rows, {len(r[0])} cols, {len(set(x[\"PTID\"] for x in r))} subjects OK')"
```
