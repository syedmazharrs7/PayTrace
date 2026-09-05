from fastapi import APIRouter
from app.config import RAZORPAY_KEY_ID

router = APIRouter(
    prefix="/api/config",
    tags=["config"]
)

@router.get("")
async def get_config():
    """Provides public configuration to the frontend (e.g., Razorpay Key ID)."""
    return {"razorpay_key_id": RAZORPAY_KEY_ID}
