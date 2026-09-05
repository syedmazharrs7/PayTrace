from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.database import get_db
import sqlite3
import logging
import uuid
from app.razorpay_client import razorpay_client, RazorpayAPIError

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/merchant/orders",
    tags=["merchant"]
)

class OrderCreate(BaseModel):
    amount: int
    currency: str

class OrderStatusUpdate(BaseModel):
    status: str

@router.post("")
async def create_merchant_order(order: OrderCreate):
    """Creates a local merchant order representing merchant state."""
    # Create unique receipt
    receipt = f"rcpt_{uuid.uuid4().hex[:12]}"
    
    # Call Razorpay
    try:
        rzp_order = await razorpay_client.create_order(
            amount=order.amount,
            currency=order.currency,
            receipt=receipt
        )
        razorpay_order_id = rzp_order["id"]
    except RazorpayAPIError as e:
        logger.error(f"Razorpay API Error creating order: {e.message}")
        raise HTTPException(status_code=502, detail=f"Failed to create order with payment gateway: {e.message}")
    except Exception as e:
        logger.error(f"Unexpected error calling Razorpay: {str(e)}")
        raise HTTPException(status_code=502, detail="Payment gateway temporarily unavailable")

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO merchant_orders (razorpay_order_id, amount, currency, status)
                VALUES (?, ?, ?, 'PENDING')
            """, (razorpay_order_id, order.amount, order.currency))
            conn.commit()
            order_id = cursor.lastrowid
            
            # Fetch and return the created record
            cursor.execute("SELECT * FROM merchant_orders WHERE id = ?", (order_id,))
            created_order = dict(cursor.fetchone())
            
            # --- Bidirectional Correlation ---
            cursor.execute("""
                SELECT * FROM webhook_events 
                WHERE razorpay_order_id = ? AND event_type = 'payment.captured'
            """, (razorpay_order_id,))
            webhook_event = cursor.fetchone()
            
            if webhook_event:
                event_dict = dict(webhook_event)
                razorpay_payment_id = event_dict.get("razorpay_payment_id")
                amount = event_dict.get("amount")
                currency = event_dict.get("currency")
                razorpay_status = event_dict.get("payment_status")
                
                # Fallback to payload for older records before migration
                if not razorpay_payment_id and event_dict.get("payload"):
                    import json
                    try:
                        payload_data = json.loads(event_dict["payload"])
                        payment_data = payload_data["payload"]["payment"]["entity"]
                        razorpay_payment_id = payment_data.get("id")
                        razorpay_status = payment_data.get("status")
                        amount = payment_data.get("amount")
                        currency = payment_data.get("currency")
                    except (KeyError, json.JSONDecodeError) as e:
                        logger.warning(f"Malformed legacy payload during retroactive correlation, error: {e}")

                if razorpay_payment_id and created_order["status"] == "PENDING" and razorpay_status == "captured":
                    try:
                        cursor.execute("""
                            INSERT INTO incidents (
                                event_id, razorpay_order_id, razorpay_payment_id, amount, currency,
                                razorpay_status, merchant_status, incident_type
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PAYMENT_STATE_MISMATCH')
                        """, (
                            event_dict["event_id"], 
                            razorpay_order_id, 
                            razorpay_payment_id, 
                            amount, 
                            currency, 
                            razorpay_status, 
                            created_order["status"]
                        ))
                        conn.commit()
                        logger.error(
                            f"PAYMENT STATE MISMATCH (Late Merchant Order) | event_id={event_dict['event_id']} | "
                            f"order_id={razorpay_order_id} | payment_id={razorpay_payment_id} | "
                            f"razorpay_status={razorpay_status} | merchant_status={created_order['status']} | "
                            f"amount={amount}"
                        )
                    except sqlite3.IntegrityError:
                        # Incident already exists
                        pass
            
            return created_order
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Order with this razorpay_order_id already exists")
    except Exception as e:
        logger.error(f"Error creating merchant order: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("")
async def list_merchant_orders():
    """Retrieves all local merchant orders."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM merchant_orders ORDER BY created_at DESC")
        orders = [dict(row) for row in cursor.fetchall()]
        return orders

@router.get("/{razorpay_order_id}")
async def get_merchant_order(razorpay_order_id: str):
    """Retrieves the local merchant order state."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM merchant_orders WHERE razorpay_order_id = ?", (razorpay_order_id,))
        order = cursor.fetchone()
        
        if not order:
            raise HTTPException(status_code=404, detail="Merchant order not found")
            
        return dict(order)

@router.get("/{razorpay_order_id}/events")
async def get_merchant_order_events(razorpay_order_id: str):
    """Retrieves chronological webhook events for a specific order."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Per operational visibility requirements, order by received_at ASC
        cursor.execute("""
            SELECT * FROM webhook_events 
            WHERE razorpay_order_id = ? 
            ORDER BY received_at ASC
        """, (razorpay_order_id,))
        events = [dict(row) for row in cursor.fetchall()]
        return events


