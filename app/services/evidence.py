from app.database import get_db

def build_evidence(incident_id: int) -> dict:
    """
    Builds a deterministic, sanitized evidence package for the AI.
    Calculates deterministic impact based purely on factual DB state.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Fetch incident
        cursor.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
        incident_row = cursor.fetchone()
        if not incident_row:
            raise ValueError(f"Incident {incident_id} not found.")
            
        incident = dict(incident_row)
        
        # 2. Fetch related merchant order
        merchant_order = None
        if incident.get("razorpay_order_id"):
            cursor.execute("SELECT * FROM merchant_orders WHERE razorpay_order_id = ?", (incident["razorpay_order_id"],))
            mo_row = cursor.fetchone()
            if mo_row:
                merchant_order = dict(mo_row)
                
        # 3. Fetch related webhooks (Sanitized)
        cursor.execute("""
            SELECT event_id, event_type, entity_id, razorpay_order_id, razorpay_payment_id, amount, currency, payment_status, created_at, received_at
            FROM webhook_events 
            WHERE razorpay_order_id = ?
        """, (incident.get("razorpay_order_id"),))
        webhook_rows = cursor.fetchall()
        webhooks = [dict(r) for r in webhook_rows]

        # 4. Deterministic Impact Calculation
        impact = "No impact calculated."
        if incident["incident_type"] == "PAYMENT_STATE_MISMATCH":
            impact = f"{incident['amount']} {incident['currency']} payment is {incident['razorpay_status']} while the merchant order remains {incident['merchant_status']}."
        
        return {
            "incident": {
                "id": incident["id"],
                "incident_type": incident["incident_type"],
                "event_id": incident["event_id"],
                "razorpay_order_id": incident["razorpay_order_id"],
                "razorpay_payment_id": incident["razorpay_payment_id"],
                "amount": incident["amount"],
                "currency": incident["currency"],
                "razorpay_status": incident["razorpay_status"],
                "merchant_status": incident["merchant_status"],
                "detected_at": incident["detected_at"]
            },
            "merchant_order": merchant_order,
            "webhooks": webhooks,
            "deterministic_impact": impact
        }
