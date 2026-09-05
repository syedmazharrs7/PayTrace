# PayTrace

PayTrace turns payment-state divergence into an actionable, auditable recovery workflow.

It is an **AI-Assisted Payment Operations & Revenue Protection system** built to handle the inevitable edge cases in distributed payment systems. PayTrace detects when payment-provider state and merchant state diverge, reconstructs what happened, and guides a human-controlled recovery.

## The Problem

In a typical e-commerce or SaaS flow, the payment provider (e.g., Razorpay) processes a payment and sends an asynchronous webhook to the merchant's backend. However, network partitions, server crashes, application bugs, or unhandled exceptions can cause the merchant's internal order state to diverge from the payment provider's state.

Consider this scenario:
* **Razorpay:** `PAYMENT = CAPTURED`
* **Merchant:** `ORDER = PENDING`

Ordinary webhook monitoring simply logs that an event was received. PayTrace actively compares the authoritative truth (the payment provider) against the local truth (the merchant database), detects the divergence, and provides a structured, bounded recovery workflow.

## The PayTrace Loop

PayTrace operates through a strict, deterministic workflow enhanced by AI for investigation:

1. **DETECT:** PayTrace ingests real Razorpay webhooks (e.g., `payment.captured`), securely verifies their HMAC-SHA256 signatures, and compares the reported payment status against the merchant's order state.
2. **UNDERSTAND:** If a mismatch is detected, PayTrace creates a `PAYMENT_STATE_MISMATCH` incident, reconstructing the chronological event lifecycle from the event ledger.
3. **RECOMMEND:** An AI model (Google Gemini) analyzes the timeline, identifies the likely root cause, assesses the impact, and recommends a specific recovery action.
4. **HUMAN APPROVAL:** *AI advises. The system verifies. Humans authorize.* Consequential state changes (like marking an order as PAID) require explicit human approval.
5. **RECONCILE:** Once approved, the merchant order state is updated through deterministic, pre-approved application logic.
6. **AUDIT:** Every detection, AI recommendation, and human authorization is persisted in a durable audit trail.

## Architecture

```text
       Razorpay (Test Mode)
       ├── REST API
       └── Webhooks
              ↓
      PayTrace Ingestion (FastAPI)
              ↓
         Event Ledger (SQLite)
              ↓
      Reconciliation Engine
              ↓
        Incident Detection
              ↓
        AI Investigation (Gemini)
              ↓
       Deterministic Safety
              ↓
    Human Approval (Operations Console)
              ↓
         Reconciliation
              ↓
         Audit Trail
              ↓
        Merchant State
```

## Where AI is Used (and Where it is Not)

**AI is used for:**
* Summarizing incidents into readable operational reports.
* Interpreting webhook timelines (e.g., failed → authorized → captured).
* Determining the likely cause of divergence.
* Recommending bounded recovery actions.

**Deterministic logic handles:**
* Webhook HMAC signature verification.
* Idempotency checks.
* Event persistence.
* State comparison and anomaly detection.
* Financial state transitions (reconciliation).
* Audit logging.

PayTrace intentionally **does not** use AI to execute autonomous financial transactions or directly mutate the database. AI acts purely as an investigative copilot.

## Security & Data Integrity

PayTrace enforces strict security boundaries:
* **Webhook Verification:** All webhooks are authenticated using `X-Razorpay-Signature` against a strict HMAC-SHA256 hash of the raw payload.
* **Idempotency:** Webhook ingestion is idempotent, driven by `x-razorpay-event-id` database constraints to prevent duplicate processing.
* **Safe Payload Handling:** To protect PII and reduce surface area, PayTrace extracts only necessary correlation IDs and metadata. Raw sensitive payloads are not blindly persisted.
* **Separation of Concerns:** The application cleanly separates the Razorpay public Key ID from the highly sensitive Secret Key.

## Real Razorpay Test Mode Demo

The application/demo uses genuine Razorpay Test Mode transactions and webhook events. Synthetic fixtures are restricted to the isolated automated test database.

