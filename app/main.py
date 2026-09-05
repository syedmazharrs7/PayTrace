from fastapi import FastAPI
import logging
from app import config
from app.routes import razorpay, webhooks, merchant, incidents

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

from fastapi.staticfiles import StaticFiles
import os
from app.routes import razorpay, webhooks, merchant, incidents, config as config_route

# Create frontend directory if it doesn't exist to prevent startup errors
os.makedirs("frontend", exist_ok=True)

# Mount frontend Operations Console
app.mount("/console", StaticFiles(directory="frontend", html=True), name="console")

# Include routes
app.include_router(razorpay.router)
app.include_router(webhooks.router)
app.include_router(merchant.router)
app.include_router(incidents.router)
app.include_router(config_route.router)

@app.get("/")
async def health_check():
    """Health check endpoint"""
    return {
        "service": "PayTrace",
        "status": "running"
    }
