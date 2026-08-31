from agent.terminology.models import Candidate, LookupResult


def score_candidate(
    candidate: Candidate,
    lookup_result: LookupResult | None,
    field_concept: dict
) -> float:
    """Score a candidate based on deterministic features.

    Scoring weights:
    - System match: 0.3
    - Not LP-prefix: 0.2
    - Numeric LOINC code: 0.2
    - Has properties: 0.2
    - Display contains field name: 0.1
    - Suggested code match: 0.15 (bonus for known correct child codes)

    Max score: 1.15
    """
    score = 0.0

    # System match (0.3)
    target_system = field_concept.get("system_hint", "http://loinc.org")
    if lookup_result and lookup_result.system == target_system:
        score += 0.3
    elif lookup_result and lookup_result.system:
        # Partial match - code exists in system
        score += 0.1

    # Not LP-prefix (0.2) - prefer standard LOINC over local codes
    if not candidate.code.startswith("LP"):
        score += 0.2

    # Numeric LOINC pattern (0.2) - prefer numeric codes
    if candidate.code.isdigit():
        score += 0.2

    # Has properties (0.2)
    if lookup_result and lookup_result.properties:
        score += 0.2

    # Display contains field name (0.1)
    field_name = field_concept.get("field_name", "").lower()
    if lookup_result and lookup_result.display:
        display_lower = lookup_result.display.lower()
        # Check for field name or common variations
        if field_name in display_lower:
            score += 0.1
        # Check for abbreviations/variations
        elif field_name == "mmse" and "mini" in display_lower:
            score += 0.1
        elif field_name == "pib" and "amyloid" in display_lower:
            score += 0.1
        elif field_name == "fdg" and "glucose" in display_lower:
            score += 0.1
        elif field_name == "moca" and "montreal" in display_lower:
            score += 0.1

    # Suggested code match (0.15 bonus) - for known correct child codes
    suggested_code = field_concept.get("suggested_loinc_code")
    if suggested_code and candidate.code == suggested_code:
        score += 0.15

    return score


def score_candidates(
    candidates: list[dict],
    field_concept: dict
) -> list[dict]:
    """Score all candidates and return sorted list."""
    scored = []

    for item in candidates:
        candidate = item["candidate"]
        lookup = item.get("lookup")

        score = score_candidate(candidate, lookup, field_concept)

        scored.append({
            "candidate": candidate,
            "lookup": lookup,
            "score": score,
            "code": candidate.code,
            "display": candidate.display,
            "system": candidate.system,
        })

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    return scored
