import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
import json
import hmac
import hashlib
from unittest.mock import patch, AsyncMock

client = TestClient(app)

def sign_payload(payload: dict, secret: str = "test_secret") -> str:
    body = json.dumps(payload).encode('utf-8')
    return hmac.new(key=secret.encode('utf-8'), msg=body, digestmod=hashlib.sha256).hexdigest()

def send_webhook(event_id, event_type, payment_status, order_id, payment_id="pay_mock123"):
    payload = {
        "event": event_type,
        "created_at": 1234567890,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": 500,
                    "currency": "INR",
                    "status": payment_status
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    headers = {
        "x-razorpay-event-id": event_id,
        "X-Razorpay-Signature": sign_payload(payload)
    }
    return client.post("/webhooks/razorpay", content=body, headers=headers)

@patch("app.routes.merchant.razorpay_client.create_order", new_callable=AsyncMock)
def test_reconciliation_updates_order(mock_create_order):
    # 1. Create order
    mock_create_order.return_value = {"id": "order_recon_1", "amount": 500, "currency": "INR", "status": "created"}
    client.post("/api/merchant/orders", json={"amount": 500, "currency": "INR"})
    
    # 2. Webhook triggers mismatch incident
    send_webhook("evt_recon_1", "payment.captured", "captured", "order_recon_1")
    
    # 3. Get incident ID
    inc_resp = client.get("/api/incidents")
    incidents = inc_resp.json()
    incident_id = next(i["id"] for i in incidents if i["razorpay_order_id"] == "order_recon_1")
    
    # 4. Resolve incident
    res = client.post(f"/api/incidents/{incident_id}/resolve")
    assert res.status_code == 200
    assert res.json()["reconciled"] == True
    
    # 5. Check order status
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM merchant_orders WHERE razorpay_order_id = 'order_recon_1'")
        assert cursor.fetchone()[0] == "PAID"
        
        # Verify audit trail
        cursor.execute("SELECT action FROM audit_trail WHERE incident_id = ? ORDER BY id ASC", (incident_id,))
        actions = [row[0] for row in cursor.fetchall()]
        assert "STATE_RECONCILED" in actions
        assert "RESOLVE_INCIDENT" in actions

@patch("app.routes.merchant.razorpay_client.create_order", new_callable=AsyncMock)
def test_reconciliation_already_paid(mock_create_order):
    mock_create_order.return_value = {"id": "order_recon_2", "amount": 500, "currency": "INR", "status": "created"}
    client.post("/api/merchant/orders", json={"amount": 500, "currency": "INR"})
    
    # Trigger mismatch
    send_webhook("evt_recon_2", "payment.captured", "captured", "order_recon_2")
    
    inc_resp = client.get("/api/incidents")
    incident_id = next(i["id"] for i in inc_resp.json() if i["razorpay_order_id"] == "order_recon_2")
    
    # Mutate to PAID manually (simulating external update)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE merchant_orders SET status = 'PAID' WHERE razorpay_order_id = 'order_recon_2'")
        conn.commit()
    
    # Resolve
    res = client.post(f"/api/incidents/{incident_id}/resolve")
    assert res.status_code == 200
    assert res.json()["reconciled"] == False  # Already paid, shouldn't duplicate

def test_resolve_already_resolved():
    # Attempt to resolve the first incident again
    inc_resp = client.get("/api/incidents")
    incident_id = next(i["id"] for i in inc_resp.json() if i["razorpay_order_id"] == "order_recon_1")
    
    res = client.post(f"/api/incidents/{incident_id}/resolve")
    assert res.status_code == 400
    assert "Cannot resolve" in res.json()["detail"]

def test_resolve_missing_merchant_order():
    # Insert a fake incident with a non-existent order
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO incidents (event_id, razorpay_order_id, razorpay_status, merchant_status, incident_type, status)
            VALUES ('evt_fake', 'order_fake', 'captured', 'PENDING', 'PAYMENT_STATE_MISMATCH', 'OPEN')
        """)
        incident_id = cursor.lastrowid
        conn.commit()
        
    res = client.post(f"/api/incidents/{incident_id}/resolve")
    assert res.status_code == 404
    assert "Affected merchant order not found" in res.json()["detail"]

def test_get_merchant_orders():
    res = client.get("/api/merchant/orders")
    assert res.status_code == 200
    orders = res.json()
    assert isinstance(orders, list)
    # Check if order_recon_1 is in the list
    assert any(o["razorpay_order_id"] == "order_recon_1" for o in orders)

def test_get_merchant_order_events():
    res = client.get("/api/merchant/orders/order_recon_1/events")
    assert res.status_code == 200
    events = res.json()
    assert isinstance(events, list)
    assert any(e["event_type"] == "payment.captured" for e in events)
    # Ensure they have received_at and created_at
    for event in events:
        assert "received_at" in event
        assert "created_at" in event

def test_get_config():
    res = client.get("/api/config")
    assert res.status_code == 200
    config = res.json()
    assert "razorpay_key_id" in config
