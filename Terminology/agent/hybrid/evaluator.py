import json
import yaml
import re
from pathlib import Path
from typing import Any
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage


LLM_EVALUATION_PROMPT = """You are a terminology mapping evaluator for ADNI (Alzheimer's Disease Neuroimaging Initiative) clinical data.

## Field Context
- Field Name: {field_name}
- Description: {description}
- Meaning: {meaning}
- Value Type: {value_type}
- Unit: {unit}
- Example Values: {example_values}

## Candidates to Evaluate (top 3 from deterministic scoring)
{candidates_list}

## Your Task
Evaluate each candidate for semantic equivalence to the ADNI field.

Consider CRITICALLY:
1. **Semantic Match**: Does the LOINC code measure the EXACT same thing as the ADNI field?
   - e.g., PIB in ADNI is PET amyloid imaging. Is the LOINC code for PET amyloid imaging?
2. **Method Compatibility**: 
   - PET imaging (brain) vs CSF (spinal fluid) vs blood - these measure the same biomarker but different matrices
   - ADNI field mentions "{method_hint}" - does the LOINC use compatible method?
3. **Specificity**: Is this a full panel/code or just a component?
4. **Clinical Validity**: Would ADNI researchers accept this mapping?

## Scoring Guidelines
- 1.0: EXACT match - same biomarker, same method, same interpretation
- 0.8-0.9: HIGH match - very close, minor differences
- 0.6-0.7: MEDIUM match - same general category but not identical
- 0.4-0.5: LOW match - some relevance but not clinically equivalent
- 0.0-0.3: NO match - different biomarker or method

## Output JSON ONLY (no explanation):
{{
  "evaluations": [
    {{
      "code": "LOINC_CODE",
      "display": "Display name", 
      "score": 0.0-1.0,
      "semantic_match": "EXACT/HIGH/MEDIUM/LOW/NONE",
      "method_compatible": true/false,
      "rationale": "2-3 sentence explanation",
      "perfect_fit": true/false
    }}
  ],
  "recommended_code": "BEST_CODE or null",
  "perfect_fit_found": true/false,
  "report": {{
    "loinc_code": "CODE if perfect_fit_found",
    "semantic_equivalence": "EXACT/HIGH/MEDIUM/LOW",
    "match_details": ["point1", "point2", "point3"],
    "confidence": "HIGH/MEDIUM/LOW",
    "recommendation": "APPROVED/NEEDS_REVIEW/REJECTED"
  }} or null
}}
"""


def load_config() -> dict:
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def to_dict(obj) -> dict:
    """Convert Pydantic model or dict to dict."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return {}


def format_candidates_for_prompt(candidates: list[dict], field_concept: dict) -> str:
    """Format top 3 candidates for LLM evaluation prompt."""
    lines = []
    
    method_hint = field_concept.get("meaning", "")
    if field_concept.get("unit"):
        method_hint += f" (unit: {field_concept['unit']})"
    
    for i, c in enumerate(candidates[:3], 1):
        candidate = to_dict(c.get("candidate", {}))
        lookup = to_dict(c.get("lookup", {}))
        
        display = lookup.get("display", candidate.get("display", ""))
        properties = lookup.get("properties", {})
        
        lines.append(f"""
### Candidate {i}:
- Code: {candidate.get('code', 'N/A')}
- Display: {display}
- Properties: {properties}
- Deterministic Score: {c.get('score', 0):.2f}
""")
    
    return "\n".join(lines)


def evaluate_with_llm(
    top_candidates: list[dict],
    field_concept: dict
) -> dict:
    """Use LLM to evaluate top 3 candidates contextually."""
    config = load_config()
    ollama_config = config.get("ollama", {})

    llm = ChatOllama(
        model=ollama_config.get("model", "llama3.1:latest"),
        temperature=0.0,
    )

    candidates_list = format_candidates_for_prompt(top_candidates, field_concept)

    prompt = LLM_EVALUATION_PROMPT.format(
        field_name=field_concept.get("field_name", ""),
        description=field_concept.get("description", ""),
        meaning=field_concept.get("meaning", ""),
        value_type=field_concept.get("value_type", ""),
        unit=field_concept.get("unit", "N/A"),
        example_values=", ".join(field_concept.get("example_values", [])),
        method_hint=field_concept.get("meaning", ""),
        candidates_list=candidates_list,
    )

    messages = [
        SystemMessage(content="You are a clinical terminology mapping expert. Output valid JSON only."),
        HumanMessage(content=prompt)
    ]

    try:
        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)

        # Extract JSON from response
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return {
                "success": True,
                "evaluation": data,
                "raw_response": content
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "evaluation": None,
            "raw_response": None
        }

    # Fallback if no JSON found
    return {
        "success": False,
        "error": "No valid JSON in LLM response",
        "evaluation": None,
        "raw_response": content if 'content' in dir() else None
    }


def determine_decision(llm_evaluation: dict, deterministic_score: float) -> dict:
    """Determine final decision based on LLM evaluation and deterministic score."""
    
    if not llm_evaluation or not llm_evaluation.get("success"):
        # LLM failed - fallback to deterministic
        return {
            "decision": "human_review",
            "reason": "LLM evaluation failed, requires human review",
            "score": deterministic_score,
            "fallback": True
        }

    evaluation = llm_evaluation.get("evaluation", {})
    perfect_found = evaluation.get("perfect_fit_found", False)
    recommended = evaluation.get("recommended_code")
    report = evaluation.get("report")

    if perfect_found and recommended:
        return {
            "decision": "mapped",
            "reason": "Perfect semantic fit identified by LLM",
            "score": 1.0,
            "recommended_code": recommended,
            "report": report,
            "perfect_fit": True
        }

    # Check evaluation scores
    evaluations = evaluation.get("evaluations", [])
    if evaluations:
        best_score = max(e.get("score", 0) for e in evaluations)
        
        # If no recommended_code from LLM, infer from highest-scored evaluation
        if not recommended:
            best_eval = next((e for e in evaluations if e.get("score") == best_score), None)
            recommended = best_eval.get("code") if best_eval else None
        
        if best_score >= 0.8:
            return {
                "decision": "mapped",
                "reason": f"High confidence match (score: {best_score:.2f})",
                "score": best_score,
                "recommended_code": recommended,
                "report": report,
                "perfect_fit": False
            }
        elif best_score >= 0.6:
            return {
                "decision": "human_review",
                "reason": f"Medium confidence - requires review (score: {best_score:.2f})",
                "score": best_score,
                "recommended_code": recommended,
                "report": None,
                "perfect_fit": False
            }
        else:
            return {
                "decision": "no_mapping",
                "reason": f"Low confidence - no good match (score: {best_score:.2f})",
                "score": best_score,
                "recommended_code": None,
                "report": None,
                "perfect_fit": False
            }

    # No valid evaluation - fallback
    return {
        "decision": "human_review",
        "reason": "No valid LLM evaluation, requires human review",
        "score": deterministic_score,
        "fallback": True
    }
