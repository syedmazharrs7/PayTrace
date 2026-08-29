import json
import os
import httpx
import logging
from datetime import datetime
from abc import ABC, abstractmethod
from fastapi import HTTPException
from pydantic import ValidationError
from app.schemas import AIOutput

logger = logging.getLogger(__name__)

class AIProvider(ABC):
    @abstractmethod
    def analyze(self, evidence: dict) -> AIOutput:
        pass

def pydantic_to_gemini_schema(schema: dict) -> dict:
    """Converts a Pydantic JSON schema to Gemini's expected Schema object format."""
    gemini_schema = {}
    
    t = schema.get("type", "").upper()
    if t:
        gemini_schema["type"] = t
        
    if "description" in schema:
        gemini_schema["description"] = schema["description"]
        
    if "enum" in schema:
        gemini_schema["enum"] = schema["enum"]
        
    if t == "OBJECT" and "properties" in schema:
        gemini_schema["properties"] = {
            k: pydantic_to_gemini_schema(v)
            for k, v in schema["properties"].items()
        }
        
    if t == "ARRAY" and "items" in schema:
        gemini_schema["items"] = pydantic_to_gemini_schema(schema["items"])
        
    if "required" in schema:
        gemini_schema["required"] = schema["required"]
        
    return gemini_schema

class GeminiProvider(AIProvider):
    def __init__(self):
        self.api_key = os.getenv("AI_API_KEY")
        self.model = os.getenv("AI_MODEL", "gemini-3.6-flash")

    def analyze(self, evidence: dict) -> AIOutput:
        if not self.api_key:
            raise HTTPException(status_code=503, detail="AI provider is not configured.")

        system_prompt = """
        You are PayTrace's incident intelligence investigator.
        Your job is to analyze the provided evidence of a payment state mismatch.
        You must distinguish between confirmed facts (e.g., webhook timestamps, order status) and inferences (e.g., potential causes).
        Do NOT invent missing events, customer information, or financial impact.
        Do NOT claim money was lost unless the evidence establishes that.
        Do NOT execute or simulate execution of financial actions.
        Do NOT treat an inference as a confirmed fact.
        You MUST return your response as a valid JSON object matching the provided JSON schema exactly.
        """
        
        schema = AIOutput.model_json_schema()
        gemini_schema = pydantic_to_gemini_schema(schema)

        payload = {
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [{
                "parts": [{"text": f"Evidence:\n{json.dumps(evidence, indent=2)}\n\nRespond strictly with a JSON object matching this schema:\n{json.dumps(schema, indent=2)}"}]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": gemini_schema
            }
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key}

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                try:
                    content = data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    logger.error("AI provider returned a response missing expected content structure.")
                    raise HTTPException(status_code=502, detail="AI analysis returned an unexpected response structure.")
                
                # Parse and validate with Pydantic
                parsed_json = json.loads(content)
                return AIOutput(**parsed_json)
                
        except httpx.TimeoutException:
            logger.error("AI provider request timed out.")
            raise HTTPException(status_code=504, detail="AI analysis service timed out. Please try again later.")
        except httpx.RequestError as exc:
            logger.error(f"AI provider network error: {type(exc).__name__}")
            raise HTTPException(status_code=502, detail="AI analysis service is temporarily unreachable.")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.error(f"AI provider returned HTTP {status}")
            
            if status == 429:
                raise HTTPException(status_code=429, detail="AI analysis service is rate limited. Please try again later.")
            elif status in [400, 401, 403, 404]:
                raise HTTPException(status_code=500, detail="AI analysis service is misconfigured or unavailable.")
            else:
                raise HTTPException(status_code=502, detail="AI analysis service is temporarily unavailable.")
                
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error(f"AI returned malformed or invalid JSON: {type(exc).__name__}")
            raise HTTPException(status_code=502, detail="AI analysis returned invalid structured data.")

class MockAIProvider(AIProvider):
    def analyze(self, evidence: dict) -> AIOutput:
        # Strictly for testing.
        return AIOutput(
            summary="Mock analysis summary",
            what_happened="Mock description of what happened",
            likely_cause="Mock likely cause",
            impact=evidence.get("deterministic_impact", "Mock impact"),
            recommended_action="Mock recommended action",
            action_type="INVESTIGATE",
            confidence="High",
            uncertainty="None"
        )

def get_ai_provider() -> AIProvider:
    if os.getenv("PAYTRACE_ENV") == "test":
        return MockAIProvider()
    return GeminiProvider()
