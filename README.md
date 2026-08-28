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
