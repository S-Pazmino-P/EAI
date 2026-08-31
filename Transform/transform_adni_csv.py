"""
transform_adni_csv.py

Apply the JSONata mapping files already produced by adni_react_pipeline.py
(llm_patient.jsonata, llm_encounter.jsonata, llm_condition.jsonata, and the
llm_observation.jsonata files) to a NEW CSV that has
the same column structure as ADNIMERGE_07Jan2026.csv.

This does NOT call an LLM and does NOT derive any mapping it just
re executes the saved expressions against new rows via the same Node/
JSONata executor (eval_jsonata.js) the pipeline itself uses. Use this once
you're happy with the mappings a pipeline run produced and want to apply
them to more data without rerunning generation/validation.

Usage:
    python transform_adni_csv.py \
        --csv new_data.csv \
        --schema schema.json \
        --mappings-dir . \
        --out-dir ./transformed

Requires eval_jsonata.js + node_modules/jsonata to be present in the
directory eval_jsonata.js is run from (same requirement as the pipeline).
"""
from __future__ import annotations
import argparse, csv, glob, json, os, subprocess, sys, time
from typing import Optional


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Row loading — identical coercion logic to adni_react_pipeline.py's
# prepare(), so a mapping written against the pipeline's row shape behaves
# the same way here (missing/empty cells -> JSON null, ints/numbers coerced
# per schema.json, everything else left as a string).
# ---------------------------------------------------------------------------
def load_rows(csv_path: str, schema_path: str) -> tuple[list[dict], list[str], list[str]]:
    schema = json.load(open(schema_path, encoding="utf-8"))
    fields = list(schema["properties"].keys())

    def coerce(f, v):
        if v is None or v.strip() == "":
            return None
        t = schema["properties"][f].get("type", "string")
        if t in ("integer", "number"):
            try:
                n = float(v)
                return int(n) if t == "integer" and n.is_integer() else n
            except ValueError:
                return v
        return v

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        csv_columns = reader.fieldnames or []
        recs = list(reader)

    missing = [f for f in fields if f not in csv_columns]
    extra = [c for c in csv_columns if c not in fields]
    rows = [{fld: coerce(fld, r.get(fld)) for fld in fields} for r in recs]
    return rows, missing, extra


# ---------------------------------------------------------------------------
# Execute one saved JSONata expression against all rows via the same Node
# executor the pipeline uses, and flatten results the same way _execute()
# does in adni_react_pipeline.py (ternary-array-of-arrays -> flat list).
# ---------------------------------------------------------------------------
def run_expression(expression: str, rows: list[dict], eval_js_path: str) -> tuple[list, Optional[str]]:
    payload = json.dumps({"expression": expression, "rows": rows})
    proc = subprocess.run(["node", eval_js_path], input=payload,
                           capture_output=True, text=True,
                           cwd=os.path.dirname(os.path.abspath(eval_js_path)) or ".")
    if proc.returncode != 0:
        try:
            err = json.loads(proc.stderr)["error"]
        except Exception:
            err = proc.stderr.strip() or "unknown node error"
        return [], f"JSONata execution failed: {err}"

    per_row = json.loads(proc.stdout)
    out: list = []
    for r in per_row:
        if r is None:
            continue
        if isinstance(r, list):
            for item in r:
                if item is not None:
                    if isinstance(item, list):
                        out.extend(item)
                    else:
                        out.append(item)
        else:
            out.append(r)
    return out, None


def find_observation_mapping_files(mappings_dir: str) -> list[str]:
    per_category = sorted(glob.glob(os.path.join(mappings_dir, "llm_observation_*.jsonata")))
    if per_category:
        return per_category
    combined = os.path.join(mappings_dir, "llm_observation.jsonata")
    if os.path.exists(combined):
        log("WARNING: no per-category llm_observation_<category>.jsonata files found; "
            "falling back to llm_observation.jsonata, which may not be a single "
            "valid expression if it was written as a labeled multi-category file.")
        return [combined]
    return []


