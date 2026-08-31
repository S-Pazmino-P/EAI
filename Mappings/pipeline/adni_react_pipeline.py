from __future__ import annotations
import csv, json, logging, os, re, subprocess, tempfile
from time import time
from typing import TypedDict, Optional, Any
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUTS_DIR = os.path.join(SCRIPT_DIR, "..", "inputs")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "..", "results")
EVAL_JSONATA = os.path.join(SCRIPT_DIR, "eval_jsonata.js")


@dataclass
class NodeTiming:
    node: str
    start: float
    end: float = 0
    iteration: int = 0
    status: str = "running"

    @property
    def duration_ms(self) -> float:
        return (self.end - self.start) * 1000 if self.end else 0


_timings: dict[str, list[NodeTiming]] = {}

from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END

MODEL = "llama3.1"
MAX_ITERS = int(os.getenv("MAX_ITERS", "4"))
llm = ChatOllama(model=MODEL, temperature=0.4)

# Optional authoritative HAPI/HL7 FHIR R4 validator. Set FHIR_VALIDATOR_JAR
# to enable it; deterministic FHIR/ADNI checks remain active regardless.
FHIR_VALIDATOR_JAR = os.getenv("FHIR_VALIDATOR_JAR", "").strip()
FHIR_VALIDATOR_VERSION = os.getenv("FHIR_VALIDATOR_VERSION", "4.0.1").strip()

JSONATA_RULES = """\
You author JSONata (engine v2.x) expressions. Internalize these rules — every
one caused a real bug when ignored:

- OBJECT KEYS MUST BE QUOTED: always use "key": value, NEVER key: value (unquoted keys cause silent failure).
- EQUALITY IS = (single equals), NOT ==. Use: $.PTGENDER = "Male" ? "male" : "unknown"
- The pipe | in JSONata is for REGEX MATCHING, not "or" or defaulting. Do NOT use | for fallbacks.
- LOGICAL AND is "and", NOT &. Use: condition1 and condition2 (NOT condition1 & condition2)
- LOGICAL OR is "or", NOT |. Use: condition1 or condition2 (NOT condition1 | condition2)
- For conditional strings without else: cond ? "value" (no : branch gives undefined when false)
- For subtraction, convert strings to numbers: $number($substring(EXAMDATE,0,4)) - $number(AGE)
- Dot-path maps implicitly over arrays; `.( ... )` runs its block once per element.
- SEQUENCES: a 1-item result COLLAPSES to a bare value, not array[1]. Wrap the
  top-level output in [ ... ] when you need a guaranteed array. An empty sequence
  is `undefined` (absent) — never null, never [].
- CONTEXT `$` rebinds inside every `.( )` block to the current element. Before
  entering a nested map, capture the row: `$row := $;` then use `$row.RID`, NOT
  bare `RID` (bare refs silently resolve against the wrong object and return
  nothing — no error).
- Blocks: `( a; b; c )`, last expr is the result. `$x := v;` assigns.
- No `undefined` literal keyword exists. To emit "nothing" from a false ternary,
  OMIT the else branch entirely: `cond ? {...}`  (writing `: undefined` is a parse error).
- Arithmetic does NOT coerce strings. `$substring(...)` is a string; wrap in
  `$number(...)` before subtracting. `&` concatenates strings.
- Filters/predicates: `array[cond]`, 0-indexed `array[0]`, sort `array^(field)`
- NEVER use `$filter(...)` for predicates. Use the bracket predicate form `array[condition]` instead.
- Key builtins: $string, $number, $exists, $floor, $substring, $match(s,/re/),
  $lookup(obj, dynamicKey), $merge([o1,o2]) (later keys win), $count, $append.
- Drop empty extension slots with the pattern: [a, b, c][$exists($)].
- For conditional extensions with only "then" branch (no else): use ternary without else
- Return ONLY the JSONata expression inside one ```jsonata code block. No prose.
- Never emit the literal string "undefined" as a field value. Optional fields must be omitted.
- Do not invent resources, duplicate blocks, or standalone imaging metadata resources.
"""

ADNI = "http://adni.example.org/fhir/CodeSystem/adni-terms"
ENC_SYS = "http://adni.example.org/fhir/identifier/encounter"
OBS_SYS = "http://adni.example.org/fhir/identifier/observation"


def build_metadata() -> list[dict]:
    L, S = "http://loinc.org", "http://snomed.info/sct"

    def r(sf, cat, sys, code, disp, vt, sec=None, img=False):
        return {"sourceField": sf, "category": cat,
                "coding": {"system": sys, "code": code, "display": disp},
                "secondaryCoding": sec, "text": sf, "valueType": vt,
                "unit": None, "enrichWithImaging": img}

    t = [
        r("APOE4", "genetic", S, "1396588002", "APOE gene", "integer"),
        r("FDG", "pet", L, "86976-8", "PET+CT Brain metabolic", "decimal"),
        r("PIB", "pet", L, "87907-2", "PET+CT Brain for amyloidosis", "decimal",
          {"system": ADNI, "code": "PIB-SUVR-mean", "display": "Mean PIB SUVR"}),
        r("AV45", "pet", L, "87907-2", "PET+CT Brain for amyloidosis", "decimal",
          {"system": ADNI, "code": "AV45-SUVR-mean", "display": "Mean Florbetapir F-18 SUVR"}),
        r("FBB", "pet", L, "87907-2", "PET+CT Brain for amyloidosis", "decimal",
          {"system": ADNI, "code": "FBB-SUVR-mean", "display": "Mean Florbetaben F-18 SUVR"}),
        r("ABETA", "csf", L, "79058-4", "Amyloid beta 1-42 [Mass/volume] in CSF", "string-numeric"),
        r("TAU", "csf", L, "79059-2", "Tau protein [Mass/volume] in CSF", "string-numeric"),
        r("PTAU", "csf", L, "79060-0", "Phosphorylated tau [Mass/volume] in CSF", "string-numeric"),
        r("CDRSB", "cognitive", L, "72165-1", "Clinical Dementia Rating - Sum of Boxes [CDR-SB]", "decimal"),
        r("MMSE", "cognitive", L, "72107-6", "Mini-Mental State Examination [MMSE]", "integer"),
        r("MOCA", "cognitive", L, "72133-2", "Montreal Cognitive Assessment [MoCA]", "integer"),
        r("FAQ", "cognitive", L, "72198-2", "Functional Activities Questionnaire [FAQ]", "integer"),
        r("ADAS11", "cognitive", S, "714360001", "Alzheimer's Disease Assessment Scale score", "string-numeric"),
        r("ADAS13", "cognitive", S, "714360001", "Alzheimer's Disease Assessment Scale score", "decimal"),
        r("ADASQ4", "cognitive", S, "714360001", "Alzheimer's Disease Assessment Scale score", "integer"),
        r("RAVLT_immediate", "memory", S, "311478003", "California verbal learning test", "integer"),
        r("RAVLT_learning", "memory", S, "311478003", "California verbal learning test", "integer"),
        r("RAVLT_forgetting", "memory", ADNI, "RAVLT-forgetting", "RAVLT forgetting", "integer"),
        r("RAVLT_perc_forgetting", "memory", ADNI, "RAVLT-perc-forgetting", "RAVLT percent forgetting", "decimal"),
        r("LDELTOTAL", "memory", S, "273921009", "Wechsler memory scale", "integer"),
        r("DIGITSCOR", "memory", S, "273857000", "Symbol digit modalities test", "integer"),
        r("TRABSCOR", "memory", S, "273882000", "Trail making test", "decimal"),
        r("mPACCdigit", "composite", ADNI, "mPACCdigit", "Modified PACC with Digit Symbol", "decimal"),
        r("mPACCtrailsB", "composite", ADNI, "mPACCtrailsB", "Modified PACC with Trails B", "decimal"),
    ]
    for f in ["EcogPtMem", "EcogPtLang", "EcogPtVisspat", "EcogPtPlan", "EcogPtOrgan", "EcogPtDivatt", "EcogPtTotal"]:
        t.append(r(f, "ecog-participant", L, "89133-3",
                    "Everyday Cognition - Participant Self Report Form [ECog]", "decimal"))
    for f in ["EcogSPMem", "EcogSPLang", "EcogSPVisspat", "EcogSPPlan", "EcogSPOrgan", "EcogSPDivatt", "EcogSPTotal"]:
        t.append(r(f, "ecog-studypartner", L, "89090-5",
                    "Everyday Cognition - Study Partner Report Form [ECog.Partner]", "decimal"))
    for f, code, disp, vt in [
        ("Ventricles", "Brain-Volume-Ventricles", "MRI ventricular volume", "decimal"),
        ("Hippocampus", "Brain-Volume-Hippocampus", "MRI hippocampal volume", "decimal"),
        ("WholeBrain", "Brain-Volume-WholeBrain", "MRI whole brain volume", "integer"),
        ("Entorhinal", "Brain-Volume-Entorhinal", "MRI entorhinal cortex volume", "integer"),
        ("Fusiform", "Brain-Volume-Fusiform", "MRI fusiform gyrus volume", "integer"),
        ("MidTemp", "Brain-Volume-MidTemp", "MRI middle temporal gyrus volume", "integer"),
        ("ICV", "ICV", "Intracranial volume", "integer")]:
        t.append(r(f, "mri-volumetric", ADNI, code, disp, vt, img=True))
    return t


