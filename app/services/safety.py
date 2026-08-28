from app.schemas import AIOutput, IncidentAnalysis

def enforce_safety(ai_output: AIOutput, incident: dict, evidence: dict, generated_at: str) -> IncidentAnalysis:
    """
    Applies deterministic safety rules to map the AI's action_type to an action_safety classification.
    """
    action_type = ai_output.action_type
    
    # Deterministic mapping
    if action_type == "INVESTIGATE":
        action_safety = "INFORMATIONAL"
    elif action_type in ["RECONCILE", "CANCEL"]:
        action_safety = "REQUIRES_HUMAN_APPROVAL"
    elif action_type in ["REFUND", "CAPTURE", "TRANSFER", "UNKNOWN"]:
        action_safety = "BLOCKED"
    else:
        # Fallback for unrecognized action types
        action_safety = "BLOCKED"

    return IncidentAnalysis(
        incident_id=incident["id"],
        incident_type=incident["incident_type"],
        summary=ai_output.summary,
        what_happened=ai_output.what_happened,
        likely_cause=ai_output.likely_cause,
        evidence=evidence,
        impact=ai_output.impact,
        recommended_action=ai_output.recommended_action,
        action_type=action_type,
        action_safety=action_safety,
        confidence=ai_output.confidence,
        uncertainty=ai_output.uncertainty,
        generated_at=generated_at
    )
