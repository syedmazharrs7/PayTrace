from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import hmac
import hashlib
import json
import logging
import sqlite3
from app import config
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"]
)

def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verifies the HMAC-SHA256 signature of the Razorpay webhook payload."""
    expected_signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)

@router.post("/razorpay")
async def razorpay_webhook(request: Request):
    """
    Ingest and process Razorpay webhooks.
    """
    # 1. Receive the raw HTTP request body.
    raw_body = await request.body()
    
    # 2 & 3. Read the headers.
    signature = request.headers.get("X-Razorpay-Signature")
    event_id = request.headers.get("x-razorpay-event-id")
    
    if not signature:
        logger.warning("Missing X-Razorpay-Signature header")
        return JSONResponse(status_code=400, content={"detail": "Missing signature"})
        
    if not event_id:
        logger.warning("Missing x-razorpay-event-id header")

    # 4 & 5. Verify the webhook signature.
    is_valid = verify_signature(raw_body, signature, config.RAZORPAY_WEBHOOK_SECRET)
    if not is_valid:
        logger.error("Invalid Razorpay webhook signature")
        return JSONResponse(status_code=400, content={"detail": "Invalid signature"})

    # 6. Parse the JSON only AFTER signature verification.
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload in webhook")
        return JSONResponse(status_code=400, content={"detail": "Invalid JSON"})

    # 7 & 8. Extract the top-level Razorpay event name and created_at.
    event_type = payload.get("event")
    created_at = payload.get("created_at")
    
    # 9. Extract relevant entity metadata (Data minimization).
    entity_id = None
    razorpay_order_id = None
    razorpay_payment_id = None
    amount = None
    currency = None
    payment_status = None
    
    try:
        if event_type and event_type.startswith("payment."):
            payment_entity = payload["payload"]["payment"]["entity"]
            entity_id = payment_entity.get("id")
            razorpay_payment_id = payment_entity.get("id")
            razorpay_order_id = payment_entity.get("order_id")
            amount = payment_entity.get("amount")
            currency = payment_entity.get("currency")
            payment_status = payment_entity.get("status")
        elif event_type and event_type.startswith("order."):
            order_entity = payload["payload"]["order"]["entity"]
            entity_id = order_entity.get("id")
            razorpay_order_id = order_entity.get("id")
    except KeyError:
        logger.warning(f"Could not extract entity ID from payload for event_type={event_type}")

    # 10. Store event in DB and check for duplicate delivery (PII is NOT persisted)
    if event_id:
        with get_db() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO webhook_events (
                        event_id, event_type, entity_id, razorpay_order_id,
                        razorpay_payment_id, amount, currency, payment_status, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_id, event_type, entity_id, razorpay_order_id,
                    razorpay_payment_id, amount, currency, payment_status, created_at
                ))
                conn.commit()
            except sqlite3.IntegrityError:
                logger.info(f"Webhook already processed event_id={event_id}. Skipping.")
                return JSONResponse(status_code=200, content={"status": "ok"})

    # 11. Log safe event metadata.
    logger.info(
        f"Webhook received | event_id={event_id} | event_type={event_type} | "
        f"signature_valid=true | entity_id={entity_id} | created_at={created_at}"
    )

    # 12. Correlate Payment State
    if event_type == "payment.captured":
        try:
            payment_data = payload["payload"]["payment"]["entity"]
            razorpay_payment_id = payment_data["id"]
            razorpay_order_id = payment_data["order_id"]
            amount = payment_data["amount"]
            currency = payment_data["currency"]
            razorpay_status = payment_data["status"]
            
            with get_db() as conn:
                cursor = conn.cursor()
                # Find merchant order
                cursor.execute("SELECT * FROM merchant_orders WHERE razorpay_order_id = ?", (razorpay_order_id,))
                order = cursor.fetchone()
                
                if order:
                    merchant_status = order["status"]
                    if merchant_status == "PENDING" and razorpay_status == "captured":
                        # We found a mismatch! Create incident
                        try:
                            cursor.execute("""
                                INSERT INTO incidents (
                                    event_id, razorpay_order_id, razorpay_payment_id, amount, currency,
                                    razorpay_status, merchant_status, incident_type
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PAYMENT_STATE_MISMATCH')
                            """, (event_id, razorpay_order_id, razorpay_payment_id, amount, currency, razorpay_status, merchant_status))
                            conn.commit()
                            logger.error(
                                f"PAYMENT STATE MISMATCH | event_id={event_id} | order_id={razorpay_order_id} | "
                                f"payment_id={razorpay_payment_id} | razorpay_status={razorpay_status} | "
                                f"merchant_status={merchant_status} | amount={amount}"
                            )
                        except sqlite3.IntegrityError:
                            # Incident already exists for this event_id
                            pass
        except KeyError as e:
            logger.warning(f"Malformed payment payload, missing key: {e}")

    # 13. Return HTTP 200 for valid events.
    return JSONResponse(status_code=200, content={"status": "ok"})