DX_TABLE = """DX -> SNOMED: CN=449888003 "Normal cognition"; AD=26929004 "Alzheimer's disease";
EMCI=386805003 & LMCI=386805003 "Mild neurocognitive disorder"; SMC=27350009 "Subjective memory complaint"."""

# ---------------------------------------------------------------------------
# Per-target authoring contracts. Patient/Encounter/Condition are unchanged
# from before; Observation is rewritten below (see _build_observation_prompt)
# to match plan.md's metadata-table-driven design instead of the flattened
# per-field ternary list that was here previously.
# ---------------------------------------------------------------------------
TARGETS = {
    "Patient": {
        "expected": 16, "kind": "object",
        "spec": f"""Input: ONE ADNIMERGE row. Output: ONE Patient resource (bare object).
- "identifier": [{{ "system": {ADNI!r}, "type": {{ "text": "PTID" }}, "value": $string($.PTID) }}]
- "gender": ternary $.PTGENDER = "Male" ? "male" : ($.PTGENDER = "Female" ? "female" : "unknown")
- "birthDate": (if EXAMDATE and AGE exist) $string($number($substring($.EXAMDATE,0,4)) - $floor($.AGE))
- "maritalStatus": (if PTMARRY exists) coding SNOMED 179159001, text = PTMARRY
- "extension": array of (PTETHCAT, PTRACCAT, PTEDUCAT) with drop-empty filter
Use $.field to access fields. Wrap output in [ ] to get array.""",
    },
    "Encounter": {
        "expected": 16, "kind": "object",
        "spec": f"""Input: ONE row. Output: ONE Encounter (bare object).
- "status": "finished", "class" with system http://terminology.hl7.org/CodeSystem/v3-ActCode code AMB
- "subject": {{ "identifier": {{ "system": {ADNI!r}, "type": {{ "text": "PTID" }}, "value": $string($.PTID) }} }}
- "period": start = $.EXAMDATE
- "identifier": [{{ "system": {ENC_SYS!r}, "value": $string($.PTID) & "-" & $.VISCODE }}]
- "extension": COLPROT, ORIGPROT, SITE
Use $.field to access fields.""",
    },
    "Condition": {
        "expected": 10, "kind": "object-or-undefined",
        "spec": f"""Input: ONE row. Output: Condition object or nothing — only emit
when $.DX != null and $.DX != "". Ternary MUST be at the TOP LEVEL, not nested
inside the object: $.DX != null and $.DX != "" ? {{ "identifier": ..., ... }} : [] — not
{{ "identifier": ..., "field": $.DX != null ? ... }}.
- "resourceType": "Condition" (literal, must be present)
- "identifier": ["adni-condition-" & $.PTID & "-" & $.VISCODE]
- "clinicalStatus": coding http://terminology.hl7.org/CodeSystem/condition-clinical code "active"
- "code": coding SNOMED 449888003, text = $.DX
- "subject": identifier with system {ADNI!r}, type.text "PTID", value = $.PTID
- "encounter": identifier with system {ENC_SYS!r}, value = $.PTID & "-" & $.VISCODE
- "recordedDate": $.EXAMDATE
Use $.field to access fields. Wrap output in [ ] to get array.""",
    },
    # "Observation" spec is built dynamically per-run by _build_observation_prompt()
    "Observation": {"expected": 273, "kind": "array", "spec": None},
}

EXAMPLE = '''Example for Patient:
```jsonata
[
  {
    "resourceType": "Patient",
    "identifier": [
      {
        "system": "http://adni.example.org/fhir/CodeSystem/adni-terms",
        "type": { "text": "PTID" },
        "value": $string($.PTID)
      }
    ],
    "gender": $.PTGENDER = "Male" ? "male" : ($.PTGENDER = "Female" ? "female" : "unknown")
  }
]
```

Example for Encounter:
```jsonata
[
  {
    "resourceType": "Encounter",
    "status": "finished",
    "class": { "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB" },
    "subject": {
      "identifier": {
        "system": "http://adni.example.org/fhir/CodeSystem/adni-terms",
        "type": { "text": "PTID" },
        "value": $string($.PTID)
      }
    },
    "identifier": [
      {
        "system": "http://adni.example.org/fhir/identifier/encounter",
        "value": $string($.PTID) & "-" & $.VISCODE
      }
    ],
    "period": { "start": $.EXAMDATE }
  }
]
```'''