def normalize_resources(target: str, resources: list) -> list:

    if target != "Patient":
        return resources
    seen: set = set()
    out: list = []
    for r in resources:
        ident = r.get("identifier") if isinstance(r, dict) else None
        key = None
        if isinstance(ident, list) and ident:
            key = ident[0].get("value") if isinstance(ident[0], dict) else None
        elif isinstance(ident, dict):
            key = ident.get("value")
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True, help="Path to the new ADNI-shaped CSV to transform")
    ap.add_argument("--schema", required=True, help="Path to schema.json (defines fields/types)")
    ap.add_argument("--mappings-dir", default=".",
                     help="Directory containing llm_patient.jsonata, llm_encounter.jsonata, "
                          "llm_condition.jsonata, and llm_observation_<category>.jsonata files "
                          "(default: current directory)")
    ap.add_argument("--eval-js", default=None,
                     help="Path to eval_jsonata.js (default: <mappings-dir>/eval_jsonata.js)")
    ap.add_argument("--out-dir", default="./transformed", help="Output directory")
    args = ap.parse_args()

    eval_js = args.eval_js or os.path.join(args.mappings_dir, "eval_jsonata.js")
    if not os.path.exists(eval_js):
        log(f"ERROR: eval_jsonata.js not found at {eval_js!r}. "
            f"Pass --eval-js or place it in --mappings-dir.")
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)

    log("PHASE 1/3: LOADING — reading CSV and coercing types per schema.json")
    rows, missing, extra = load_rows(args.csv, args.schema)
    log(f"LOADING: read {len(rows)} rows from {args.csv}")
    if missing:
        log(f"LOADING: WARNING — {len(missing)} schema field(s) absent from this CSV "
            f"(will be treated as null for every row): {missing}")
    if extra:
        log(f"LOADING: {len(extra)} extra CSV column(s) not in schema.json will be ignored: {extra}")

    log("PHASE 2/3: TRANSFORM — applying saved JSONata mappings")
    all_bundle_entries: list = []
    summary: dict[str, int] = {}

    # Patient / Encounter / Condition — one mapping file each.
    single_targets = [
        ("Patient", os.path.join(args.mappings_dir, "llm_patient.jsonata")),
        ("Encounter", os.path.join(args.mappings_dir, "llm_encounter.jsonata")),
        ("Condition", os.path.join(args.mappings_dir, "llm_condition.jsonata")),
    ]
    for target, path in single_targets:
        if not os.path.exists(path):
            log(f"TRANSFORM [{target}]: SKIPPED — mapping file not found: {path}")
            continue
        log(f"TRANSFORM [{target}]: running {os.path.basename(path)} against {len(rows)} rows...")
        expr = open(path, encoding="utf-8").read()
        resources, err = run_expression(expr, rows, eval_js)
        if err:
            log(f"TRANSFORM [{target}]: FAILED — {err}")
            summary[target] = 0
            continue
        before = len(resources)
        resources = normalize_resources(target, resources)
        if before != len(resources):
            log(f"NORMALIZE [{target}]: de-duplicated {before} -> {len(resources)} (removed {before - len(resources)} duplicates)")
        log(f"TRANSFORM [{target}]: produced {len(resources)} resource(s)")
        summary[target] = len(resources)
        all_bundle_entries.extend(resources)
        out_path = os.path.join(args.out_dir, f"out_{target.lower()}.json")
        json.dump(resources, open(out_path, "w", encoding="utf-8"), indent=2)

    # Observation — one mapping file per category, results concatenated.
    obs_files = find_observation_mapping_files(args.mappings_dir)
    if not obs_files:
        log("TRANSFORM [Observation]: SKIPPED — no llm_observation*.jsonata files found")
    else:
        log(f"TRANSFORM [Observation]: found {len(obs_files)} category mapping file(s)")
        obs_all: list = []
        for path in obs_files:
            category = os.path.basename(path).replace("llm_observation_", "").replace(".jsonata", "")
            log(f"TRANSFORM [Observation/{category}]: running against {len(rows)} rows...")
            expr = open(path, encoding="utf-8").read()
            resources, err = run_expression(expr, rows, eval_js)
            if err:
                log(f"TRANSFORM [Observation/{category}]: FAILED — {err}")
                continue
            log(f"TRANSFORM [Observation/{category}]: produced {len(resources)} resource(s)")
            obs_all.extend(resources)
        summary["Observation"] = len(obs_all)
        all_bundle_entries.extend(obs_all)
        out_path = os.path.join(args.out_dir, "out_observation.json")
        json.dump(obs_all, open(out_path, "w", encoding="utf-8"), indent=2)

    log("PHASE 3/3: WRITING — assembling combined FHIR Bundle")
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": r} for r in all_bundle_entries],
    }
    bundle_path = os.path.join(args.out_dir, "bundle.json")
    json.dump(bundle, open(bundle_path, "w", encoding="utf-8"), indent=2)
    log(f"WRITING: wrote combined bundle ({len(all_bundle_entries)} resources) -> {bundle_path}")

    log("DONE.")
    log("Summary: " + ", ".join(f"{k}={v}" for k, v in summary.items()))


if __name__ == "__main__":
    main()
