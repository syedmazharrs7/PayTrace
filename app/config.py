import os
import sys
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load .env file
load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

def validate_config():
    missing = []
    if not RAZORPAY_KEY_ID:
        missing.append("RAZORPAY_KEY_ID")
    if not RAZORPAY_KEY_SECRET:
        missing.append("RAZORPAY_KEY_SECRET")
    if not RAZORPAY_WEBHOOK_SECRET:
        missing.append("RAZORPAY_WEBHOOK_SECRET")
        
    if missing:
        error_msg = f"Missing required configuration variables: {', '.join(missing)}"
        logger.error(error_msg)
        sys.exit(1)
        
    # We don't log the secret itself, just confirm it's loaded
    logger.info("Razorpay configuration validated successfully.")