# ---------------------------------------------------------------------------
# Observation strategy.
#
# Units are grouped by SYNTACTIC SHAPE, not medical domain. A JSONata array
# literal is one atomic parse/eval — if any single field's block inside a
# batch has a stray brace or bad regex, the WHOLE batch returns 0 resources,
# including fields that were written correctly. Domain categories (e.g.
# "cognitive") mixed plain numeric fields with the fragile string-numeric
# comparator-parsing fields in one call, so a single mistake on one field
# could sink several unrelated, easy fields alongside it.
#
# Shape-based units:
#   - "plain"          integer/decimal, no imaging enrichment — a one-line
#                       ternary, nearly copy-paste across fields. Low risk,
#                       batched larger (OBS_PLAIN_CHUNK fields/unit).
#   - "string-numeric"  ABETA/TAU/PTAU/ADAS11 — needs the regex-strip-
#                       comparator pattern, the single most fragile bit of
#                       syntax in the spec. One field per unit: the risk is
#                       concentrated exactly where it belongs, and there are
#                       only 4 such fields total so full granularity is cheap.
#   - "imaging"         mri-volumetric fields — numeric base plus 3 extra
#                       conditional sub-blocks (method/extension/derivedFrom).
#                       Batched smaller than "plain" (OBS_IMAGING_CHUNK) since
#                       each field carries more structure to get right, and
#                       — per the LLM-only requirement — this enrichment is
#                       NOT injected deterministically anywhere downstream;
#                       the model must generate it itself or it's absent.
#
# The LLM authors the JSONata for every unit itself, from the spec in
# _build_observation_unit_prompt. There is no deterministic reference and no
# fallback: the ReAct retry loop (validate -> feedback -> regenerate), plus
# the generic best-attempt tracking in _validate, is what improves results.
# ---------------------------------------------------------------------------
OBS_PLAIN_CHUNK = 6
OBS_IMAGING_CHUNK = 3


def _chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def build_observation_units(metadata: list[dict]) -> "OrderedDict[str, list[dict]]":
    from collections import OrderedDict
    imaging = [e for e in metadata if e.get("enrichWithImaging")]
    string_numeric = [e for e in metadata if e["valueType"] == "string-numeric" and not e.get("enrichWithImaging")]
    plain = [e for e in metadata if e not in imaging and e not in string_numeric]

    units: "OrderedDict[str, list[dict]]" = OrderedDict()
    for i, chunk in enumerate(_chunk(plain, OBS_PLAIN_CHUNK), start=1):
        units[f"plain-{i}"] = chunk
    for entry in string_numeric:
        units[f"string-numeric-{entry['sourceField']}"] = [entry]
    for i, chunk in enumerate(_chunk(imaging, OBS_IMAGING_CHUNK), start=1):
        units[f"imaging-{i}"] = chunk
    return units


def _unit_shape(unit_label: str) -> str:
    if unit_label.startswith("string-numeric-"):
        return "string-numeric"
    if unit_label.startswith("imaging-"):
        return "imaging"
    return "plain"


def _build_observation_unit_prompt(unit_label: str, entries: list[dict]) -> str:
    """Spec-driven prompt, tailored to the unit's syntactic shape. The LLM
    authors the JSONata itself from a field contract (name, code, secondary
    code, value type) — same style as Patient/Encounter/Condition. Nothing
    here is executed as a fallback; it is purely instructional."""
    shape = _unit_shape(unit_label)

    lines = []
    for e in entries:
        coding = e["coding"]
        sec = e.get("secondaryCoding")
        line = (f'- {e["sourceField"]}  (valueType: {e["valueType"]})  '
                f'code: {{"system": "{coding["system"]}", "code": "{coding["code"]}"}}')
        if sec:
            line += f'  +secondary: {{"system": "{sec["system"]}", "code": "{sec["code"]}"}}'
        lines.append(line)
    fields_block = "\n".join(lines)

    base = f"""Input: ONE ADNIMERGE row. Output: a FLAT JSONata ARRAY of 0..{len(entries)}
Observation resources for this unit — one per field below that has a
non-null, non-empty value in this row.

FIELDS IN THIS UNIT:
{fields_block}

IMPORTANT: In the template below, FIELDNAME is a PLACEHOLDER. Substitute
each actual field name listed above. Write field access as `$.FIELDNAME` —
a dot followed by the bare field name. NEVER write `$.<FIELDNAME>` — angle
brackets are NOT valid JSONata syntax and the expression will fail to execute.

- Top-level output: `[ block1, block2, ... ]` — exactly one block per field
  listed above, in order.
- Each block: `($.FIELDNAME != null and $string($.FIELDNAME) != "") ? [ {{...}} ] : []`
  Use `!= null`, NOT a bare truthy ternary (`$.FIELDNAME ? ...`) — 0 is a
  legitimate value (e.g. APOE4=0, CDRSB=0) and a truthy check would wrongly
  drop it.
- Each Observation object:
  - `"resourceType": "Observation"`
  - `"identifier": [{{ "system": "{OBS_SYS}", "value": $string($.PTID) & "-" & $.VISCODE & "-FIELDNAME" }}]`
  - `"code": {{ "coding": [the primary code above{{, the secondary code above if listed}}], "text": "FIELDNAME" }}`
  - `"subject": {{ "identifier": {{ "system": "{ADNI}", "type": {{ "text": "PTID" }}, "value": $string($.PTID) }} }}`
  - `"encounter": {{ "identifier": {{ "system": "{ENC_SYS}", "value": $string($.PTID) & "-" & $.VISCODE }} }}`
  - `"effectiveDateTime": $.EXAMDATE
"""

    if shape == "plain":
        value_rule = """  - VALUE: `"valueQuantity": {{ "value": $number($.FIELDNAME) }}`
  (every field in this unit is integer/decimal — no comparator parsing needed)
"""
    elif shape == "string-numeric":
        value_rule = """  - VALUE: the raw CSV value MAY have a leading comparator (`<`, `>`, `<=`,
    `>=`) before the number (e.g. "80" or "<200"). Strip it, then cast:
    `"valueQuantity": {{ "value": $number($replace($string($.FIELDNAME), /^(<=|>=|<|>)\\s*/, "")) }}`

    Worked example for a field called EXAMPLE with code {{"system": "http://loinc.org", "code": "12345-6"}}:
    ```jsonata
    ($.EXAMPLE != null and $string($.EXAMPLE) != "") ? [{{
      "resourceType": "Observation",
      "identifier": [{{ "system": "{OBS_SYS}", "value": $string($.PTID) & "-" & $.VISCODE & "-EXAMPLE" }}],
      "code": {{ "coding": [{{"system": "http://loinc.org", "code": "12345-6"}}], "text": "EXAMPLE" }},
      "valueQuantity": {{ "value": $number($replace($string($.EXAMPLE), /^(<=|>=|<|>)\\s*/, "")) }},
      "subject": {{ "identifier": {{ "system": "{ADNI}", "type": {{ "text": "PTID" }}, "value": $string($.PTID) }} }},
      "encounter": {{ "identifier": {{ "system": "{ENC_SYS}", "value": $string($.PTID) & "-" & $.VISCODE }} }},
      "effectiveDateTime": $.EXAMDATE
    }}] : []
    ```
""".format(ADNI=ADNI, ENC_SYS=ENC_SYS, OBS_SYS=OBS_SYS)
    else:  # imaging
        value_rule = f"""  - VALUE: `"valueQuantity": {{ "value": $number($.FIELDNAME) }}`
  - ADDITIONALLY attach imaging enrichment **as fields INSIDE the same
    Observation object** (never as sibling array elements). Each is guarded
    by its own `!= null` check; omit the field when the source is null:
      - `"method": {{ "text": $.FSVERSION }}` when `$.FSVERSION != null`
      - `"extension": ($.FLDSTRENG != null ? [{{ "url": "{ADNI}#FLDSTRENG", "valueString": $.FLDSTRENG }}] : [])`
      - `"derivedFrom": [{{ "reference": "ImagingStudy/adni-image-" & $string($.IMAGEUID) }}]` when `$.IMAGEUID != null`
  - Do NOT create separate standalone Observations for FSVERSION, FLDSTRENG,
    or IMAGEUID themselves — they are enrichment attached to the volumetric
    field's own Observation, never independent resources.
  - The outer block is ONE object `{{...}}`, NOT an array `[Observation,
    method-fragment, extension-fragment, derivedFrom-fragment]`.

    Worked example for a field called VOLUME with code {{"system": "{ADNI}", "code": "Brain-Volume-Vol"}}:
    ```jsonata
    ($.VOLUME != null and $string($.VOLUME) != "") ? [{{
      "resourceType": "Observation",
      "identifier": [{{ "system": "{OBS_SYS}", "value": $string($.PTID) & "-" & $.VISCODE & "-VOLUME" }}],
      "code": {{ "coding": [{{"system": "{ADNI}", "code": "Brain-Volume-Vol"}}], "text": "VOLUME" }},
      "valueQuantity": {{ "value": $number($.VOLUME) }},
      "subject": {{ "identifier": {{ "system": "{ADNI}", "type": {{ "text": "PTID" }}, "value": $string($.PTID) }} }},
      "encounter": {{ "identifier": {{ "system": "{ENC_SYS}", "value": $string($.PTID) & "-" & $.VISCODE }} }},
      "effectiveDateTime": $.EXAMDATE,
      "method": ($.FSVERSION != null ? {{ "text": $.FSVERSION }} : null),
      "extension": ($.FLDSTRENG != null ? [{{ "url": "{ADNI}#FLDSTRENG", "valueString": $.FLDSTRENG }}] : []),
      "derivedFrom": ($.IMAGEUID != null ? [{{ "reference": "ImagingStudy/adni-image-" & $string($.IMAGEUID) }}] : [])
    }}] : []
    ```
"""

    return base + value_rule + """
No JavaScript syntax anywhere (no `function`, no `==`, no `.prop = value`,
no `|` used as boolean-or).

Return ONLY the JSONata expression inside one ```jsonata code block.
No prose, no explanation.
"""


