from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.razorpay_client import razorpay_client, RazorpayAPIError
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/razorpay",
    tags=["razorpay"]
)

@router.get("/orders/{order_id}")
async def get_order(order_id: str):
    """
    Retrieve a Razorpay Order by its ID.
    """
    try:
        return await razorpay_client.get_order(order_id)
    except RazorpayAPIError as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "error": e.message,
                "status_code": e.status_code,
                "details": e.details
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving order {order_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "An unexpected error occurred",
                "status_code": 500
            }
        )

@router.get("/orders/{order_id}/payments")
async def get_order_payments(order_id: str):
    """
    Retrieve payments for a Razorpay Order by its ID.
    """
    try:
        return await razorpay_client.get_order_payments(order_id)
    except RazorpayAPIError as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "error": e.message,
                "status_code": e.status_code,
                "details": e.details
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving payments for order {order_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "An unexpected error occurred",
                "status_code": 500
            }
        )

@router.get("/payments/{payment_id}")
async def get_payment(payment_id: str):
    """
    Retrieve a Razorpay Payment by its ID.
    """
    try:
        return await razorpay_client.get_payment(payment_id)
    except RazorpayAPIError as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "error": e.message,
                "status_code": e.status_code,
                "details": e.details
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving payment {payment_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "An unexpected error occurred",
                "status_code": 500
            }
        )
