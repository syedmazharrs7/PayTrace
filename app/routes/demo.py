from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.database import get_db
import sqlite3

router = APIRouter(
    prefix="/api/demo",
    tags=["demo"]
)

class DemoMismatchRequest(BaseModel):
    razorpay_order_id: str
    amount: int
    currency: str

@router.post("/create-payment-mismatch")
async def create_payment_mismatch(request: DemoMismatchRequest):
    """
    SIMULATION ENDPOINT ONLY: Creates a local merchant order in PENDING state.
    This sets up the system so that when the real Razorpay 'payment.captured' webhook
    arrives for this order_id, it will trigger a PAYMENT_STATE_MISMATCH incident.
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO merchant_orders (razorpay_order_id, amount, currency, status)
                VALUES (?, ?, ?, 'PENDING')
            """, (request.razorpay_order_id, request.amount, request.currency))
            conn.commit()
            
            return {
                "message": "Merchant order created in PENDING state.",
                "instructions": f"Now trigger the real Razorpay webhook for order '{request.razorpay_order_id}' to observe the mismatch detection."
            }
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Merchant order already exists for this order_id.")
