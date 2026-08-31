import json
import yaml
import re
from pathlib import Path
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage


LLM_TERMS_PROMPT = """Given an ADNI field concept, generate up to 4 effective search terms for LOINC terminology lookup.

Rules:
- Each term should be 2-5 words
- Mix of abbreviations (e.g., "PIB PET") and descriptive terms (e.g., "amyloid SUVr")
- Include variations that might match different LOINC entries
- Focus on the core clinical meaning

Input:
- Field Name: {field_name}
- Description: {description}
- Meaning: {meaning}

Output JSON only (no explanation), with exactly this structure:
{{
  "search_terms": ["term1", "term2", "term3", "term4"],
  "rationale": "brief explanation"
}}
"""


def load_config() -> dict:
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def generate_search_terms(field_concept: dict) -> list[str]:
    """Generate 4 search terms using LLM based on field concept."""
    config = load_config()
    ollama_config = config.get("ollama", {})

    llm = ChatOllama(
        model=ollama_config.get("model", "llama3.1:latest"),
        temperature=0.0,
    )

    prompt = LLM_TERMS_PROMPT.format(
        field_name=field_concept.get("field_name", ""),
        description=field_concept.get("description", ""),
        meaning=field_concept.get("meaning", ""),
    )

    messages = [
        SystemMessage(content="You are a terminology mapping assistant that outputs valid JSON only."),
        HumanMessage(content=prompt)
    ]

    try:
        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)

        # Extract JSON from response
        json_match = re.search(r'\{[^{}]*"search_terms"[^{}]*\}', content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            terms = data.get("search_terms", [])
            if terms and len(terms) <= 4:
                return terms

    except Exception as e:
        print(f"LLM error for {field_concept.get('field_name')}: {e}")

    # Fallback: use field_name
    fallback = [field_concept.get("field_name", "")]
    meaning_words = field_concept.get("meaning", "").split()[:3]
    if meaning_words:
        fallback.append(" ".join(meaning_words))
    return fallback[:4]


def generate_search_terms_simple(field_concept: dict) -> list[str]:
    """Fallback: generate simple search terms without LLM."""
    terms = [field_concept.get("field_name", "")]

    # Add first 3 words of meaning
    meaning_words = field_concept.get("meaning", "").split()[:3]
    if meaning_words:
        terms.append(" ".join(meaning_words))

    # Add field name variations
    field_name = field_concept.get("field_name", "")
    if field_name == "MMSE":
        terms.extend(["Mini-Mental", "Mini Mental State"])
    elif field_name == "PIB":
        terms.extend(["Amyloid PET", "Pittsburgh Compound"])
    elif field_name == "AV45":
        terms.extend(["Florbetapir", "Amyloid PET"])
    elif field_name == "FBB":
        terms.extend(["Florbetaben", "Amyloid PET"])
    elif field_name == "FDG":
        terms.extend(["FDG PET brain", "glucose metabolism"])
    elif field_name == "ADAS11" or field_name == "ADAS13":
        terms.extend(["ADAS-Cog", "Alzheimer Assessment"])
    elif field_name == "MOCA":
        terms.extend(["Montreal Cognitive", "MoCA"])

    return list(set(terms))[:4]  # Unique, max 4
