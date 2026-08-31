import json
import yaml
from pathlib import Path
from datetime import datetime

from agent.terminology.client import TerminologyClient
from agent.terminology.models import Candidate
from agent.hybrid.llm_terms import generate_search_terms, generate_search_terms_simple
from agent.hybrid.scorer import score_candidates
from agent.hybrid.thresholds import apply_thresholds, get_top_candidates
from agent.hybrid.evaluator import evaluate_with_llm, determine_decision
from agent.hybrid.report_generator import save_mapping_report
from agent.hybrid.children import find_child_candidates, deduplicate_candidates


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base; nested dicts merge, scalars replace."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config() -> dict:
    base_path = Path(__file__).parent.parent.parent / "config.yaml"
    with open(base_path) as f:
        config = yaml.safe_load(f)
    local_path = base_path.parent / "config.local.yaml"
    if local_path.exists():
        with open(local_path) as f:
            local = yaml.safe_load(f) or {}
        config = _deep_merge(config, local)
    return config


def load_terminology_config() -> dict:
    return load_config()["terminology_server"]


def load_fields() -> list[dict]:
    fields_path = Path(__file__).parent.parent.parent / "fields.json"
    with open(fields_path) as f:
        data = json.load(f)
    return data.get("fields", [])


def get_agent_fields() -> list[dict]:
    """Get fields that should use the agent path."""
    all_fields = load_fields()
    return [f for f in all_fields if f.get("agent_path", False)]


def run_field(
    field_concept: dict,
    terminology_client: TerminologyClient | None = None
) -> dict:
    """Process a single field through the hybrid pipeline.

    Steps:
    1. Generate search terms (LLM)
    2. Query expand (deterministic)
    3. Lookup each candidate (deterministic)
    4. Score candidates (deterministic)
    5. Apply thresholds (deterministic)
    """
    field_name = field_concept.get("field_name", "UNKNOWN")

    if terminology_client is None:
        terminology_client = TerminologyClient(load_terminology_config())

    # Step 1: Generate search terms
    try:
        search_terms = generate_search_terms(field_concept)
    except Exception as e:
        print(f"LLM error for {field_name}, using fallback: {e}")
        search_terms = generate_search_terms_simple(field_concept)

    # Step 2: Query expand - try each term until we get candidates
    candidates = []
    expand_results = []

    for term in search_terms:
        vs_url = field_concept.get("target_value_set", "http://loinc.org/vs")
        result = terminology_client.expand(vs_url=vs_url, filter_text=term, count=10)

        expand_results.append({
            "term": term,
            "vs_url": vs_url,
            "candidates": [c.model_dump() for c in result.candidates],
            "total": result.total,
        })

        if result.candidates:
            candidates = result.candidates
            break

    # Fallback: try field_name if no candidates found
    if not candidates:
        fallback_term = field_concept.get("field_name", "")
        vs_url = field_concept.get("target_value_set", "http://loinc.org/vs")
        result = terminology_client.expand(vs_url=vs_url, filter_text=fallback_term, count=10)
        candidates = result.candidates
        expand_results.append({
            "term": fallback_term,
            "vs_url": vs_url,
            "candidates": [c.model_dump() for c in result.candidates],
            "total": result.total,
        })

    if not candidates:
        return {
            "field_name": field_name,
            "decision": "no_mapping",
            "reason": "No candidates found from terminology server",
            "score": 0.0,
            "expand_results": expand_results,
            "scored_candidates": [],
        }

    # Step 3: Lookup each candidate
    lookup_results = []
    for candidate in candidates:
        lookup = terminology_client.lookup(system=candidate.system, code=candidate.code)
        lookup_results.append({
            "candidate": candidate,
            "lookup": lookup,
        })

    # Step 3a: Find child candidates for panel/form type entries
    vs_url = field_concept.get("target_value_set", "http://loinc.org/vs")
    children = find_child_candidates(candidates, field_concept, terminology_client, vs_url)

    if children:
        print(f"  Found {len(children)} child candidates")
        # Add children to candidates and lookup
        for child in children:
            # Check if already in lookup_results
            existing_codes = {lr["candidate"].code for lr in lookup_results}
            if child.code not in existing_codes:
                try:
                    lookup = terminology_client.lookup(system=child.system, code=child.code)
                    lookup_results.append({
                        "candidate": child,
                        "lookup": lookup,
                    })
                except Exception as e:
                    print(f"    Failed to lookup child {child.code}: {e}")

    # Step 4: Score candidates (including children)
    scored = score_candidates(lookup_results, field_concept)

    # Step 5: LLM evaluation on top 3 candidates
    top_3 = get_top_candidates(scored, limit=3)
    
    deterministic_score = 0.0
    if top_3:
        deterministic_score = top_3[0].get("score", 0.0)
    
    llm_evaluation = None
    llm_decision = None
    
    if top_3:
        try:
            llm_result = evaluate_with_llm(top_3, field_concept)
            if llm_result.get("success"):
                llm_evaluation = llm_result.get("evaluation")
                llm_decision = determine_decision(llm_result, deterministic_score)
        except Exception as e:
            print(f"  LLM evaluation error: {e}")
            llm_evaluation = None

    # Step 6: Apply thresholds (or use LLM decision if available)
    if llm_decision:
        # Use LLM-based decision
        decision = llm_decision
        # Override with LLM-specific fields
        decision["llm_evaluation"] = llm_evaluation
        decision["report"] = llm_decision.get("report")
        
        # Get the candidate - use LLM recommendation or fallback to top deterministic
        recommended_code = llm_decision.get("recommended_code")
        if recommended_code:
            for c in top_3:
                cand = c.get("candidate")
                cand_dict = cand.model_dump() if hasattr(cand, "model_dump") else (cand if isinstance(cand, dict) else {})
                cand_code = cand_dict.get("code", "")
                if cand_code == recommended_code:
                    decision["candidate"] = cand_dict
                    lookup = c.get("lookup")
                    decision["lookup"] = lookup.model_dump() if hasattr(lookup, "model_dump") else (lookup if isinstance(lookup, dict) else {})
                    break
        elif top_3:
            # Use top deterministic candidate when LLM doesn't specify
            top = top_3[0]
            cand = top.get("candidate")
            decision["candidate"] = cand.model_dump() if hasattr(cand, "model_dump") else (cand if isinstance(cand, dict) else {})
            lookup = top.get("lookup")
            decision["lookup"] = lookup.model_dump() if hasattr(lookup, "model_dump") else (lookup if isinstance(lookup, dict) else {})
    else:
        # Fallback to deterministic thresholds
        decision = apply_thresholds(scored, field_concept)

    return {
        "field_name": field_name,
        "field_concept": field_concept,
        "search_terms": search_terms,
        "expand_results": expand_results,
        "scored_candidates": scored,
        "decision": decision.get("decision", "no_mapping"),
        "candidate": decision.get("candidate"),
        "score": decision.get("score", 0.0),
        "reason": decision.get("reason"),
        "llm_evaluation": decision.get("llm_evaluation"),
        "report": decision.get("report"),
    }


