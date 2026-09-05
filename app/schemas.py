from pydantic import BaseModel, Field
from typing import Literal

class AIOutput(BaseModel):
    """The strict schema expected from the AI provider."""
    summary: str
    what_happened: str
    likely_cause: str
    impact: str
    recommended_action: str
    action_type: Literal["INVESTIGATE", "RECONCILE", "REFUND", "CAPTURE", "TRANSFER", "CANCEL", "UNKNOWN"]
    confidence: str
    uncertainty: str

class IncidentAnalysis(BaseModel):
    """The complete analysis object including DB info, evidence, and safety."""
    incident_id: int
    incident_type: str
    summary: str
    what_happened: str
    likely_cause: str
    evidence: dict
    impact: str
    recommended_action: str
    action_type: Literal["INVESTIGATE", "RECONCILE", "REFUND", "CAPTURE", "TRANSFER", "CANCEL", "UNKNOWN"]
    action_safety: Literal["INFORMATIONAL", "REQUIRES_HUMAN_APPROVAL", "BLOCKED"]
    confidence: str
    uncertainty: str
    generated_at: str

class IncidentAnalysisResponse(BaseModel):
    """The public API response schema and database representation."""
    id: int
    incident_id: int
    summary: str
    what_happened: str
    likely_cause: str
    impact: str
    recommended_action: str
    action_type: Literal["INVESTIGATE", "RECONCILE", "REFUND", "CAPTURE", "TRANSFER", "CANCEL", "UNKNOWN"]
    action_safety: Literal["INFORMATIONAL", "REQUIRES_HUMAN_APPROVAL", "BLOCKED"]
    confidence: str
    uncertainty: str
    created_at: str

class AuditTrailResponse(BaseModel):
    """The schema for an audit trail entry."""
    id: int
    incident_id: int
    action: str
    reason: str
    safety_classification: str
    timestamp: str

