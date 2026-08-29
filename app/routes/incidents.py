from fastapi import APIRouter, HTTPException
from app.database import get_db

router = APIRouter(
    prefix="/api/incidents",
    tags=["incidents"]
)

@router.get("")
async def list_incidents():
    """List all detected incidents."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM incidents ORDER BY detected_at DESC")
        incidents = [dict(row) for row in cursor.fetchall()]
        return incidents

@router.get("/{incident_id}")
async def get_incident(incident_id: int):
    """Get details of a specific incident."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
        incident = cursor.fetchone()
        
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
            
        return dict(incident)

from fastapi import Depends
from app.services.investigator import get_ai_provider, AIProvider
from app.services.evidence import build_evidence
from app.services.safety import enforce_safety
import json
from datetime import datetime, timezone
import sqlite3

from app.schemas import IncidentAnalysisResponse

@router.get("/{incident_id}/analysis", response_model=IncidentAnalysisResponse)
async def get_incident_analysis(incident_id: int):
    """Read-only. Returns existing analysis or 404."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM incident_analyses WHERE incident_id = ?", (incident_id,))
        analysis_row = cursor.fetchone()
        
        if not analysis_row:
            raise HTTPException(status_code=404, detail="Analysis not found")
            
        # Parse evidence string back to dict
        analysis = dict(analysis_row)
        # Assuming we didn't store evidence in DB per schema, but wait, 
        # incident_analyses schema: summary, what_happened, likely_cause, impact, recommended_action, action_type, action_safety, confidence, uncertainty, created_at.
        # So we don't return the full evidence block from the DB, just the analysis.
        return analysis

@router.post("/{incident_id}/analysis", response_model=IncidentAnalysisResponse)
async def generate_incident_analysis(incident_id: int, provider: AIProvider = Depends(get_ai_provider)):
    """Generates the analysis if not exists. Uses AI provider."""
    # 1. Check if exists (Idempotency)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM incident_analyses WHERE incident_id = ?", (incident_id,))
        existing = cursor.fetchone()
        if existing:
            return dict(existing)
            
    # 2. Build Evidence
    try:
        evidence = build_evidence(incident_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
        
    incident = evidence["incident"]
    generated_at = datetime.now(timezone.utc).isoformat()
    
    # 3. AI Analysis
    ai_output = provider.analyze(evidence)
    
    # 4. Deterministic Safety Gate
    final_analysis = enforce_safety(ai_output, incident, evidence, generated_at)
    
    # 5. Persist
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO incident_analyses (
                    incident_id, summary, what_happened, likely_cause, impact,
                    recommended_action, action_type, action_safety, confidence, uncertainty
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                final_analysis.incident_id,
                final_analysis.summary,
                final_analysis.what_happened,
                final_analysis.likely_cause,
                final_analysis.impact,
                final_analysis.recommended_action,
                final_analysis.action_type,
                final_analysis.action_safety,
                final_analysis.confidence,
                final_analysis.uncertainty
            ))
            
            cursor.execute("""
                INSERT INTO audit_trail (
                    incident_id, action, reason, safety_classification
                ) VALUES (?, ?, ?, ?)
            """, (
                final_analysis.incident_id,
                final_analysis.recommended_action,
                "AI Recommendation",
                final_analysis.action_safety
            ))
            conn.commit()
            
            # Fetch the inserted row to return with ID
            cursor.execute("SELECT * FROM incident_analyses WHERE incident_id = ?", (incident_id,))
            return dict(cursor.fetchone())
            
        except sqlite3.IntegrityError:
            # Race condition, already inserted
            cursor.execute("SELECT * FROM incident_analyses WHERE incident_id = ?", (incident_id,))
            return dict(cursor.fetchone())

@router.post("/{incident_id}/resolve")
async def resolve_incident(incident_id: int):
    """Resolves an open incident and records it in the audit trail."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Verify incident exists and check status
        cursor.execute("SELECT status FROM incidents WHERE id = ?", (incident_id,))
        incident_row = cursor.fetchone()
        
        if not incident_row:
            raise HTTPException(status_code=404, detail="Incident not found.")
            
        current_status = incident_row["status"]
        if current_status != "OPEN":
            raise HTTPException(status_code=400, detail=f"Cannot resolve incident with status: {current_status}")
            
        # 2. Update status to RESOLVED
        resolved_at = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE incidents SET status = 'RESOLVED', resolved_at = ? WHERE id = ?",
            (resolved_at, incident_id)
        )
        
        # 3. Add audit trail entry
        cursor.execute("""
            INSERT INTO audit_trail (
                incident_id, action, reason, safety_classification, timestamp
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            incident_id,
            "RESOLVE_INCIDENT",
            "Human requested incident resolution",
            "INFORMATIONAL",
            resolved_at
        ))
        
        conn.commit()
        
        return {"status": "success", "detail": "Incident resolved."}
