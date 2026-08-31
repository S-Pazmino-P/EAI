from typing import TypedDict


class DecisionResult(TypedDict):
    decision: str
    candidate: dict | None
    score: float
    reason: str | None


def apply_thresholds(
    scored_candidates: list[dict],
    field_concept: dict,
    thresholds: dict | None = None
) -> DecisionResult:
    """Apply decision thresholds to scored candidates.

    Default thresholds:
    - mapped: >= 0.7
    - human_review: >= 0.4
    - no_mapping: < 0.4
    """
    if thresholds is None:
        thresholds = {
            "mapped": 0.7,
            "human_review": 0.4,
        }

    mapped_threshold = thresholds.get("mapped", 0.7)
    human_review_threshold = thresholds.get("human_review", 0.4)

    if not scored_candidates:
        return {
            "decision": "no_mapping",
            "candidate": None,
            "score": 0.0,
            "reason": "No candidates found from terminology server"
        }

    best = scored_candidates[0]
    score = best["score"]

    if score >= mapped_threshold:
        return {
            "decision": "mapped",
            "candidate": best,
            "score": score,
            "reason": f"High confidence match (score: {score:.2f})"
        }
    elif score >= human_review_threshold:
        return {
            "decision": "human_review",
            "candidate": best,
            "score": score,
            "reason": f"Medium confidence - requires review (score: {score:.2f})"
        }
    else:
        return {
            "decision": "no_mapping",
            "candidate": best,
            "score": score,
            "reason": f"Low confidence - no good match (score: {score:.2f})"
        }


def get_top_candidates(scored_candidates: list[dict], limit: int = 3) -> list[dict]:
    """Get top N candidates for audit trail."""
    return scored_candidates[:limit]
