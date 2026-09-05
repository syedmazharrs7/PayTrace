import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
import json
import hmac
import hashlib
from unittest.mock import patch, AsyncMock
from app.razorpay_client import RazorpayAPIError

client = TestClient(app)

def sign_payload(payload: dict, secret: str = "test_secret") -> str:
    body = json.dumps(payload).encode('utf-8')
    return hmac.new(key=secret.encode('utf-8'), msg=body, digestmod=hashlib.sha256).hexdigest()

# -------------------------------------------------------------------
# A & B: ORDER CREATION
# -------------------------------------------------------------------

@patch("app.routes.merchant.razorpay_client.create_order", new_callable=AsyncMock)
def test_successful_razorpay_order_creation(mock_create_order):
    mock_create_order.return_value = {
        "id": "order_mocked123",
        "amount": 50000,
        "currency": "INR",
        "receipt": "rcpt_mock",
        "status": "created"
    }
    
    response = client.post("/api/merchant/orders", json={
        "amount": 50000,
        "currency": "INR"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["razorpay_order_id"] == "order_mocked123"
    assert data["amount"] == 50000
    assert data["status"] == "PENDING"
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM merchant_orders WHERE razorpay_order_id = 'order_mocked123'")
        assert cursor.fetchone() is not None

@patch("app.routes.merchant.razorpay_client.create_order", new_callable=AsyncMock)
def test_razorpay_api_failure(mock_create_order):
    mock_create_order.side_effect = RazorpayAPIError("Simulated failure", status_code=500)
    
    response = client.post("/api/merchant/orders", json={
        "amount": 50000,
        "currency": "INR"
    })
    
    assert response.status_code == 502
    assert "Failed to create order" in response.json()["detail"]

# -------------------------------------------------------------------
# C, D, E, F: LIFECYCLE WEBHOOKS
# -------------------------------------------------------------------

def send_webhook(event_id, event_type, payment_status, order_id, payment_id="pay_mock123"):
    payload = {
        "event": event_type,
        "created_at": 1234567890,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": 50000,
                    "currency": "INR",
                    "status": payment_status
                }
            }
        }
    }
    # Adjust for order.paid
    if event_type.startswith("order."):
        payload["payload"] = {
            "order": {
                "entity": {
                    "id": order_id,
                    "amount": 50000,
                    "currency": "INR",
                    "status": payment_status
                }
            }
        }
        
    body = json.dumps(payload).encode('utf-8')
    headers = {
        "x-razorpay-event-id": event_id,
        "X-Razorpay-Signature": hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
    }
    return client.post("/webhooks/razorpay", content=body, headers=headers)

@patch("app.routes.merchant.razorpay_client.create_order", new_callable=AsyncMock)
def test_lifecycle_authorized_and_failed(mock_create_order):
    # Setup merchant order
    mock_create_order.return_value = {"id": "order_lifecyc_1", "amount": 50000, "currency": "INR", "status": "created"}
    client.post("/api/merchant/orders", json={"amount": 50000, "currency": "INR"})
    
    # Send payment.authorized
    r1 = send_webhook("evt_auth_1", "payment.authorized", "authorized", "order_lifecyc_1")
    assert r1.status_code == 200
    
    # Send payment.failed
    r2 = send_webhook("evt_fail_1", "payment.failed", "failed", "order_lifecyc_1")
    assert r2.status_code == 200
    
    with get_db() as conn:
        cursor = conn.cursor()
        # Verify 2 webhooks persisted
        cursor.execute("SELECT COUNT(*) FROM webhook_events WHERE razorpay_order_id = 'order_lifecyc_1'")
        assert cursor.fetchone()[0] == 2
        
        # Verify NO incident created
        cursor.execute("SELECT COUNT(*) FROM incidents WHERE razorpay_order_id = 'order_lifecyc_1'")
        assert cursor.fetchone()[0] == 0

@patch("app.routes.merchant.razorpay_client.create_order", new_callable=AsyncMock)
def test_payment_captured_mismatch(mock_create_order):
    mock_create_order.return_value = {"id": "order_mismatch", "amount": 500, "currency": "INR", "status": "created"}
    client.post("/api/merchant/orders", json={"amount": 500, "currency": "INR"})
    
    # Send captured
    send_webhook("evt_cap_1", "payment.captured", "captured", "order_mismatch")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM incidents WHERE razorpay_order_id = 'order_mismatch'")
        assert cursor.fetchone() is not None

