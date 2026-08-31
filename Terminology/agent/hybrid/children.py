import json
from pathlib import Path
from typing import Any
from agent.terminology.models import Candidate


def load_fields() -> list[dict]:
    fields_path = Path(__file__).parent.parent.parent / "fields.json"
    with open(fields_path) as f:
        data = json.load(f)
    return data.get("fields", [])


def get_field_concept(field_name: str) -> dict | None:
    """Get field concept by name."""
    fields = load_fields()
    for f in fields:
        if f.get("field_name") == field_name:
            return f
    return None


def has_suggested_children(field_name: str) -> bool:
    """Check if field has suggested LOINC children in fields.json."""
    field = get_field_concept(field_name)
    if field:
        suggested = field.get("suggested_loinc_code")
        # Check if it's a child code (specific panel, not parent form)
        return suggested and suggested.startswith("892")
    return False


def get_suggested_code(field_name: str) -> str | None:
    """Get the suggested LOINC code from fields.json."""
    field = get_field_concept(field_name)
    if field:
        return field.get("suggested_loinc_code")
    return None


def generate_child_search_terms(field_concept: dict) -> list[str]:
    """Generate search terms to find child entries."""
    field_name = field_concept.get("field_name", "")
    meaning = field_concept.get("meaning", "")
    terms = []

    # ECog fields - use "panel" + domain + ECog variant
    if "Ecog" in field_name:
        # Determine if it's Participant (self) or Study Partner (informant)
        variant = "[ECog.Partner]" if "SP" in field_name else "[ECog]"

        # Extract domain from field name
        if "Mem" in field_name:
            domain = "Memory"
        elif "Lang" in field_name:
            domain = "Language"
        elif "Visspat" in field_name:
            domain = "Visuospatial"
        elif "Plan" in field_name:
            domain = "Planning"
        elif "Organ" in field_name:
            domain = "Organization"
        elif "Divatt" in field_name:
            domain = "Divided attention"
        elif "Total" in field_name:
            domain = "Total"
        else:
            domain = ""

        if domain:
            terms.extend([
                f"{domain} panel {variant}".strip(),
                f"{domain} {variant}".strip(),
            ])

    # ADAS fields
    elif "ADAS" in field_name:
        terms.extend([
            "ADAS-Cog",
            "Alzheimer Assessment Scale",
        ])

    # RAVLT fields
    elif "RAVLT" in field_name:
        terms.extend([
            "RAVLT",
            "Rey Auditory Verbal Learning",
        ])

    # Generic fallback: add "panel" to meaning
    if not terms and meaning:
        words = meaning.split()
        if len(words) >= 2:
            terms.append(f"{' '.join(words[:3])} panel")

    return terms


def find_child_candidates(
    candidates: list[Any],
    field_concept: dict,
    terminology_client,
    vs_url: str = "http://loinc.org/vs"
) -> list[Any]:
    """Find child codes for parent candidates.

    Args:
        candidates: List of parent candidates from expand
        field_concept: Field concept dict with field_name, meaning, etc.
        terminology_client: TerminologyClient instance
        vs_url: Value set URL for expansion

    Returns:
        List of child candidates (may be empty)
    """
    if not candidates:
        return []

    field_name = field_concept.get("field_name", "")
    children = []

    # First check if we have a suggested code in fields.json
    suggested_code = get_suggested_code(field_name)
    if suggested_code:
        # Try to find this specific code
        for cand in candidates:
            if cand.code == suggested_code:
                return []  # Parent is already the child we want

        # Try to lookup the suggested code directly
        try:
            lookup = terminology_client.lookup(system="http://loinc.org", code=suggested_code)
            if lookup:
                child_cand = Candidate(
                    code=suggested_code,
                    display=lookup.display,
                    system="http://loinc.org"
                )
                children.append(child_cand)
                return children
        except Exception:
            pass

    # Check if any parent candidate is a "form" or "panel" type
    has_parent_candidates = False
    for candidate in candidates:
        display_lower = candidate.display.lower()
        if any(kw in display_lower for kw in ["form", "panel", "report", "everyday cognition"]):
            has_parent_candidates = True
            break

    if not has_parent_candidates:
        return []

    # Generate child search terms
    child_terms = generate_child_search_terms(field_concept)

    # Search for children using generated terms
    for term in child_terms[:3]:  # Limit to 3 terms to avoid too many API calls
        try:
            result = terminology_client.expand(
                vs_url=vs_url,
                filter_text=term,
                count=10
            )

            for child in result.candidates:
                # Skip if it's the same as a parent
                is_parent = False
                for parent in candidates:
                    if child.code == parent.code:
                        is_parent = True
                        break

                if not is_parent:
                    # Avoid duplicates
                    if not any(c.code == child.code for c in children):
                        children.append(child)

        except Exception as e:
            # Continue to next term if one fails
            continue

    return children


def deduplicate_candidates(candidates: list[Any]) -> list[Any]:
    """Remove duplicate candidates by code."""
    seen = set()
    unique = []

    for c in candidates:
        if c.code not in seen:
            seen.add(c.code)
            unique.append(c)

    return unique
