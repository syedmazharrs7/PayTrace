import pytest
from fastapi.testclient import TestClient
import os
import hmac
import hashlib
import json
import sqlite3

# Set test DB path before importing the app
TEST_DB = "test_paytrace.db"
os.environ["PAYTRACE_DB_PATH"] = TEST_DB
os.environ["SKIP_DB_INIT"] = "true"

from app.main import app
from app.database import init_db, get_db
from app import config

client = TestClient(app)

config.RAZORPAY_WEBHOOK_SECRET = "test_secret"

@pytest.fixture(autouse=True)
def setup_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def generate_signature(body: bytes, secret: str = "test_secret") -> str:
    return hmac.new(
        key=secret.encode('utf-8'),
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()

def test_merchant_order_creation():
    response = client.post("/api/merchant/orders", json={
        "razorpay_order_id": "order_1",
        "amount": 1000,
        "currency": "INR"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["razorpay_order_id"] == "order_1"
    assert data["status"] == "PENDING"

def test_merchant_order_retrieval():
    client.post("/api/merchant/orders", json={
        "razorpay_order_id": "order_2",
        "amount": 2000,
        "currency": "INR"
    })
    response = client.get("/api/merchant/orders/order_2")
    assert response.status_code == 200
    assert response.json()["razorpay_order_id"] == "order_2"

def test_merchant_status_update():
    client.post("/api/merchant/orders", json={
        "razorpay_order_id": "order_3",
        "amount": 3000,
        "currency": "INR"
    })
    response = client.patch("/api/merchant/orders/order_3/status", json={"status": "PAID"})
    assert response.status_code == 200
    assert response.json()["status"] == "PAID"

def test_captured_payment_pending_order_incident():
    client.post("/api/merchant/orders", json={
        "razorpay_order_id": "order_4",
        "amount": 4000,
        "currency": "INR"
    })
    
    payload = {
        "event": "payment.captured",
        "created_at": 1234567890,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_4",
                    "order_id": "order_4",
                    "amount": 4000,
                    "currency": "INR",
                    "status": "captured"
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    signature = generate_signature(body)
    
    response = client.post("/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": "evt_4",
        "Content-Type": "application/json"
    })
    assert response.status_code == 200
    
    inc_resp = client.get("/api/incidents")
    assert inc_resp.status_code == 200
    incidents = inc_resp.json()
    assert len(incidents) == 1
    assert incidents[0]["razorpay_order_id"] == "order_4"
    assert incidents[0]["incident_type"] == "PAYMENT_STATE_MISMATCH"

def test_captured_payment_paid_order_no_incident():
    client.post("/api/merchant/orders", json={
        "razorpay_order_id": "order_5",
        "amount": 5000,
        "currency": "INR"
    })
    client.patch("/api/merchant/orders/order_5/status", json={"status": "PAID"})
    
    payload = {
        "event": "payment.captured",
        "created_at": 1234567890,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_5",
                    "order_id": "order_5",
                    "amount": 5000,
                    "currency": "INR",
                    "status": "captured"
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    signature = generate_signature(body)
    
    response = client.post("/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": "evt_5",
        "Content-Type": "application/json"
    })
    assert response.status_code == 200
    
    inc_resp = client.get("/api/incidents")
    incidents = inc_resp.json()
    assert len(incidents) == 0

def test_captured_payment_failed_order_no_incident():
    client.post("/api/merchant/orders", json={
        "razorpay_order_id": "order_6",
        "amount": 6000,
        "currency": "INR"
    })
    client.patch("/api/merchant/orders/order_6/status", json={"status": "FAILED"})
    
    payload = {
        "event": "payment.captured",
        "created_at": 1234567890,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_6",
                    "order_id": "order_6",
                    "amount": 6000,
                    "currency": "INR",
                    "status": "captured"
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    signature = generate_signature(body)
    
    response = client.post("/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": "evt_6",
        "Content-Type": "application/json"
    })
    assert response.status_code == 200
    
    inc_resp = client.get("/api/incidents")
    incidents = inc_resp.json()
    assert len(incidents) == 0

def test_captured_payment_missing_order_no_incident():
    payload = {
        "event": "payment.captured",
        "created_at": 1234567890,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_7",
                    "order_id": "order_7_missing",
                    "amount": 7000,
                    "currency": "INR",
                    "status": "captured"
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    signature = generate_signature(body)
    
    response = client.post("/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": "evt_7",
        "Content-Type": "application/json"
    })
    assert response.status_code == 200
    
    inc_resp = client.get("/api/incidents")
    incidents = inc_resp.json()
    assert len(incidents) == 0

def test_duplicate_webhook_no_duplicate_incident():
    client.post("/api/merchant/orders", json={
        "razorpay_order_id": "order_8",
        "amount": 8000,
        "currency": "INR"
    })
    
    payload = {
        "event": "payment.captured",
        "created_at": 1234567890,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_8",
                    "order_id": "order_8",
                    "amount": 8000,
                    "currency": "INR",
                    "status": "captured"
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    signature = generate_signature(body)
    
    response1 = client.post("/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": "evt_8",
        "Content-Type": "application/json"
    })
    assert response1.status_code == 200
    
    response2 = client.post("/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": "evt_8",
        "Content-Type": "application/json"
    })
    assert response2.status_code == 200
    
    inc_resp = client.get("/api/incidents")
    incidents = inc_resp.json()
    assert len(incidents) == 1
    assert incidents[0]["razorpay_order_id"] == "order_8"

def test_invalid_signature_rejected():
    payload = {"event": "payment.captured"}
    body = json.dumps(payload).encode('utf-8')
    response = client.post("/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": "invalid_signature",
        "x-razorpay-event-id": "evt_9",
        "Content-Type": "application/json"
    })
    assert response.status_code == 400

def test_order_paid_event_stored_no_incident():
    payload = {
        "event": "order.paid",
        "created_at": 1234567890,
        "payload": {
            "order": {
                "entity": {
                    "id": "order_10"
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    signature = generate_signature(body)
    
    response = client.post("/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": "evt_10",
        "Content-Type": "application/json"
    })
    assert response.status_code == 200
    
    inc_resp = client.get("/api/incidents")
    incidents = inc_resp.json()
    assert len(incidents) == 0

def test_payment_captured_then_merchant_order_incident():
    # 1. Trigger webhook first (order does not exist yet)
    payload = {
        "event": "payment.captured",
        "created_at": 1234567890,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_11",
                    "order_id": "order_11",
                    "amount": 11000,
                    "currency": "INR",
                    "status": "captured"
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    signature = generate_signature(body)
    
    response = client.post("/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": "evt_11",
        "Content-Type": "application/json"
    })
    assert response.status_code == 200
    
    # Verify no incident yet
    inc_resp = client.get("/api/incidents")
    assert len(inc_resp.json()) == 0
    
    # 2. Create merchant order later
    response2 = client.post("/api/merchant/orders", json={
        "razorpay_order_id": "order_11",
        "amount": 11000,
        "currency": "INR"
    })
    assert response2.status_code == 200
    
    # 3. Check incident is now created
    inc_resp2 = client.get("/api/incidents")
    incidents = inc_resp2.json()
    assert len(incidents) == 1
    assert incidents[0]["razorpay_order_id"] == "order_11"
    assert incidents[0]["incident_type"] == "PAYMENT_STATE_MISMATCH"

def test_payment_captured_then_repeated_merchant_order_idempotency():
    # 1. Trigger webhook first
    payload = {
        "event": "payment.captured",
        "created_at": 1234567890,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_12",
                    "order_id": "order_12",
                    "amount": 12000,
                    "currency": "INR",
                    "status": "captured"
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    signature = generate_signature(body)
    
    client.post("/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": "evt_12",
        "Content-Type": "application/json"
    })
    
    # 2. Create merchant order -> creates incident
    client.post("/api/merchant/orders", json={
        "razorpay_order_id": "order_12",
        "amount": 12000,
        "currency": "INR"
    })
    
    inc_resp1 = client.get("/api/incidents")
    assert len(inc_resp1.json()) == 1
    
    # 3. Repeat merchant order creation -> should fail 400 and not duplicate incident
    response3 = client.post("/api/merchant/orders", json={
        "razorpay_order_id": "order_12",
        "amount": 12000,
        "currency": "INR"
    })
    assert response3.status_code == 400
    
    inc_resp2 = client.get("/api/incidents")
    assert len(inc_resp2.json()) == 1

def test_sensitive_data_not_persisted():
    payload = {
        "event": "payment.captured",
        "created_at": 1234567890,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_13",
                    "order_id": "order_13",
                    "amount": 13000,
                    "currency": "INR",
                    "status": "captured",
                    "email": "customer@example.com",
                    "contact": "+919876543210",
                    "card": {
                        "last4": "1234",
                        "network": "Visa"
                    },
                    "vpa": "user@upi"
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    signature = generate_signature(body)
    
    response = client.post("/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": "evt_13",
        "Content-Type": "application/json"
    })
    assert response.status_code == 200
    
    # Connect to the test db and verify the payload was not stored
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM webhook_events WHERE event_id = 'evt_13'")
        row = cursor.fetchone()
        
        assert row is not None
        row_dict = dict(row)
        
        # Ensure payload is either None or does not contain PII
        if row_dict.get("payload"):
            assert "customer@example.com" not in row_dict["payload"]
            assert "+919876543210" not in row_dict["payload"]
            assert "1234" not in row_dict["payload"]
        
        # Verify the minimized fields were stored
        assert row_dict["razorpay_payment_id"] == "pay_13"
        assert row_dict["amount"] == 13000
        assert row_dict["currency"] == "INR"
        assert row_dict["payment_status"] == "captured"