def log_node(func):
    def wrapper(s: S, *args, **kwargs):
        node_name = func.__name__
        iter_count = s.get("iteration", 0)
        logger.info(f"Entering node: {node_name} (iteration={iter_count})")

        timing = NodeTiming(node=node_name, start=time(), iteration=iter_count)
        _timings.setdefault(node_name, []).append(timing)

        try:
            result = func(s, *args, **kwargs)
            timing.end = time()
            timing.status = "success"
            return result
        except Exception as e:
            timing.end = time()
            timing.status = f"failed: {e}"
            raise
    return wrapper


class S(TypedDict, total=False):
    csv_path: str; schema_path: str
    rows: list[dict]; metadata: list[dict]
    expression: str; resources: list; exec_error: Optional[str]
    feedback: str; iteration: int
    results: dict
    best_resources: list; best_expression: str; best_issues: list; best_score: int; best_iteration: int
    # Observation unit sub-loop (units are grouped by syntactic shape, not domain)
    obs_unit_order: list[str]
    obs_units: dict  # unit label -> list[metadata entry]
    obs_unit_idx: int
    obs_accum: list
    obs_expressions: dict  # unit label -> the expression actually used to produce its resources


@log_node
def prepare(s: S) -> S:
    schema = json.load(open(s["schema_path"], encoding="utf-8"))
    fields = list(schema["properties"].keys())

    def coerce(f, v):
        if v is None or v == "": return None
        t = schema["properties"][f].get("type", "string")
        if t in ("integer", "number"):
            try:
                n = float(v); return int(n) if t == "integer" and n.is_integer() else n
            except ValueError:
                return v
        return v

    with open(s["csv_path"], encoding="utf-8") as f:
        recs = list(csv.DictReader(f))
    rows = [{fld: coerce(fld, r.get(fld)) for fld in fields} for r in recs]

    metadata = build_metadata()
    units = build_observation_units(metadata)
    return {"rows": rows, "metadata": metadata,
            "obs_unit_order": list(units.keys()), "obs_units": dict(units),
            "obs_unit_idx": 0, "obs_accum": [], "obs_expressions": {},
            "iteration": 0, "feedback": "", "expression": "", "results": {},
            "best_resources": [], "best_expression": "", "best_issues": [], "best_score": 10**9, "best_iteration": 0}


def _extract(text: str) -> str:
    if "```" in text:
        block = text.split("```")[1]
        return block[len("jsonata"):].strip() if block.startswith("jsonata") else block.strip()
    return text.strip()


# ---------------------------------------------------------------------------
# Shared generate / execute / validate logic, parameterized by target.
# Each resource type gets its own thin graph node below so the graph is
# explicit (generate_patient, generate_encounter, ...) rather than driven
# by a generic t_idx loop.
# ---------------------------------------------------------------------------
def _generate(s: S, target: str) -> S:
    """Used for Patient / Encounter / Condition. Observation uses the
    unit sub-loop (generate_observation_unit) instead — see below."""
    cfg = TARGETS[target]
    schema_fields = ', '.join(json.load(open(s['schema_path']))['properties'])
    user = f"""Write a per-row JSONata mapping producing a FHIR {target}.

{EXAMPLE}

CONTRACT:
{cfg['spec']}

Available CSV fields (already type-coerced, empty->null):
{schema_fields}
"""
    if s.get("feedback"):
        user += f"""

TARGETED REPAIR MODE. Preserve all valid mapping logic. Make the smallest possible change required by the hard validator findings. Do not rewrite unrelated fields or add resources.
Previous attempt:
```jsonata
{s.get('expression', '')}
```
VALIDATION FEEDBACK:
{s['feedback']}
"""

    msg = llm.invoke([("system", JSONATA_RULES), ("human", user)])
    return {"expression": _extract(msg.content), "exec_error": None}


