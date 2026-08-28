# PayTrace

## Current milestone
Razorpay Test Mode API connectivity and payment/order retrieval.

## Setup
```bash
python -m venv venv
```
Windows activation:
```powershell
.\venv\Scripts\activate
```

Install:
```bash
pip install -r requirements.txt
```

Copy:
`.env.example` -> `.env`
Then enter Razorpay Test Mode credentials manually.

Run:
```bash
uvicorn app.main:app --reload
```

Open:
`http://localhost:8000/docs`

## Webhook setup
PayTrace runs locally on port 8000. Razorpay cannot directly reach localhost, so a public HTTPS tunnel is required.
We use `zrok` for local testing.

1. Start PayTrace locally.
2. Start the tunnel: `zrok share public localhost:8000`
3. Configure Razorpay Test Mode webhook URL to: `https://<zrok-public-url>/webhooks/razorpay`
4. The webhook secret must be configured in both `.env` and Razorpay Dashboard. **Note:** The webhook secret is NOT the Razorpay API secret.

Webhook endpoint:
`POST /webhooks/razorpay`

## Security
The `.env` file is intentionally excluded from Git in the `.gitignore` file to ensure credentials are never committed.

## Payment-State Correlation (Milestone 3)
PayTrace features bidirectional correlation to accurately detect PAYMENT_STATE_MISMATCH incidents regardless of event arrival order:
1. **Webhook First (Late Merchant Order):** Razorpay sends `payment.captured` first. The webhook is verified, idempotently stored, and processed. Later, when the merchant creates the order in PayTrace as `PENDING`, PayTrace retroactively discovers the prior webhook and triggers an incident.
2. **Merchant Order First (Standard Flow):** The merchant creates the order as `PENDING`. Later, the `payment.captured` webhook arrives. PayTrace immediately correlates the webhook against the existing PENDING order and triggers an incident.

### Why event arrival order doesn't matter
In distributed systems with asynchronous webhooks, network delays or retries can cause webhooks to arrive before the local database commits the initial order. Bidirectional correlation ensures we never miss a mismatch simply because Razorpay was faster than the merchant's application infrastructure. Idempotency guarantees (`UNIQUE(event_id, incident_type)`) ensure duplicate webhooks or repeated updates do not spawn false duplicate incidents.

## Incident Intelligence (Milestone 4)
PayTrace features an advanced incident intelligence layer that uses AI to analyze mismatches while maintaining strict deterministic safety boundaries.

### Facts vs Inferences
The system enforces a strict distinction:
- **Facts:** Razorpay order ID, payment statuses, webhook IDs, timestamps, and deterministic calculated impact.
- **Inferences:** AI-generated summary, likely cause, what happened, and recommended action.

### Evidence Builder
Before AI analysis, PayTrace constructs a deterministic, sanitized evidence package. 
**Data Minimization:** It explicitly strips out all customer PII, contact info, email addresses, and raw webhook payloads. The AI only sees the minimum structured facts required to understand the state mismatch.

### Deterministic Impact Calculation
The AI does NOT decide how much money was lost. PayTrace application logic calculates the financial impact (e.g., amount at risk) based purely on verified database records.

### Structured Action Types & Deterministic Safety Engine
The AI classifies its recommendation into a structured `action_type` (e.g., `INVESTIGATE`, `RECONCILE`, `REFUND`). 
Crucially, **AI recommendation ≠ authorization**. 
A deterministic Safety Engine maps these types to rigid boundaries:
- `INVESTIGATE` → `INFORMATIONAL`
- `RECONCILE` / `CANCEL` → `REQUIRES_HUMAN_APPROVAL`
- `REFUND` / `CAPTURE` / `TRANSFER` / `UNKNOWN` → `BLOCKED`

### Audit Trail
Every analysis automatically generates an immutable audit trail record indicating the AI's recommendation and the Safety Engine's final classification.

### API Usage
Generate or retrieve an analysis for an incident:
- `POST /api/incidents/{incident_id}/analysis`: Idempotently builds evidence, calls the AI provider, runs the safety engine, stores the result, and returns it.
- `GET /api/incidents/{incident_id}/analysis`: Retrieves the existing analysis (read-only). Returns 404 if not found.

### AI Provider Configuration
The provider is configurable via environment variables in `.env`:
```env
# Optional: Set testing mode to bypass AI completely (uses MockProvider)
PAYTRACE_ENV=development 

# For production, supply your AI credentials (Gemini is the default provider):
AI_API_KEY=your_gemini_api_key_here
AI_MODEL=gemini-3.6-flash
```
If credentials are missing in production, the system fails gracefully with a 503 error and refuses to fabricate analysis.

### Running Tests
To run the complete 22-test suite covering both bidirectional correlation (M3) and incident intelligence (M4):
```bash
python -m pytest
```
