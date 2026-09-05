import httpx
import logging
from typing import Optional, Dict, Any
from app import config

logger = logging.getLogger(__name__)

class RazorpayAPIError(Exception):
    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict[Any, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}

class RazorpayClient:
    BASE_URL = "https://api.razorpay.com/v1"
    
    def __init__(self):
        self.auth = (config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET)
        # Timeout of 10 seconds should be reasonable for API calls
        self.timeout = httpx.Timeout(10.0)
        
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        
        # Log safe details
        logger.info(f"Razorpay API Request: {method} {endpoint}")
        
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                response = await client.request(method, url, **kwargs)
                
                # Check for HTTP errors
                if response.status_code >= 400:
                    try:
                        error_data = response.json()
                    except ValueError:
                        error_data = {"raw_text": response.text}
                        
                    logger.error(f"Razorpay API Error: {method} {endpoint} - Status {response.status_code}")
                    raise RazorpayAPIError(
                        message="Razorpay API request failed",
                        status_code=response.status_code,
                        details=error_data
                    )
                
                return response.json()
                
        except httpx.RequestError as e:
            logger.error(f"Razorpay connection error: {str(e)}")
            raise RazorpayAPIError(
                message="Connection to Razorpay failed",
                status_code=503,
                details={"error": str(e)}
            )

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Fetch a specific order from Razorpay"""
        return await self._make_request("GET", f"/orders/{order_id}")
        
    async def get_order_payments(self, order_id: str) -> Dict[str, Any]:
        """Fetch payments associated with an order"""
        return await self._make_request("GET", f"/orders/{order_id}/payments")
        
    async def get_payment(self, payment_id: str) -> Dict[str, Any]:
        """Fetch a specific payment from Razorpay"""
        return await self._make_request("GET", f"/payments/{payment_id}")

    async def create_order(self, amount: int, currency: str, receipt: str) -> Dict[str, Any]:
        """Create a new order in Razorpay"""
        return await self._make_request("POST", "/orders", json={
            "amount": amount,
            "currency": currency,
            "receipt": receipt
        })

razorpay_client = RazorpayClient()