def _strip_single_arg_filter(expr: str) -> tuple[str, bool]:
    """Remove accidental one-argument $filter(x) wrappers only.

    JSONata $filter requires an array and a predicate function. Llama sometimes
    emits $filter(array[predicate]) even though the predicate is already encoded
    in the bracket expression. That wrapper is redundant and safe to remove.
    Genuine two-argument forms are left untouched for targeted model repair.
    """
    marker = "$filter("
    changed = False
    pos = expr.find(marker)
    while pos >= 0:
        start = pos + len(marker)
        depth = 1
        bracket_depth = 0
        quote = None
        escape = False
        comma_at_top = False
        end = None
        i = start
        while i < len(expr):
            ch = expr[i]
            if quote:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == quote:
                    quote = None
            else:
                if ch in ('\"', "'"):
                    quote = ch
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0 and bracket_depth == 0:
                        end = i
                        break
                elif ch == "[":
                    bracket_depth += 1
                elif ch == "]" and bracket_depth > 0:
                    bracket_depth -= 1
                elif ch == "," and depth == 1 and bracket_depth == 0:
                    comma_at_top = True
                    break
            i += 1
        if end is None:
            break
        if not comma_at_top:
            inner = expr[start:end].strip()
            expr = expr[:pos] + inner + expr[end + 1:]
            changed = True
            pos = expr.find(marker, pos + len(inner))
        else:
            pos = expr.find(marker, start)
    return expr, changed


def _sanitize_jsonata_expression(expression: str) -> tuple[str, list[str]]:
    """Apply narrowly-scoped JSONata syntax cleanup without redesigning mappings."""
    expr = _extract(expression).strip()
    repairs: list[str] = []
    if expr.startswith("="):
        expr = expr[1:].lstrip()
        repairs.append("removed accidental leading '=' from JSONata expression")
    expr2, changed = _strip_single_arg_filter(expr)
    if changed:
        expr = expr2
        repairs.append("removed invalid one-argument $filter wrapper")
    return expr, repairs


def _execute(s: S, target: str) -> S:
    expression, syntax_repairs = _sanitize_jsonata_expression(s["expression"])
    payload = json.dumps({"expression": expression, "rows": s["rows"]})
    proc = subprocess.run(["node", EVAL_JSONATA], input=payload,
                           capture_output=True, text=True)
    if proc.returncode != 0:
        try:
            err = json.loads(proc.stderr)["error"]
        except Exception:
            err = proc.stderr.strip() or "unknown node error"
        guidance = ""
        if 'function "filter"' in err or 'Argument 2 of function "filter"' in err:
            guidance = " TARGETED JSONATA FIX: do not use $filter(...). Rewrite predicates using array[condition], and preserve all other logic."
        return {
            "resources": [],
            "expression": expression,
            "exec_error": f"JSONata execution failed: {err}",
            "feedback": guidance,
        }

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
    return {
        "resources": out,
        "expression": expression,
        "exec_error": None,
        "feedback": "syntax normalization: " + "; ".join(syntax_repairs) if syntax_repairs else s.get("feedback", ""),
    }


ALLOWED_SYS = {"http://loinc.org", "http://snomed.info/sct", ADNI, ENC_SYS,
               "http://terminology.hl7.org/CodeSystem/v3-ActCode",
               "http://terminology.hl7.org/CodeSystem/condition-clinical",
               "http://unitsofmeasure.org", "http://loinc.org/76494-1",
               "http://loinc.org/76498-2"}


class Verdict(BaseModel):
    verdict: str = Field(description="PASS or FAIL")
    feedback: str = Field(description="Concrete, actionable fixes if FAIL; else 'ok'")


def _walk(obj: Any, path: str = ""):
    """Yield (path, value) pairs for every nested value."""
    yield path or "$", obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = f"{path}.{k}" if path else k
            yield from _walk(v, child)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def _strip_literal_undefined(obj: Any) -> tuple[Any, int]:
    """Remove only literal 'undefined' values; never invent clinical data."""
    repairs = 0
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if v == "undefined":
                repairs += 1
                continue
            nv, n = _strip_literal_undefined(v)
            repairs += n
            out[k] = nv
        return out, repairs
    if isinstance(obj, list):
        out = []
        for v in obj:
            if v == "undefined":
                repairs += 1
                continue
            nv, n = _strip_literal_undefined(v)
            repairs += n
            out.append(nv)
        return out, repairs
    return obj, 0


def _tracking_key(r: dict) -> str:
    """Extract a business key from a resource's first `identifier` entry.

    Handles both identifier forms authored across the resource types:
    Patient/Encounter/Observation use a list of identifier objects carrying a
    `value`; Condition uses a list with a bare string. Returns "" when no
    identifier is present so the caller can treat it as a missing key."""
    ident = r.get("identifier")
    if isinstance(ident, list) and ident:
        first = ident[0]
        if isinstance(first, dict):
            return str(first.get("value", ""))
        return str(first)
    return ""


def _normalize_resources(s: S, target: str, res: list) -> tuple[list, list[str]]:
    """Perform safe contract-defined repairs before authoritative validation."""
    normalized = []
    repairs: list[str] = []
    seen_keys: set[str] = set()

    unit = None
    if s.get("obs_unit_order"):
        idx = s.get("obs_unit_idx", 0)
        if idx < len(s["obs_unit_order"]):
            unit = s["obs_unit_order"][idx]
    entries = s.get("obs_units", {}).get(unit, []) if unit else []

    for raw in res:
        if not isinstance(raw, dict):
            normalized.append(raw)
            continue

        item, removed = _strip_literal_undefined(raw)
        if removed:
            repairs.append(f"removed {removed} literal 'undefined' value(s)")

        if item.get("resourceType") in (None, ""):
            item["resourceType"] = target
            repairs.append(f"set missing resourceType={target!r}")

        key = _tracking_key(item)
        if key and key in seen_keys:
            repairs.append(f"dropped duplicate resource identifier {key!r}")
            continue
        if key:
            seen_keys.add(key)

        if target == "Observation":
            # Structural cleanup only — dropping a malformed/invalid resource
            # is not the same as fabricating content. We do NOT inject
            # method/extension/derivedFrom here: imaging enrichment is part
            # of the mapping and must come from the LLM itself (see the
            # "imaging" unit prompt in _build_observation_unit_prompt).
            if any(key.endswith(f"-{x}") for x in ("FSVERSION", "FLDSTRENG", "IMAGEUID")):
                repairs.append(f"dropped standalone imaging metadata resource {key!r}")
                continue

        normalized.append(item)

    return normalized, repairs