### The Lifecycle
1. PayTrace creates a Razorpay Test Mode order via the REST API.
2. The user completes the payment via the standard Razorpay Checkout.
3. Razorpay delivers real webhooks (e.g., `payment.authorized`, `payment.captured`, `order.paid`).
4. PayTrace verifies, persists, and correlates these events.
5. If the merchant order state remains `PENDING` despite a `payment.captured` event, an incident is triggered.

*Note: PayTrace strictly uses Razorpay Test Mode. No Live Mode funds are processed.*

## Setup & Running Locally

### 1. Clone the repository
```bash
git clone https://github.com/syedmazharrs7/PayTrace.git
cd PayTrace
```

### 2. Create a Virtual Environment
**Windows PowerShell:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Requirements
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Create a `.env` file based on `.env.example`:
```
RAZORPAY_KEY_ID=rzp_test_...        # Public Key
RAZORPAY_KEY_SECRET=...             # Secret Key
RAZORPAY_WEBHOOK_SECRET=...         # Secret Webhook Signature Key
GEMINI_API_KEY=...                  # Secret API Key
PAYTRACE_DB_PATH=paytrace.db
```

### 5. Start the Server
```bash
python -m uvicorn app.main:app --reload
```
* **API URL:** `http://127.0.0.1:8000`
* **Operations Console:** `http://127.0.0.1:8000/console/`

## Webhook Local Testing

To receive real Razorpay webhooks locally, you must expose your local FastAPI server to the internet using a tool like `zrok2` or `ngrok`.

```bash
zrok2 share public http://localhost:8000
```
Configure your Razorpay Test Mode Webhook Settings to point to your public tunnel:
`https://<your-zrok-share>/webhooks/razorpay`

## Automated Testing

PayTrace uses a fully isolated test suite that utilizes an isolated test database (`test_paytrace.db`) to ensure the production/demo database is never polluted by synthetic fixtures.

Run the test suite:
```bash
python -m pytest tests/ -q
```
**Current Verified Result:**
`58 passed, 2 warnings in ~40.54s`

## API Documentation

Key endpoints in the PayTrace application:

* `GET /api/merchant/orders` - List all merchant orders.
* `POST /api/merchant/orders` - Create a real Razorpay Test Mode order.
* `GET /api/merchant/orders/{razorpay_order_id}/events` - View chronological webhook lifecycle for an order.
* `POST /webhooks/razorpay` - Secure ingestion endpoint for Razorpay webhooks.
* `GET /api/incidents` - List all detected payment-state mismatches.
* `POST /api/incidents/{id}/analysis` - Trigger/retrieve AI investigation for a specific incident.
* `POST /api/incidents/{id}/resolve` - Apply human-approved reconciliation (updates order to `PAID`).

## Engineering Lessons

Building a robust payment operations tool surfaced several critical realities:
1. **Amount Unit Representation:** Razorpay processes INR amounts in minor units (paise). A raw payload value of `50000` represents ₹500.00. The AI evidence layer required explicit major/minor formatting to prevent LLM hallucinations about large values.
2. **Test Database Pollution:** Early test iterations polluted the application DB due to import-time side effects locking the database path. This was successfully mitigated using global pytest environment overrides (`conftest.py`) to guarantee strict test isolation.
3. **Simulation Endpoints:** To preserve data integrity for the final product, all internal testing simulation endpoints (which mocked local orders) were systematically purged. The final application relies 100% on genuine webhook events.

## Limitations & Non-Goals

PayTrace is an engineering prototype designed for the Razorpay Buildathon. It intentionally **does not** implement:
* Unrestricted AI financial execution (AI cannot mutate state directly).
* Fabricated payment data or fake demo generators.
* Generic analytics or generic dashboarding.
* Live Mode transactions.

## Conclusion

PayTrace is built around a simple principle: **payment truth and merchant truth should not silently diverge.**

AI investigates. Deterministic controls protect financial state. Humans authorize consequential recovery.