@patch("app.routes.merchant.razorpay_client.create_order", new_callable=AsyncMock)
def test_payment_captured_matching(mock_create_order):
    mock_create_order.return_value = {"id": "order_match", "amount": 500, "currency": "INR", "status": "created"}
    client.post("/api/merchant/orders", json={"amount": 500, "currency": "INR"})
    
    # Manually update merchant to PAID
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE merchant_orders SET status = 'PAID' WHERE razorpay_order_id = 'order_match'")
        conn.commit()
    
    # Send captured
    send_webhook("evt_cap_2", "payment.captured", "captured", "order_match")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM incidents WHERE razorpay_order_id = 'order_match'")
        assert cursor.fetchone()[0] == 0

# -------------------------------------------------------------------
# G, H: ORDER PAID & DUPLICATES
# -------------------------------------------------------------------

@patch("app.routes.merchant.razorpay_client.create_order", new_callable=AsyncMock)
def test_order_paid_and_duplicates(mock_create_order):
    mock_create_order.return_value = {"id": "order_paid_dup", "amount": 500, "currency": "INR", "status": "created"}
    client.post("/api/merchant/orders", json={"amount": 500, "currency": "INR"})
    
    # Send captured (creates incident)
    send_webhook("evt_cap_3", "payment.captured", "captured", "order_paid_dup")
    
    # Send duplicate captured (same event id)
    send_webhook("evt_cap_3", "payment.captured", "captured", "order_paid_dup")
    
    # Send order.paid
    send_webhook("evt_ord_paid_1", "order.paid", "paid", "order_paid_dup")
    
    with get_db() as conn:
        cursor = conn.cursor()
        # Should have 2 webhook events (captured, order.paid), duplicate is ignored
        cursor.execute("SELECT COUNT(*) FROM webhook_events WHERE razorpay_order_id = 'order_paid_dup'")
        assert cursor.fetchone()[0] == 2
        
        # Should have exactly 1 incident
        cursor.execute("SELECT COUNT(*) FROM incidents WHERE razorpay_order_id = 'order_paid_dup'")
        assert cursor.fetchone()[0] == 1

# -------------------------------------------------------------------
# I, J: OUT OF ORDER & RETRIES
# -------------------------------------------------------------------

@patch("app.routes.merchant.razorpay_client.create_order", new_callable=AsyncMock)
def test_out_of_order(mock_create_order):
    mock_create_order.return_value = {"id": "order_ooo", "amount": 500, "currency": "INR", "status": "created"}
    client.post("/api/merchant/orders", json={"amount": 500, "currency": "INR"})
    
    # Send captured BEFORE authorized
    send_webhook("evt_cap_ooo", "payment.captured", "captured", "order_ooo")
    send_webhook("evt_auth_ooo", "payment.authorized", "authorized", "order_ooo")
    
    with get_db() as conn:
        cursor = conn.cursor()
        # Incident should exist from captured
        cursor.execute("SELECT COUNT(*) FROM incidents WHERE razorpay_order_id = 'order_ooo'")
        assert cursor.fetchone()[0] == 1

@patch("app.routes.merchant.razorpay_client.create_order", new_callable=AsyncMock)
def test_failed_then_captured(mock_create_order):
    mock_create_order.return_value = {"id": "order_retry", "amount": 500, "currency": "INR", "status": "created"}
    client.post("/api/merchant/orders", json={"amount": 500, "currency": "INR"})
    
    # Customer tries and fails
    send_webhook("evt_fail_retry", "payment.failed", "failed", "order_retry")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM incidents WHERE razorpay_order_id = 'order_retry'")
        assert cursor.fetchone()[0] == 0  # No incident on failure
        
    # Customer tries again and succeeds
    send_webhook("evt_cap_retry", "payment.captured", "captured", "order_retry", payment_id="pay_retry2")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM incidents WHERE razorpay_order_id = 'order_retry'")
        assert cursor.fetchone()[0] == 1  # Incident created on capture mismatch