def run_all_fields(output_dir: Path | None = None) -> list[dict]:
    """Process all agent-path fields and generate mapping report."""
    agent_fields = get_agent_fields()
    results = []

    print(f"Processing {len(agent_fields)} fields...")

    terminology_client = TerminologyClient(load_terminology_config())

    for i, field in enumerate(agent_fields, 1):
        print(f"\n[{i}/{len(agent_fields)}] {field['field_name']}")

        result = run_field(field, terminology_client)
        results.append(result)

        print(f"  Decision: {result['decision']}")
        if result.get("candidate"):
            c = result["candidate"]
            print(f"  Code: {c.get('code')} - {c.get('display')}")
            print(f"  Score: {result['score']:.2f}")

        # Save individual field outputs
        if output_dir:
            save_outputs(result, output_dir)

    # Generate mapping report
    if output_dir:
        codesystem_path, markdown_path = save_mapping_report(results, output_dir)
        print(f"\nMapping report generated:")
        print(f"  CodeSystem: {codesystem_path}")
        print(f"  Markdown:   {markdown_path}")

    return results


def save_outputs(result: dict, output_dir: Path):
    """Save ConceptMap and audit JSON for a field."""
    output_dir.mkdir(parents=True, exist_ok=True)
    field_name = result["field_name"]

    candidate = result.get("candidate")
    decision = result.get("decision", "")

    # ConceptMap
    if decision == "mapped" and candidate:
        conceptmap = {
            "resourceType": "ConceptMap",
            "id": f"adni-{field_name.lower()}",
            "meta": {
                "source": "ADNI",
                "date": datetime.utcnow().isoformat() + "Z"
            },
            "status": "final",
            "group": [{
                "source": "http://adni.example.org",
                "target": candidate.get("system", "http://loinc.org"),
                "element": [{
                    "code": field_name,
                    "target": [{
                        "code": candidate.get("code"),
                        "display": candidate.get("display")
                    }]
                }]
            }]
        }
    else:
        conceptmap = {
            "resourceType": "ConceptMap",
            "id": f"adni-{field_name.lower()}",
            "meta": {
                "source": "ADNI",
                "date": datetime.utcnow().isoformat() + "Z"
            },
            "status": "pending",
            "group": [{
                "source": "http://adni.example.org",
                "target": "http://loinc.org",
                "element": [{
                    "code": field_name,
                    "target": []
                }]
            }]
        }

    conceptmap_path = output_dir / f"{field_name}.conceptmap.json"
    with open(conceptmap_path, "w") as f:
        json.dump(conceptmap, f, indent=2)

    # Audit JSON
    scored = result.get("scored_candidates", [])
    top_candidates = get_top_candidates(scored, limit=5)

    # Convert Candidate objects to dicts
    for tc in top_candidates:
        if hasattr(tc.get("candidate"), "model_dump"):
            tc["candidate"] = tc["candidate"].model_dump()
        if tc.get("lookup") and hasattr(tc.get("lookup"), "model_dump"):
            tc["lookup"] = tc["lookup"].model_dump()

    # Convert expand_results Candidates to dicts
    for er in result.get("expand_results", []):
        er["candidates"] = er.get("candidates", [])

    audit = {
        "field": field_name,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "semantic_group": result.get("field_concept", {}).get("semantic_group", ""),
        "decision": decision,
        "score": result.get("score", 0.0),
        "reason": result.get("reason"),
        "search_terms": result.get("search_terms", []),
        "expand_results": result.get("expand_results", []),
        "top_candidates": top_candidates,
        "llm_evaluation": result.get("llm_evaluation"),
        "report": result.get("report"),
    }

    audit_path = output_dir / f"{field_name}.audit.json"
    with open(audit_path, "w") as f:
        json.dump(audit, f, indent=2)

    return conceptmap_path, audit_path
