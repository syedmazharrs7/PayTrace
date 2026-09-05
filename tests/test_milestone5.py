import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, get_db
import sqlite3
import os
import json
import httpx
import hmac
import hashlib
from unittest.mock import patch, MagicMock
from app.services.investigator import get_ai_provider, GeminiProvider

client = TestClient(app)

# Helper to sign payloads
def sign_payload(payload: dict, secret: str = "test_secret") -> str:
    body = json.dumps(payload).encode('utf-8')
    return hmac.new(key=secret.encode('utf-8'), msg=body, digestmod=hashlib.sha256).hexdigest()

@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    os.environ["PAYTRACE_ENV"] = "test"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = "test_secret"
    # Use in-memory DB for tests
    os.environ["PAYTRACE_DB_PATH"] = ":memory:"
    # In order for :memory: to work across multiple get_db calls in a single test,
    # we'd normally use a file or shared cache. Let's use a temporary file instead.
    import tempfile
    fd, path = tempfile.mkstemp()
    os.environ["PAYTRACE_DB_PATH"] = path
    
    init_db()
    yield
    
    os.close(fd)
    os.remove(path)

# -------------------------------------------------------------------
# WEBHOOK TESTS
# -------------------------------------------------------------------
def test_webhook_missing_signature():
    response = client.post("/webhooks/razorpay", json={"event": "payment.captured"}, headers={"x-razorpay-event-id": "evt_1"})
    assert response.status_code == 400
    assert response.json() == {"detail": "Missing signature"}

def test_webhook_missing_event_id():
    payload = {"event": "payment.captured"}
    body = json.dumps(payload).encode('utf-8')
    headers = {
        "X-Razorpay-Signature": hmac.new(key=b"test_secret", msg=body, digestmod=hashlib.sha256).hexdigest()
    }
    response = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert response.status_code == 400
    assert response.json() == {"detail": "Missing event ID"}

def test_webhook_invalid_signature():
    payload = {"event": "payment.captured"}
    headers = {
        "x-razorpay-event-id": "evt_1",
        "X-Razorpay-Signature": "invalid_signature"
    }
    response = client.post("/webhooks/razorpay", json=payload, headers=headers)
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid signature"}

def test_webhook_malformed_json():
    # TestClient doesn't easily send malformed JSON when using json= kwarg, send bytes directly
    headers = {
        "x-razorpay-event-id": "evt_1",
        "X-Razorpay-Signature": "dummy" # It will fail signature check first unless we use a valid one
    }
    # Create valid signature for invalid JSON
    body = b"{"
    sig = hmac.new(key=b"test_secret", msg=body, digestmod=hashlib.sha256).hexdigest()
    headers["X-Razorpay-Signature"] = sig
    
    response = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid JSON"}

