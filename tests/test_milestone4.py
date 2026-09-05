import pytest
from unittest.mock import patch, AsyncMock
import os
import sqlite3
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, get_db
from app.services.evidence import build_evidence
from app.services.safety import enforce_safety
from app.schemas import AIOutput
from app.services.investigator import AIProvider, GeminiProvider
from pydantic import ValidationError

TEST_DB = "test_paytrace.db"
os.environ["PAYTRACE_DB_PATH"] = TEST_DB
os.environ["SKIP_DB_INIT"] = "true"
os.environ["PAYTRACE_ENV"] = "test" # Use MockAIProvider

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    
    # Pre-populate a fake incident and data for testing
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO merchant_orders (razorpay_order_id, amount, currency, status) VALUES ('order_test', 1000, 'INR', 'PENDING')")
        cursor.execute("INSERT INTO webhook_events (event_id, event_type, entity_id, razorpay_order_id, razorpay_payment_id, amount, currency, payment_status) VALUES ('evt_test', 'payment.captured', 'pay_test', 'order_test', 'pay_test', 1000, 'INR', 'captured')")
        cursor.execute("INSERT INTO incidents (event_id, razorpay_order_id, razorpay_payment_id, amount, currency, razorpay_status, merchant_status, incident_type) VALUES ('evt_test', 'order_test', 'pay_test', 1000, 'INR', 'captured', 'PENDING', 'PAYMENT_STATE_MISMATCH')")
        conn.commit()

    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_evidence_facts_and_no_pii():
    # 1. Evidence contains required facts.
    # 2. Evidence contains no PII.
    evidence = build_evidence(1)
    
    assert evidence["incident"]["razorpay_order_id"] == "order_test"
    assert evidence["incident"]["amount"] == 1000
    assert evidence["merchant_order"]["status"] == "PENDING"
    assert len(evidence["webhooks"]) == 1
    
    # Ensure no PII keys exist in the evidence
    for wh in evidence["webhooks"]:
        assert "email" not in wh
        assert "contact" not in wh
        assert "card" not in wh
        assert "payload" not in wh

def test_deterministic_impact():
    # 3. Deterministic impact calculation.
    evidence = build_evidence(1)
    impact = evidence["deterministic_impact"]
    assert "10.00 INR payment is captured" in impact
    assert "merchant order remains PENDING" in impact

def test_valid_mock_ai_provider():
    # 4. Valid MockAIProvider response.
    # POST /api/incidents/1/analysis uses MockAIProvider due to PAYTRACE_ENV=test
    response = client.post("/api/incidents/1/analysis")
    assert response.status_code == 200
    data = response.json()
    assert data["action_type"] == "INVESTIGATE"
    assert data["action_safety"] == "INFORMATIONAL"

def test_invalid_ai_output_rejected():
    # 5. Invalid AI output rejected by Pydantic.
    with pytest.raises(ValidationError):
        AIOutput(summary="foo") # Missing required fields

def test_safety_gate_mappings():
    # 6-12. Test all safety mappings
    incident = {"id": 1, "incident_type": "TEST"}
    evidence = {}
    
    def check_safety(action_type, expected_safety):
        ai_out = AIOutput(summary="", what_happened="", likely_cause="", impact="", recommended_action="", action_type=action_type, confidence="", uncertainty="")
        result = enforce_safety(ai_out, incident, evidence, "")
        assert result.action_safety == expected_safety
        
    check_safety("INVESTIGATE", "INFORMATIONAL")
    check_safety("RECONCILE", "REQUIRES_HUMAN_APPROVAL")
    check_safety("REFUND", "BLOCKED")
    check_safety("CAPTURE", "BLOCKED")
    check_safety("TRANSFER", "BLOCKED")
    check_safety("CANCEL", "REQUIRES_HUMAN_APPROVAL")
    check_safety("UNKNOWN", "BLOCKED")

def test_missing_incident():
    # 13. Missing incident -> 404
    response = client.post("/api/incidents/999/analysis")
    assert response.status_code == 404

def test_missing_production_ai_credentials():
    # 14. Missing production AI credentials -> graceful 503
    os.environ.pop("AI_API_KEY", None)
    provider = GeminiProvider()
    response = client.post("/api/incidents/1/analysis")
    # This uses MockAIProvider because of PAYTRACE_ENV, let's test the provider directly:
    with pytest.raises(Exception) as exc:
        provider.analyze({})
    assert exc.value.status_code == 503
    assert "not configured" in str(exc.value.detail)

def test_post_creates_exactly_one_analysis_and_idempotent():
    # 15. POST analysis creates exactly one analysis.
    # 16. Repeated POST does not create duplicates.
    resp1 = client.post("/api/incidents/1/analysis")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "evidence" not in data1
    assert "created_at" in data1
    assert "action_type" in data1
    
    resp2 = client.post("/api/incidents/1/analysis")
    assert resp2.status_code == 200
    assert data1["id"] == resp2.json()["id"]
    
    # Verify exactly one in DB
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM incident_analyses WHERE incident_id = 1")
        assert cursor.fetchone()["count"] == 1

def test_get_analysis_is_read_only():
    # 17. GET analysis is read-only.
    # First GET should be 404
    get_resp = client.get("/api/incidents/1/analysis")
    assert get_resp.status_code == 404
    
    # POST to create
    client.post("/api/incidents/1/analysis")
    
    # GET again should return it
    get_resp2 = client.get("/api/incidents/1/analysis")
    assert get_resp2.status_code == 200
    data2 = get_resp2.json()
    assert data2["incident_id"] == 1
    assert "evidence" not in data2
    assert "created_at" in data2

def test_database_exception_triggers_rollback():
    # Verify explicit rollback is called on exception
    with pytest.raises(RuntimeError):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO merchant_orders (razorpay_order_id, amount, currency, status) VALUES ('rollback_test', 500, 'INR', 'PENDING')")
            raise RuntimeError("Force rollback")
            
    # Verify it rolled back
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM merchant_orders WHERE razorpay_order_id = 'rollback_test'")
        assert cursor.fetchone() is None

from unittest.mock import patch, MagicMock

def test_gemini_provider_sends_structured_schema():
    # 6. Add/update a mocked provider test proving that the Gemini request contains the structured-output schema configuration.
    os.environ["AI_API_KEY"] = "fake_key"
    provider = GeminiProvider()
    
    evidence = {"test": "data"}
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '{"summary":"s", "what_happened":"w", "likely_cause":"l", "impact":"i", "recommended_action":"r", "action_type":"INVESTIGATE", "confidence":"c", "uncertainty":"u"}'
                }]
            }
        }]
    }
    
    with patch("httpx.Client.post", return_value=mock_response) as mock_post:
        result = provider.analyze(evidence)
        
        # Verify post was called
        assert mock_post.called
        args, kwargs = mock_post.call_args
        
        # Verify payload contains generationConfig with responseSchema
        payload = kwargs.get("json", {})
        gen_config = payload.get("generationConfig", {})
        
        assert gen_config.get("responseMimeType") == "application/json"
        
        schema = gen_config.get("responseSchema")
        assert schema is not None
        assert schema["type"] == "OBJECT"
        assert "properties" in schema
        assert "action_type" in schema["properties"]
        assert schema["properties"]["action_type"]["enum"] == ["INVESTIGATE", "RECONCILE", "REFUND", "CAPTURE", "TRANSFER", "CANCEL", "UNKNOWN"]

        # Ensure validation happened after mocked response
        assert result.action_type == "INVESTIGATE"
