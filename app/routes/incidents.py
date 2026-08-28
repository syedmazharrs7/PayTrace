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
