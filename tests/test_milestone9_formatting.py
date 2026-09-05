import pytest
from app.services.evidence import build_evidence
from app.database import get_db

def test_build_evidence_formats_amounts_correctly():
    # Setup test DB state directly for the test
    import time
    unique_suffix = str(int(time.time() * 1000))
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Insert a mock incident with minor units 50000
        cursor.execute("""
            INSERT INTO incidents (
                incident_type, event_id, razorpay_order_id, razorpay_payment_id,
                amount, currency, razorpay_status, merchant_status, detected_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "PAYMENT_STATE_MISMATCH", f"evt_format_{unique_suffix}", f"ord_{unique_suffix}", f"pay_{unique_suffix}",
            50000, "INR", "captured", "PENDING", "2026-01-01T00:00:00Z", "OPEN"
        ))
        conn.commit()
        incident_id = cursor.lastrowid

        
    # Build evidence
    evidence = build_evidence(incident_id)
        
    # Verify the AI is provided explicitly with major unit formatting
    assert evidence["incident"]["amount"] == 50000
    assert evidence["incident"]["amount_minor"] == 50000
    assert evidence["incident"]["amount_major"] == 500.00
    assert evidence["incident"]["currency"] == "INR"
    
    # Verify the deterministic impact string does not ambiguously use minor units
    # It should say "500.00 INR payment is captured while the merchant order remains PENDING."
    assert "500.00 INR payment is captured" in evidence["deterministic_impact"]
    assert "50000 INR" not in evidence["deterministic_impact"]

