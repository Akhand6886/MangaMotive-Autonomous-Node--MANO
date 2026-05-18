import httpx
import json
import logging
from typing import Type, TypeVar, Optional, Any
from pydantic import BaseModel, ValidationError
from config import settings

logger = logging.getLogger("OllamaService")

T = TypeVar("T", bound=BaseModel)

class OllamaService:
    """
    Service for interacting with the local Ollama LLM runtime.
    Optimized for small models (Gemma 4 E2B, Qwen2.5) on Raspberry Pi 5 8GB.
    Implements Pillar 4: Reflection & Self-Correction loop.
    """
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.default_model = settings.ollama_default_model
        self.timeout = settings.ollama_timeout_seconds

    async def generate_text(self, prompt: str, model: Optional[str] = None, system: Optional[str] = None) -> str:
        """Generates raw text completion from Ollama."""
        target_model = model or self.default_model
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False
        }
        if system:
            payload["system"] = system

        logger.info(f"[Ollama] Generating text completion with model: {target_model}")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
            except httpx.HTTPError as e:
                logger.error(f"[Ollama] HTTP Error during generation: {e}")
                raise RuntimeError(f"Ollama API Error: {e}")

    async def generate_structured(self, prompt: str, schema_class: Type[T], model: Optional[str] = None, max_retries: int = 3) -> T:
        """
        Generates structured JSON matching a Pydantic schema class.
        Implements an automatic Reflection & Self-Correction loop.
        """
        target_model = model or self.default_model
        url = f"{self.base_url}/api/generate"
        
        # Inject JSON schema instructions into prompt
        schema_json = schema_class.model_json_schema()
        full_prompt = (
            f"{prompt}\n\n"
            f"CRITICAL INSTRUCTION: You MUST respond ONLY with a valid JSON object matching this schema:\n"
            f"{json.dumps(schema_json, indent=2)}\n"
            f"Do not include any markdown formatting, backticks, or conversational text outside the JSON object."
        )

        payload = {
            "model": target_model,
            "prompt": full_prompt,
            "format": "json",
            "stream": False
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            attempt = 0
            last_error = ""

            while attempt < max_retries:
                attempt += 1
                logger.info(f"[Ollama] Structured generation attempt {attempt}/{max_retries} with model: {target_model}")
                
                try:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    raw_json = data.get("response", "").strip()

                    # Attempt Pydantic validation
                    parsed_obj = schema_class.model_validate_json(raw_json)
                    logger.info("[Ollama] Structured validation PASSED.")
                    return parsed_obj

                except ValidationError as ve:
                    logger.warning(f"[Ollama] Pydantic validation failed on attempt {attempt}: {ve}")
                    last_error = str(ve)
                    
                    # Reflection & Self-Correction Loop
                    correction_prompt = (
                        f"Your previous JSON output failed validation with the following error:\n"
                        f"{last_error}\n\n"
                        f"Here was your invalid JSON output:\n{raw_json}\n\n"
                        f"Please correct the JSON structure to fully comply with the schema and return ONLY the corrected JSON object."
                    )
                    payload["prompt"] = correction_prompt

                except (httpx.HTTPError, json.JSONDecodeError) as e:
                    logger.warning(f"[Ollama] API/Decode error on attempt {attempt}: {e}")
                    last_error = str(e)

            logger.error(f"[Ollama] Failed to generate valid structured output after {max_retries} attempts.")
            raise RuntimeError(f"Ollama structured generation failed: {last_error}")

ollama_service = OllamaService()