def _programmatic(target: str, res: list, s: S) -> list[str]:
    issues: list[str] = []
    if not res:
        return [f"No {target} resources were produced."]

    keys: set[str] = set()
    for idx, r in enumerate(res[:1000]):
        if not isinstance(r, dict):
            issues.append(f"item[{idx}] is not an object")
            continue
        if r.get("resourceType") != target:
            issues.append(f"item[{idx}] resourceType={r.get('resourceType')!r}; expected {target!r}")
        tkey = _tracking_key(r)
        if not tkey or "undefined" in tkey.lower():
            issues.append(f"item[{idx}] has malformed/missing identifier: {tkey!r}")
        elif tkey in keys:
            issues.append(f"duplicate resource identifier {tkey!r}")
        else:
            keys.add(tkey)
        for path, value in _walk(r):
            if isinstance(value, str) and value == "undefined":
                issues.append(f"item[{idx}] contains literal undefined at {path}")
                break

    def systems(o):
        if not isinstance(o, dict):
            return
        code = o.get("code")
        if isinstance(code, dict):
            for c in code.get("coding", []) or []:
                if isinstance(c, dict):
                    yield c.get("system")

    for r in res[:1000]:
        for sys in systems(r):
            if sys and sys not in ALLOWED_SYS:
                issues.append(f"Unexpected coding system {sys!r} (not in terminology.md).")

    if target == "Patient":
        for r in res:
            if not isinstance(r, dict):
                continue
            if not isinstance(r.get("identifier"), list) or not r["identifier"]:
                issues.append(f"Patient {_tracking_key(r) or '<no-identifier>'} missing identifier")

    if target == "Condition":
        for r in res:
            if not isinstance(r, dict):
                continue
            if "resourceType" not in r:
                issues.append(f"Condition {_tracking_key(r) or '<no-identifier>'} missing resourceType")
            if not r.get("code", {}).get("coding"):
                issues.append(f"Condition {_tracking_key(r) or '<no-identifier>'} missing code.coding")

    if target == "Observation":
        category = s.get("obs_unit_order", [None])[s.get("obs_unit_idx", 0)]
        entries = s.get("obs_units", {}).get(category, [])
        expected_keys = []
        for row in s.get("rows", []):
            for e in entries:
                if row.get(e["sourceField"]) not in (None, ""):
                    expected_keys.append(f"{row.get('PTID')}-{row.get('VISCODE')}-{e['sourceField']}")
        actual_keys = [_tracking_key(r) for r in res if isinstance(r, dict)]
        actual_set = set(actual_keys)
        for tkey in expected_keys:
            if tkey not in actual_set:
                issues.append(f"missing Observation {tkey!r}")
        if len(actual_keys) != len(set(actual_keys)):
            issues.append("duplicate Observation identifiers detected")
        for tkey in actual_keys:
            if isinstance(tkey, str) and any(tkey.endswith(f"-{x}") for x in ("FSVERSION", "FLDSTRENG", "IMAGEUID")):
                issues.append(f"standalone imaging metadata Observation {tkey!r}")

    return issues


