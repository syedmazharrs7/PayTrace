from fastapi import FastAPI
import logging
from app import config
from app.routes import razorpay, webhooks, merchant, incidents, demo

# Configure logging securely
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validate credentials at startup
config.validate_config()

# Initialize DB
from app.database import init_db
init_db()

app = FastAPI(
    title="PayTrace API",
    description="Backend Milestone 5: Production-Grade Incident Intelligence",
    version="1.5.0"
)

# Include routes
app.include_router(razorpay.router)
app.include_router(webhooks.router)
app.include_router(merchant.router)
app.include_router(incidents.router)
app.include_router(demo.router)

@app.get("/")
async def health_check():
    """Health check endpoint"""
    return {
        "service": "PayTrace",
        "status": "running"
    }