def test_webhook_valid_duplicate_delivery():
    payload = {
        "event": "payment.captured",
        "created_at": 123456,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_1",
                    "order_id": "order_1",
                    "amount": 100,
                    "currency": "INR",
                    "status": "captured"
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    headers = {
        "x-razorpay-event-id": "evt_duplicate",
        "X-Razorpay-Signature": hmac.new(key=b"test_secret", msg=body, digestmod=hashlib.sha256).hexdigest()
    }
    
    # First delivery
    r1 = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert r1.status_code == 200
    
    # Second delivery
    r2 = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert r2.status_code == 200 # Should be idempotent and return 200
    
    # Verify only one event was stored
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM webhook_events WHERE event_id = 'evt_duplicate'")
        assert cursor.fetchone()[0] == 1

def test_webhook_malformed_nested_payload():
    payload = {
        "event": "payment.captured",
        "created_at": 123456,
        "payload": {
            "payment": {
                # missing entity
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    headers = {
        "x-razorpay-event-id": "evt_malformed",
        "X-Razorpay-Signature": hmac.new(key=b"test_secret", msg=body, digestmod=hashlib.sha256).hexdigest()
    }
    response = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert response.status_code == 400
    assert response.json() == {"detail": "Malformed payment payload"}


# -------------------------------------------------------------------
# INCIDENT RESOLUTION TESTS
# -------------------------------------------------------------------
def test_resolve_incident():
    # Insert an incident
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO incidents (event_id, incident_type, status)
            VALUES ('evt_test_resolve', 'PAYMENT_STATE_MISMATCH', 'OPEN')
        """)
        incident_id = cursor.lastrowid
        conn.commit()
        
    response = client.post(f"/api/incidents/{incident_id}/resolve")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Verify DB state
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, resolved_at FROM incidents WHERE id = ?", (incident_id,))
        row = cursor.fetchone()
        assert row["status"] == "RESOLVED"
        assert row["resolved_at"] is not None
        
        # Verify Audit trail
        cursor.execute("SELECT * FROM audit_trail WHERE incident_id = ?", (incident_id,))
        audit = cursor.fetchone()
        assert audit is not None
        assert audit["action"] == "RESOLVE_INCIDENT"

def test_resolve_already_resolved_incident():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO incidents (event_id, incident_type, status)
            VALUES ('evt_test_resolve_2', 'PAYMENT_STATE_MISMATCH', 'RESOLVED')
        """)
        incident_id = cursor.lastrowid
        conn.commit()
        
    response = client.post(f"/api/incidents/{incident_id}/resolve")
    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot resolve incident with status: RESOLVED"

def test_resolve_missing_incident():
    response = client.post("/api/incidents/99999/resolve")
    assert response.status_code == 404
    assert response.json()["detail"] == "Incident not found."

def test_resolve_non_open_incident():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO incidents (event_id, incident_type, status)
            VALUES ('evt_test_resolve_3', 'PAYMENT_STATE_MISMATCH', 'INVESTIGATING')
        """)
        incident_id = cursor.lastrowid
        conn.commit()
        
    response = client.post(f"/api/incidents/{incident_id}/resolve")
    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot resolve incident with status: INVESTIGATING"


# -------------------------------------------------------------------
# AI PROVIDER FAILURE TESTS
# -------------------------------------------------------------------
class MockResponse:
    def __init__(self, status_code, json_data=None, text=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text or ""
        self.request = MagicMock()
        self.request.url = "http://mock-api.com"
        self.request.method = "POST"
        
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("Error", request=self.request, response=self)
            
    def json(self):
        if self._json is None:
            raise json.JSONDecodeError("Expecting value", "", 0)
        return self._json

def test_ai_provider_missing_key():
    provider = GeminiProvider()
    provider.api_key = None # Clear key
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        provider.analyze({})
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "AI provider is not configured."

@patch("httpx.Client.post")
def test_ai_provider_network_error(mock_post):
    mock_post.side_effect = httpx.RequestError("Network down")
    
    provider = GeminiProvider()
    provider.api_key = "dummy"
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        provider.analyze({})
    assert exc_info.value.status_code == 502
    assert "temporarily unreachable" in exc_info.value.detail

@patch("httpx.Client.post")
def test_ai_provider_timeout(mock_post):
    mock_post.side_effect = httpx.TimeoutException("Timeout")
    
    provider = GeminiProvider()
    provider.api_key = "dummy"
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        provider.analyze({})
    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.detail

@patch("httpx.Client.post")
def test_ai_provider_rate_limit(mock_post):
    mock_post.return_value = MockResponse(429)
    
    provider = GeminiProvider()
    provider.api_key = "dummy"
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        provider.analyze({})
    assert exc_info.value.status_code == 429
    assert "rate limited" in exc_info.value.detail

@patch("httpx.Client.post")
def test_ai_provider_malformed_json_response(mock_post):
    # Missing 'candidates'
    mock_post.return_value = MockResponse(200, {"wrong": "structure"})
    
    provider = GeminiProvider()
    provider.api_key = "dummy"
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        provider.analyze({})
    assert exc_info.value.status_code == 502
    assert "unexpected response structure" in exc_info.value.detail

@patch("httpx.Client.post")
def test_gemini_url_security(mock_post):
    mock_post.return_value = MockResponse(200, {
        "candidates": [{"content": {"parts": [{"text": '{"summary": "test", "what_happened": "t", "likely_cause": "t", "impact": "t", "recommended_action": "t", "action_type": "INVESTIGATE", "action_safety": "INFORMATIONAL", "confidence": "High", "uncertainty": "None"}'}]}}]
    })
    
    provider = GeminiProvider()
    provider.api_key = "secret_key_123"
    provider.model = "test-model"
    
    provider.analyze({"test": "data"})
    
    # Verify the URL does not contain the key
    call_args = mock_post.call_args
    url = call_args[0][0]
    headers = call_args[1].get("headers", {})
    
    assert "secret_key_123" not in url
    assert headers.get("x-goog-api-key") == "secret_key_123"

@patch("app.services.investigator.GeminiProvider.analyze")
def test_gemini_failure_atomicity(mock_analyze):
    # Setup test with actual Gemini provider instead of mock
    # Force failure
    from fastapi import HTTPException
    mock_analyze.side_effect = HTTPException(status_code=504, detail="Timeout")
    
    # Create incident
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO incidents (event_id, incident_type, status)
            VALUES ('evt_atomicity', 'PAYMENT_STATE_MISMATCH', 'OPEN')
        """)
        incident_id = cursor.lastrowid
        conn.commit()
        
    # Must explicitly override the Depends to use real GeminiProvider for this test
    app.dependency_overrides[get_ai_provider] = lambda: GeminiProvider()
    
    response = client.post(f"/api/incidents/{incident_id}/analysis")
    assert response.status_code == 504
    
    # Check that nothing was persisted
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM incident_analyses WHERE incident_id = ?", (incident_id,))
        assert cursor.fetchone()[0] == 0
        
        cursor.execute("SELECT COUNT(*) FROM audit_trail WHERE incident_id = ?", (incident_id,))
        assert cursor.fetchone()[0] == 0
        
    app.dependency_overrides.clear()


# -------------------------------------------------------------------
# END-TO-END INTEGRATION TEST
# -------------------------------------------------------------------
def test_end_to_end_mismatch_to_resolution():
    # 1. Create a merchant order (PENDING)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO merchant_orders (razorpay_order_id, amount, currency, status)
            VALUES ('order_e2e_1', 100, 'INR', 'PENDING')
        """)
        conn.commit()

    # 2. Simulate Webhook indicating CAPTURED
    payload = {
        "event": "payment.captured",
        "created_at": 123456,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_e2e_1",
                    "order_id": "order_e2e_1",
                    "amount": 100,
                    "currency": "INR",
                    "status": "captured"
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    headers = {
        "x-razorpay-event-id": "evt_e2e_1",
        "X-Razorpay-Signature": hmac.new(key=b"test_secret", msg=body, digestmod=hashlib.sha256).hexdigest()
    }
    webhook_res = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert webhook_res.status_code == 200
    
    # 3. Check Incident was created
    incidents_res = client.get("/api/incidents")
    incidents = incidents_res.json()
    e2e_incident = next((i for i in incidents if i["event_id"] == "evt_e2e_1"), None)
    assert e2e_incident is not None
    assert e2e_incident["status"] == "OPEN"
    incident_id = e2e_incident["id"]
    
    # 4. Generate Analysis (Uses MockAIProvider automatically in tests)
    analysis_res = client.post(f"/api/incidents/{incident_id}/analysis")
    assert analysis_res.status_code == 200
    analysis = analysis_res.json()
    assert analysis["incident_id"] == incident_id
    assert analysis["action_safety"] == "INFORMATIONAL" # Mock sets it to INVESTIGATE -> INFORMATIONAL
    
    # Verify Audit Trail for analysis
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_trail WHERE incident_id = ? AND action = ?", (incident_id, "Mock recommended action"))
        assert cursor.fetchone() is not None
        
    # 5. Resolve Incident
    resolve_res = client.post(f"/api/incidents/{incident_id}/resolve")
    assert resolve_res.status_code == 200
    
    # 6. Verify Final State
    final_incident = client.get(f"/api/incidents/{incident_id}").json()
    assert final_incident["status"] == "RESOLVED"