def _validate_with_hapi(resources: list, target: str) -> list[str]:
    """Use the HAPI/HL7 FHIR R4 validator when configured."""
    if not FHIR_VALIDATOR_JAR:
        return []
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="adni-fhir-") as td:
        for i, resource in enumerate(resources):
            path = os.path.join(td, f"{target.lower()}-{i}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(resource, f)
            proc = subprocess.run(
                ["java", "-jar", FHIR_VALIDATOR_JAR, "-version", FHIR_VALIDATOR_VERSION, path],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                detail = (proc.stdout + "\n" + proc.stderr).strip().replace("\n", " | ")
                issues.append(f"FHIR validator failed for {target}[{i}]: {detail[:1000]}")
    return issues


def _validate(s: S, target: str) -> S:
    """Validate current attempt, retain the best attempt, and never discard work just
    because MAX_ITERS was reached. Execution failures trigger retry feedback, while
    the best successfully executed candidate remains available as the fallback.
    """
    iteration = s["iteration"] + 1

    if s.get("exec_error"):
        issue = s["exec_error"]
        guidance = issue
        if "must be of the same data type" in issue and "operator" in issue:
            guidance += " TARGETED JSONATA FIX: a numeric operator is comparing incompatible types. Wrap string operands with $number(...) before >, <, >=, <=, +, -, *, or /. Do not change unrelated logic."
        if 'function "filter"' in issue:
            guidance += " TARGETED JSONATA FIX: do not use one-argument $filter(...); use array[condition] instead."

        # If this is the final execution attempt, restore the best successfully
        # executed candidate rather than replacing it with an empty/error result.
        final = iteration >= MAX_ITERS
        best_resources = s.get("best_resources", [])
        best_expression = s.get("best_expression", "")
        best_issues = s.get("best_issues", [])
        used_best = bool(best_expression) or bool(best_resources)
        if final and used_best:
            final_issues = list(best_issues)
            results = {**s.get("results", {}),
                       "__last_pass__": not final_issues,
                       "__last_issues__": final_issues,
                       "__last_repairs__": [],
                       "__used_best_attempt__": True,
                       "__execution_error_on_final_attempt__": issue}
            return {"feedback": f"MAX_ITERS reached after execution error; using best attempt #{s.get('best_iteration', 0)}. Final error: {issue}",
                    "iteration": iteration,
                    "resources": list(best_resources),
                    "expression": best_expression,
                    "results": results,
                    "exec_error": None}

        results = {**s.get("results", {}),
                   "__last_pass__": False,
                   "__last_issues__": [guidance],
                   "__last_repairs__": []}
        return {"feedback": guidance, "iteration": iteration, "results": results}

    res, repairs = _normalize_resources(s, target, s.get("resources", []))
    s["resources"] = res
    issues = _programmatic(target, res, s)
    issues.extend(_validate_with_hapi(res, target))

    # Optional critic supplies repair wording only; deterministic/FHIR validation
    # remains authoritative.
    try:
        critic = llm.with_structured_output(Verdict).invoke([
            ("system", "You are a strict FHIR R4 + ADNI reviewer. Deterministic validator results are authoritative. Return concise repair advice."),
            ("human", f"Target: {target}\nDeterministic/FHIR issues: {issues or 'none'}\n"
                       f"Repairs already applied: {repairs or 'none'}\nSample resources:\n{json.dumps(res[:3], indent=2)}")
        ])
    except Exception:
        critic = None

    if issues:
        advice = critic.feedback if critic is not None else "Apply the listed validation fixes only."
        feedback = (f"HARD VALIDATION FAIL: {'; '.join(issues)}. "
                    f"TARGETED REPAIR: {advice}. Repairs already applied: {'; '.join(repairs) if repairs else 'none'}")
    else:
        feedback = "ok" if not repairs else f"deterministic repairs: {'; '.join(repairs)}"

    # Keep the numerically best successful execution seen so far. Fewer hard issues
    # is always better; ties prefer the later attempt because it may include repairs.
    score = len(issues)
    best_score = s.get("best_score", 10**9)
    if score <= best_score:
        best_resources = list(res)
        best_expression = s.get("expression", "")
        best_issues = list(issues)
        best_iteration = iteration
    else:
        best_resources = s.get("best_resources", [])
        best_expression = s.get("best_expression", "")
        best_issues = s.get("best_issues", [])
        best_iteration = s.get("best_iteration", 0)
        best_score = best_score

    results = {**s.get("results", {}),
               "__last_pass__": not issues,
               "__last_issues__": issues,
               "__last_repairs__": repairs,
               "__best_score__": score if score <= best_score else best_score}

    # On the final attempt, restore the best successfully executed candidate.
    # This is deliberately fail-soft: a remaining validation issue is reported in
    # metadata/logging, but it does not crash the whole LangGraph run.
    if iteration >= MAX_ITERS and best_resources is not None:
        s["resources"] = list(best_resources)
        s["expression"] = best_expression
        issues = list(best_issues)
        feedback = (f"MAX_ITERS reached; using best attempt #{best_iteration} "
                    f"with {len(issues)} hard validation issue(s). " +
                    ("; ".join(issues) if issues else "candidate passed validation."))
        results["__last_issues__"] = issues
        results["__last_pass__"] = not issues
        results["__used_best_attempt__"] = True

    return {
        "feedback": feedback,
        "iteration": iteration,
        "results": results,
        "best_resources": best_resources,
        "best_expression": best_expression,
        "best_issues": best_issues,
        "best_score": min(score, best_score),
        "best_iteration": best_iteration,
    }


def _retry_or_proceed(s: S) -> str:
    # Retry while budget remains. At MAX_ITERS, continue with the best attempt
    # rather than raising and aborting the entire pipeline.
    if s.get("exec_error") or s.get("results", {}).get("__last_issues__"):
        return "retry" if s["iteration"] < MAX_ITERS else "proceed"
    return "proceed"


@log_node
def fail_validation(s: S) -> S:
    """Legacy compatibility node: no longer raises. Preserve the best candidate."""
    return {
        "feedback": s.get("feedback", ""),
        "resources": list(s.get("best_resources", s.get("resources", []))),
        "expression": s.get("best_expression", s.get("expression", "")),
    }


def _stash(s: S, target: str) -> S:
    """Save the best available expression/resources under the target key and
    reset scratch state for the next stage. Invalid final attempts do not abort the pipeline."""
    # Drop transient validator/repair bookkeeping before publishing stage results.
    results = {k: v for k, v in dict(s["results"]).items() if not k.startswith("__")}
    results[target] = {"expression": s["expression"],
                        "resources": s["resources"],
                        "count": len(s["resources"]),
                        "iterations": s["iteration"]}
    return {"results": results, "iteration": 0, "feedback": "", "expression": "",
            "best_resources": [], "best_expression": "", "best_issues": [],
            "best_score": 10**9, "best_iteration": 0}


# ---------------------------------------------------------------------------
# Observation unit sub-loop (units grouped by syntactic shape — see
# build_observation_units / _build_observation_unit_prompt above)
# ---------------------------------------------------------------------------
@log_node
def generate_observation_unit(s: S) -> S:
    unit = s["obs_unit_order"][s["obs_unit_idx"]]
    entries = s["obs_units"][unit]

    # LLM supplies all mapping logic including imaging enrichment — there is
    # no deterministic content injection anywhere downstream for Observation.
    prompt = _build_observation_unit_prompt(unit, entries)
    if s.get("feedback"):
        prompt += f"""

TARGETED REPAIR MODE. Preserve all valid blocks exactly once. Make the smallest possible change required by the hard validator findings. NEVER create standalone FSVERSION, FLDSTRENG, or IMAGEUID Observations.
Previous attempt:
```jsonata
{s.get('expression', '')}
```
VALIDATION FEEDBACK:
{s['feedback']}
"""

    msg = llm.invoke([("system", JSONATA_RULES), ("human", prompt)])
    return {"expression": _extract(msg.content), "exec_error": None}


@log_node
def execute_observation_unit(s: S) -> S:
    return _execute(s, "Observation")


@log_node
def validate_observation_unit(s: S) -> S:
    unit = s["obs_unit_order"][s["obs_unit_idx"]]
    entries = s["obs_units"][unit]
    field_names = {e["sourceField"] for e in entries}
    expected = sum(1 for row in s["rows"] for f in field_names if row.get(f) not in (None, ""))

    saved = dict(TARGETS["Observation"])
    TARGETS["Observation"]["expected"] = expected
    try:
        out = _validate(s, "Observation")
    finally:
        TARGETS["Observation"].update(saved)
    return out


def _after_obs_unit(s: S) -> str:
    decision = _retry_or_proceed(s)
    return "retry" if decision == "retry" else "proceed"


@log_node
def advance_observation_unit(s: S) -> S:
    """Accumulate this unit's LLM-authored resources and move to the next
    unit or hand off to finalize(). Records which expression produced this
    unit's resources so the mapping is preserved. There is NO deterministic
    fallback: whatever the LLM produced (passing, or — after exhausting
    MAX_ITERS — the best attempt _validate tracked) is what's stored."""
    unit = s["obs_unit_order"][s["obs_unit_idx"]]
    # Keep only real Observation resources — drop any fragments the LLM may
    # have emitted as array siblings (e.g. bare {"method":...} enrichment
    # sub-objects). A real Observation carries resourceType + a business
    # identifier; anything else is structural noise, not a resource.
    resources = [r for r in s["resources"]
                if isinstance(r, dict)
                and r.get("resourceType") == "Observation"
                and _tracking_key(r)]
    used_expression = s["expression"]

    accum = list(s["obs_accum"]) + resources
    expressions = dict(s["obs_expressions"])
    expressions[unit] = used_expression

    results = dict(s["results"])
    results.pop("__last_pass__", None)
    results.pop("__last_issues__", None)

    return {"obs_accum": accum, "obs_expressions": expressions, "obs_unit_idx": s["obs_unit_idx"] + 1,
            "results": results, "iteration": 0, "feedback": "", "expression": "",
            "best_resources": [], "best_expression": "", "best_issues": [],
            "best_score": 10**9, "best_iteration": 0}


def _after_advance_observation(s: S) -> str:
    return "next_unit" if s["obs_unit_idx"] < len(s["obs_unit_order"]) else "finalize"


@log_node
def finalize(s: S) -> S:
    # Publish only actual target results; transient __* validator metadata is internal.
    results = {k: v for k, v in dict(s["results"]).items() if not k.startswith("__")}
    # Assemble the real per-unit expressions into one labeled document. There
    # is no longer a single Observation expression (it's many, one per
    # shape-based unit) — this stores the actual mapping instead of a
    # placeholder string, and __main__ also writes each one to its own file.
    combined = "\n\n".join(
        f"// ---- unit: {unit} ----\n{expr}"
        for unit, expr in s["obs_expressions"].items()
    )
    results["Observation"] = {"expression": combined,
                               "expressions_by_unit": dict(s["obs_expressions"]),
                               "resources": s["obs_accum"],
                               "count": len(s["obs_accum"]),
                               "iterations": None}
    return {"results": results}



# ---------------------------------------------------------------------------
# Explicit per-resource graph nodes
# ---------------------------------------------------------------------------
@log_node
def generate_patient(s: S) -> S: return _generate(s, "Patient")
@log_node
def execute_patient(s: S) -> S: return _execute(s, "Patient")
@log_node
def validate_patient(s: S) -> S: return _validate(s, "Patient")
@log_node
def advance_to_encounter(s: S) -> S: return _stash(s, "Patient")

@log_node
def generate_encounter(s: S) -> S: return _generate(s, "Encounter")
@log_node
def execute_encounter(s: S) -> S: return _execute(s, "Encounter")
@log_node
def validate_encounter(s: S) -> S: return _validate(s, "Encounter")
@log_node
def advance_to_condition(s: S) -> S: return _stash(s, "Encounter")

@log_node
def generate_condition(s: S) -> S: return _generate(s, "Condition")
@log_node
def execute_condition(s: S) -> S: return _execute(s, "Condition")
@log_node
def validate_condition(s: S) -> S: return _validate(s, "Condition")
@log_node
def advance_to_observation(s: S) -> S: return _stash(s, "Condition")

def build():
    g = StateGraph(S)
    g.add_node("prepare", prepare)

    g.add_node("generate_patient", generate_patient)
    g.add_node("execute_patient", execute_patient)
    g.add_node("validate_patient", validate_patient)
    g.add_node("advance_to_encounter", advance_to_encounter)

    g.add_node("generate_encounter", generate_encounter)
    g.add_node("execute_encounter", execute_encounter)
    g.add_node("validate_encounter", validate_encounter)
    g.add_node("advance_to_condition", advance_to_condition)

    g.add_node("generate_condition", generate_condition)
    g.add_node("execute_condition", execute_condition)
    g.add_node("validate_condition", validate_condition)
    g.add_node("advance_to_observation", advance_to_observation)

    g.add_node("generate_observation_unit", generate_observation_unit)
    g.add_node("execute_observation_unit", execute_observation_unit)
    g.add_node("validate_observation_unit", validate_observation_unit)
    g.add_node("advance_observation_unit", advance_observation_unit)
    g.add_node("fail_validation", fail_validation)
    g.add_node("finalize", finalize)

    g.add_edge(START, "prepare")
    g.add_edge("prepare", "generate_patient")

    g.add_edge("generate_patient", "execute_patient")
    g.add_edge("execute_patient", "validate_patient")
    g.add_conditional_edges("validate_patient", _retry_or_proceed,
                             {"retry": "generate_patient", "proceed": "advance_to_encounter", "fail": "advance_to_encounter"})
    g.add_edge("advance_to_encounter", "generate_encounter")

    g.add_edge("generate_encounter", "execute_encounter")
    g.add_edge("execute_encounter", "validate_encounter")
    g.add_conditional_edges("validate_encounter", _retry_or_proceed,
                             {"retry": "generate_encounter", "proceed": "advance_to_condition", "fail": "advance_to_condition"})
    g.add_edge("advance_to_condition", "generate_condition")

    g.add_edge("generate_condition", "execute_condition")
    g.add_edge("execute_condition", "validate_condition")
    g.add_conditional_edges("validate_condition", _retry_or_proceed,
                             {"retry": "generate_condition", "proceed": "advance_to_observation", "fail": "advance_to_observation"})
    g.add_edge("advance_to_observation", "generate_observation_unit")

    g.add_edge("generate_observation_unit", "execute_observation_unit")
    g.add_edge("execute_observation_unit", "validate_observation_unit")
    g.add_conditional_edges("validate_observation_unit", _retry_or_proceed,
                             {"retry": "generate_observation_unit",
                              "proceed": "advance_observation_unit",
                              "fail": "advance_observation_unit"})
    g.add_conditional_edges("advance_observation_unit", _after_advance_observation,
                             {"next_unit": "generate_observation_unit",
                              "finalize": "finalize"})
    g.add_edge("finalize", END)

    return g.compile()


if __name__ == "__main__":
    print("Building graph...")
    app = build()
    print("Invoking pipeline...")
    pipeline_start = time()
    final = app.invoke(
        {"csv_path": os.path.join(INPUTS_DIR, "adnimerge_small.csv"),
         "schema_path": os.path.join(INPUTS_DIR, "schema.json")},
        {"recursion_limit": 200},
    )
    pipeline_end = time()
    print("Writing outputs...")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    for tgt, info in final["results"].items():
        # Only published target dictionaries are written. Internal bookkeeping keys
        # (defensively filtered above) must never reach this loop.
        if not isinstance(info, dict) or "resources" not in info:
            logger.warning("Skipping non-target result %r", tgt)
            continue
        print(f"{tgt:12} count={info['count']:>4}  iters={info['iterations']}")
        with open(os.path.join(RESULTS_DIR, f"llm_{tgt.lower()}.jsonata"), "w") as f:
            f.write(info["expression"])
        with open(os.path.join(RESULTS_DIR, f"out_{tgt.lower()}.json"), "w") as f:
            json.dump(info["resources"], f, indent=2)
        if "expressions_by_unit" in info:
            for unit, expr in info["expressions_by_unit"].items():
                with open(os.path.join(RESULTS_DIR, f"llm_observation_{unit}.jsonata"), "w") as f:
                    f.write(expr)

    timing_summary = {}
    total_node_time = 0
    for node_name, entries in _timings.items():
        total_ms = sum(e.duration_ms for e in entries)
        call_count = len(entries)
        avg_ms = total_ms / call_count if call_count > 0 else 0
        timing_summary[node_name] = {
            "calls": call_count,
            "total_ms": round(total_ms, 2),
            "avg_ms": round(avg_ms, 2),
            "statuses": [e.status for e in entries]
        }
        total_node_time += total_ms

    print("\n" + "=" * 70)
    print("TIMING SUMMARY")
    print("=" * 70)
    print(f"{'Node':<40} {'Calls':>6} {'Total (ms)':>12} {'Avg (ms)':>10}")
    print("-" * 70)
    for node_name, stats in sorted(timing_summary.items()):
        print(f"{node_name:<40} {stats['calls']:>6} {stats['total_ms']:>12.2f} {stats['avg_ms']:>10.2f}")
    print("-" * 70)
    print(f"{'TOTAL PIPELINE TIME':<40} {'':>6} {((pipeline_end - pipeline_start) * 1000):>12.2f} {'':>10}")
    print(f"{'SUM OF NODE TIMES':<40} {'':>6} {total_node_time:>12.2f} {'':>10}")
    print("=" * 70)

    with open(os.path.join(RESULTS_DIR, "timing_summary.json"), "w") as f:
        json.dump({
            "pipeline_total_ms": round((pipeline_end - pipeline_start) * 1000, 2),
            "nodes": timing_summary
        }, f, indent=2)

    print("Done!")
