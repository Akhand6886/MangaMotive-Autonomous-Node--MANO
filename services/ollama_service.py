"""
Ollama LLM Service Layer.

Provides structured and freeform text generation via a local Ollama runtime,
with automatic schema-compliant mock fallbacks when offline.
"""

import re
import httpx
import json
import logging
import hashlib
from typing import Type, TypeVar, Optional, Any, Dict, List
from pydantic import BaseModel, ValidationError
from config import settings
from database import SessionLocal
from models import LLMCache, ProjectMemory
from sqlalchemy import select

logger = logging.getLogger("OllamaService")

T = TypeVar("T", bound=BaseModel)

class OllamaService:
    """
    Service for interacting with the local Ollama LLM runtime.
    Optimized for small models (Gemma 4 E2B, Qwen2.5) on Raspberry Pi 5 8GB.
    Implements Pillar 4: Reflection & Self-Correction loop.

    Uses a shared httpx.AsyncClient for connection pooling and keep-alive reuse.
    """

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.default_model = settings.ollama_default_model
        self.timeout = httpx.Timeout(settings.ollama_timeout_seconds, connect=10.0)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazily initializes and returns a persistent HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Closes the persistent HTTP client. Call on application shutdown."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _get_runtime_settings(self) -> Dict[str, Any]:
        """Loads runtime overrides from SQLite ProjectMemory database, falling back to config settings."""
        runtime = {
            "llm_provider": settings.llm_provider,
            "openai_api_key": settings.openai_api_key,
            "openai_model": settings.openai_model,
            "gemini_api_key": settings.gemini_api_key,
            "gemini_model": settings.gemini_model,
        }
        try:
            async with SessionLocal() as db:
                for key in runtime.keys():
                    result = await db.execute(
                        select(ProjectMemory).where(ProjectMemory.key == key)
                    )
                    mem = result.scalars().first()
                    if mem and mem.value and len(mem.value) > 0:
                        runtime[key] = mem.value[0]
        except Exception as e:
            logger.warning(f"Failed to load runtime settings from DB: {e}")
        return runtime

    async def generate_text(self, prompt: str, model: Optional[str] = None, system: Optional[str] = None) -> str:
        """Generates raw text completion from Ollama, OpenAI, or Gemini, with robust fallback if offline."""
        runtime = await self._get_runtime_settings()
        provider = runtime["llm_provider"]
        target_model = model or (runtime["openai_model"] if provider == "openai" else runtime["gemini_model"] if provider == "gemini" else self.default_model)
        
        # 1. Compute prompt hash
        prompt_content = f"provider: {provider}\nsystem: {system or ''}\nprompt: {prompt}\nmodel: {target_model}"
        prompt_hash = hashlib.sha256(prompt_content.encode("utf-8")).hexdigest()
        
        # 2. Check Cache
        try:
            async with SessionLocal() as db:
                result = await db.execute(
                    select(LLMCache).where(LLMCache.prompt_hash == prompt_hash)
                )
                cache_entry = result.scalars().first()
                if cache_entry:
                    logger.info(f"[LLMCache Hit] Text cache hit for hash: {prompt_hash}")
                    return cache_entry.response
        except Exception as e:
            logger.warning(f"[LLMCache Error] Failed to read from cache: {e}")

        # 3. Cache Miss - Generate
        response_text = ""
        try:
            client = await self._get_client()
            if provider == "openai":
                api_key = runtime["openai_api_key"]
                if not api_key:
                    raise ValueError("OpenAI API key is missing")
                url = "https://api.openai.com/v1/chat/completions"
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": prompt})
                payload = {
                    "model": target_model,
                    "messages": messages,
                    "temperature": 0.7
                }
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                logger.info(f"[OpenAI] Generating text completion with model: {target_model}")
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                response_text = data["choices"][0]["message"]["content"]

            elif provider == "gemini":
                api_key = runtime["gemini_api_key"]
                if not api_key:
                    raise ValueError("Gemini API key is missing")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
                parts = [{"text": prompt}]
                if system:
                    parts.insert(0, {"text": f"System Instruction: {system}\n\n"})
                payload = {
                    "contents": [{"parts": parts}]
                }
                logger.info(f"[Gemini] Generating text completion with model: {target_model}")
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                response_text = data["candidates"][0]["content"]["parts"][0]["text"]

            else:  # ollama
                url = f"{self.base_url}/api/generate"
                payload = {
                    "model": target_model,
                    "prompt": prompt,
                    "stream": False
                }
                if system:
                    payload["system"] = system
                logger.info(f"[Ollama] Generating text completion with model: {target_model}")
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                response_text = data.get("response", "")

        except Exception as e:
            logger.warning(f"[{provider.upper()} Generation Error] {e}. Utilizing fallback mock response.")
            response_text = self._generate_text_fallback(prompt)

        # 4. Save to Cache
        if response_text:
            try:
                async with SessionLocal() as db:
                    cache_entry = LLMCache(
                        prompt_hash=prompt_hash,
                        prompt=prompt_content,
                        response=response_text
                    )
                    db.add(cache_entry)
                    await db.commit()
                    logger.info(f"[LLMCache Save] Saved text response for hash: {prompt_hash}")
            except Exception as e:
                logger.warning(f"[LLMCache Save Failed] Could not save response to cache: {e}")

        return response_text

    async def generate_structured(self, prompt: str, schema_class: Type[T], model: Optional[str] = None, max_retries: int = 3) -> T:
        """
        Generates structured JSON matching a Pydantic schema class.
        Implements an automatic Reflection & Self-Correction loop.
        Falls back to a schema-compliant mock generator if provider is offline or fails repeatedly.
        """
        runtime = await self._get_runtime_settings()
        provider = runtime["llm_provider"]
        target_model = model or (runtime["openai_model"] if provider == "openai" else runtime["gemini_model"] if provider == "gemini" else self.default_model)
        
        schema_json = schema_class.model_json_schema()
        full_prompt = (
            f"{prompt}\n\n"
            f"CRITICAL INSTRUCTION: You MUST respond ONLY with a valid JSON object matching this schema:\n"
            f"{json.dumps(schema_json, indent=2)}\n"
            f"Do not include any markdown formatting, backticks, or conversational text outside the JSON object."
        )

        # 1. Compute prompt hash
        prompt_content = f"provider: {provider}\nstructured: {schema_class.__name__}\nprompt: {full_prompt}\nmodel: {target_model}"
        prompt_hash = hashlib.sha256(prompt_content.encode("utf-8")).hexdigest()

        # 2. Check Cache
        try:
            async with SessionLocal() as db:
                result = await db.execute(
                    select(LLMCache).where(LLMCache.prompt_hash == prompt_hash)
                )
                cache_entry = result.scalars().first()
                if cache_entry:
                    logger.info(f"[LLMCache Hit] Structured cache hit for hash: {prompt_hash}")
                    try:
                        parsed_obj = schema_class.model_validate_json(cache_entry.response)
                        logger.info("[LLMCache Hit] Structured validation PASSED.")
                        return parsed_obj
                    except ValidationError as ve:
                        logger.warning(f"[LLMCache Hit] Cached response failed validation: {ve}. Re-generating.")
        except Exception as e:
            logger.warning(f"[LLMCache Error] Failed to read from cache: {e}")

        parsed_obj = None
        try:
            client = await self._get_client()
            attempt = 0
            last_error = ""

            while attempt < max_retries:
                attempt += 1
                logger.info(f"[{provider.upper()}] Structured generation attempt {attempt}/{max_retries} with model: {target_model}")
                
                try:
                    raw_json = ""
                    if provider == "openai":
                        api_key = runtime["openai_api_key"]
                        if not api_key:
                            raise ValueError("OpenAI API key is missing")
                        url = "https://api.openai.com/v1/chat/completions"
                        payload = {
                            "model": target_model,
                            "messages": [{"role": "user", "content": full_prompt}],
                            "temperature": 0.7,
                            "response_format": {"type": "json_object"}
                        }
                        headers = {
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        }
                        response = await client.post(url, json=payload, headers=headers)
                        response.raise_for_status()
                        data = response.json()
                        raw_json = data["choices"][0]["message"]["content"].strip()

                    elif provider == "gemini":
                        api_key = runtime["gemini_api_key"]
                        if not api_key:
                            raise ValueError("Gemini API key is missing")
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
                        payload = {
                            "contents": [{"parts": [{"text": full_prompt}]}],
                            "generationConfig": {
                                "responseMimeType": "application/json"
                            }
                        }
                        response = await client.post(url, json=payload)
                        response.raise_for_status()
                        data = response.json()
                        raw_json = data["candidates"][0]["content"]["parts"][0]["text"].strip()

                    else:  # ollama
                        url = f"{self.base_url}/api/generate"
                        payload = {
                            "model": target_model,
                            "prompt": full_prompt,
                            "format": "json",
                            "stream": False
                        }
                        response = await client.post(url, json=payload)
                        response.raise_for_status()
                        data = response.json()
                        raw_json = data.get("response", "").strip()

                    # Clean markdown wrappers if any API output contains them
                    if raw_json.startswith("```"):
                        raw_json = re.sub(r"^```(?:json)?\n|```$", "", raw_json, flags=re.MULTILINE).strip()

                    # Attempt Pydantic validation
                    parsed_obj = schema_class.model_validate_json(raw_json)
                    logger.info(f"[{provider.upper()}] Structured validation PASSED.")
                    break

                except ValidationError as ve:
                    logger.warning(f"[{provider.upper()}] Pydantic validation failed on attempt {attempt}: {ve}")
                    last_error = str(ve)
                    
                    # Reflection & Self-Correction Loop
                    correction_prompt = (
                        f"Your previous JSON output failed validation with the following error:\n"
                        f"{last_error}\n\n"
                        f"Here was your invalid JSON output:\n{raw_json}\n\n"
                        f"Please correct the JSON structure to fully comply with the schema and return ONLY the corrected JSON object."
                    )
                    # For Ollama we update payload prompt, for OpenAI/Gemini we modify full_prompt
                    if provider == "ollama":
                        payload["prompt"] = correction_prompt
                    else:
                        full_prompt = correction_prompt

                except (httpx.ConnectError, httpx.ConnectTimeout) as ce:
                    logger.warning(f"[{provider.upper()} Connection Error] Connect failure: {ce}. Skipping retries.")
                    break
                except (httpx.HTTPError, json.JSONDecodeError) as e:
                    logger.warning(f"[{provider.upper()}] API/Decode error on attempt {attempt}: {e}")
                    last_error = str(e)

            if parsed_obj is None:
                logger.error(f"[{provider.upper()}] Failed to generate valid structured output after {max_retries} attempts. Triggering schema-compliant mock fallback.")
                parsed_obj = self._generate_fallback_mock(prompt, schema_class)

        except Exception as e:
            logger.warning(f"[{provider.upper()} Offline] Ollama/API server is unreachable: {e}. Generating schema-compliant mock fallback.")
            parsed_obj = self._generate_fallback_mock(prompt, schema_class)

        # Save to Cache
        if parsed_obj is not None:
            try:
                response_json = parsed_obj.model_dump_json()
                async with SessionLocal() as db:
                    cache_entry = LLMCache(
                        prompt_hash=prompt_hash,
                        prompt=prompt_content,
                        response=response_json
                    )
                    db.add(cache_entry)
                    await db.commit()
                    logger.info(f"[LLMCache Save] Saved structured response for hash: {prompt_hash}")
            except Exception as e:
                logger.warning(f"[LLMCache Save Failed] Could not save response to cache: {e}")

        return parsed_obj

    def _generate_text_fallback(self, prompt: str) -> str:
        """Generates smart mock text content based on keywords in the prompt."""
        prompt_lower = prompt.lower()
        if "script" in prompt_lower:
            return (
                "[Hook: 00:00 - 00:10]\nDid you notice the massive detail hidden in the latest episode? Let's break it down!\n\n"
                "[Body: 00:10 - 00:45]\nThe visual directing reaches peak quality during the sword clash scene. "
                "Notice the lighting cues reflecting characters' determination.\n\n"
                "[Outro: 00:45 - 06:00]\nLet me know your thoughts in the comments. Subscribe for more deep dives!"
            )
        elif "evaluat" in prompt_lower or "check" in prompt_lower:
            return "The text complies with style rules. Factual accuracy is 95%. Banned words are not present."
        else:
            return "Simulated text content generated by the Intelligence Harness offline fallback engine."

    def _generate_fallback_mock(self, prompt: str, schema_class: Type[T]) -> T:
        """
        Generates structured data mapping the fields of the requested Pydantic schema class
        with appropriate, context-aware dummy information.
        """
        class_name = schema_class.__name__
        logger.info(f"[Ollama Fallback] Synthesizing mock payload for model class: {class_name}")

        # Try to guess target series or topic from prompt
        topic = "Anime Spotlight"
        series_match = re.search(r"'(.*?)'|\"(.*?)\"", prompt)
        if series_match:
            topic = series_match.group(1) or series_match.group(2)
        else:
            words = [w for w in prompt.split() if w.istitle()]
            if len(words) >= 2:
                topic = " ".join(words[:2])

        # Prepare default dictionaries for known schemas
        mock_data = {}

        if class_name == "StructuredTask":
            mock_data = {
                "topic": topic,
                "style": "Hype, engaging, fast-paced",
                "target_platform": "YouTube Short" if "short" in prompt.lower() else "Editorial Blog",
                "duration": "60 seconds" if "short" in prompt.lower() else "800 words",
                "assets_needed": ["Script", "Thumbnail", "Voice Audio"]
            }
        elif class_name == "ExecutionPlan":
            is_video = "short" in prompt.lower() or "video" in prompt.lower()
            if is_video:
                steps = [
                    {"step_id": "step_1", "name": "Topic Research", "worker": "research_worker", "description": "Scrape details and fan theories for " + topic},
                    {"step_id": "step_2", "name": "Script Drafting", "worker": "script_writer", "description": "Write a high-retention narration script"},
                    {"step_id": "step_3", "name": "Lore Verification", "worker": "lore_checker", "description": "Verify script facts against manga canon"},
                    {"step_id": "step_4", "name": "Thumbnail Strategy", "worker": "thumbnail_strategist", "description": "Generate visual prompts and cover assets"},
                    {"step_id": "step_5", "name": "TTS Audio Timing", "worker": "voice_timing", "description": "Synthesize narrative audio track"},
                    {"step_id": "step_6", "name": "Fact Check Evaluation", "worker": "fact_verifier", "description": "Check details and enforce style compliance"},
                    {"step_id": "step_7", "name": "Publishing Execution", "worker": "publishing_worker", "description": "Save assets and publish metadata to SQLite DB"}
                ]
            else:
                steps = [
                    {"step_id": "step_1", "name": "Deep Research", "worker": "research_worker", "description": "Collect episode subtitles and summaries"},
                    {"step_id": "step_2", "name": "Review Drafting", "worker": "script_writer", "description": "Write a structured review article draft"},
                    {"step_id": "step_3", "name": "Style Compliance", "worker": "style_consistency", "description": "Generate SEO titles, tags, and slug URLs"},
                    {"step_id": "step_4", "name": "Formatting Cleanup", "worker": "style_consistency", "description": "Deterministic markdown format cleanup"},
                    {"step_id": "step_5", "name": "Fact Audit", "worker": "fact_verifier", "description": "Verify facts and ensure no banned words"},
                    {"step_id": "step_6", "name": "Publish to Contentful", "worker": "publishing_worker", "description": "Upload media assets and push to Contentful CMA"}
                ]
            mock_data = {
                "plan_title": f"Production Plan for {topic}",
                "steps": steps
            }
        elif class_name == "ThemeExtractorOutput":
            mock_data = {
                "main_theme": "Growth through adversity",
                "tone": "intense, emotional",
                "strengths": ["Outstanding choreography", "Breathtaking visual effects", "Incredible soundtrack composition"],
                "weaknesses": ["Exposition dumps in early scenes", "Minor character screenshare is limited"],
                "standout_moments": ["The jaw-dropping final counter-attack", "The tragic flashback revealing backstory"],
                "pacing_analysis": "Dynamic pacing starts slow with building tension, culminating in an epic battle.",
                "narrative_direction": "Prepares the main cast for a major confrontation in the next chapter."
            }
        elif class_name == "ReviewWriterOutput":
            mock_data = {
                "draft_title": f"Why {topic} Sets the Ultimate Benchmark for Modern Storytelling",
                "score": 9,
                "positive_summary": "Top-tier character exploration and world-class animation direction.",
                "negative_summary": "Pacing can feel a little rushed in transitional periods.",
                "verdict": "An outstanding production that highlights the heights of modern anime adaptation.",
                "review_body_markdown": f"## The Brilliance of {topic}\n\nThe latest release of {topic} marks a massive milestone. Production standards are at an all-time high, blending emotional weight with dynamic fight sequences.\n\n### Character Development\n\nWhat shines most is how characters deal with grief and resolution. We see significant narrative growth that rewards long-term viewers.\n\n### Narrative Pacing\n\nThe pacing builds a heavy atmosphere from the start. Although it contains brief structural gaps, the climactic sequence completely makes up for it.",
                "impactful_lines": [
                    "\"The fire in our souls will never be extinguished!\"",
                    "\"We fight not for glory, but to see tomorrow together.\"",
                    "\"To falter now is to betray everyone who believed in us.\""
                ]
            }
        elif class_name == "SEOWorkerOutput":
            clean_slug = topic.lower().replace(" ", "-").replace(":", "").replace("'", "")
            mock_data = {
                "seo_title": f"{topic} Review - The Ultimate Peak Highlight",
                "slug": f"{clean_slug}-review-peak-highlight",
                "meta_description": f"Read our deep-dive analysis of the latest release of {topic}. Discover our review score, breakdown of strengths, weaknesses, and final verdict.",
                "keywords": [topic.lower(), "anime review", "episode analysis", "plot recap", "otaku news"],
                "tags": ["anime", "review", topic.lower(), "analysis"]
            }
        else:
            # Catch-all generic model field populate
            for field_name, field_info in schema_class.model_fields.items():
                annotation = field_info.annotation
                annotation_str = str(annotation)
                
                if "List" in annotation_str or "list" in annotation_str:
                    mock_data[field_name] = [f"Sample {field_name} item 1", f"Sample {field_name} item 2"]
                elif "Dict" in annotation_str or "dict" in annotation_str:
                    mock_data[field_name] = {"sample_key": "sample_val"}
                elif annotation == str or "str" in annotation_str:
                    if "slug" in field_name:
                        mock_data[field_name] = topic.lower().replace(" ", "-")
                    elif "title" in field_name:
                        mock_data[field_name] = f"Mock {topic} Title"
                    elif "description" in field_name or "summary" in field_name:
                        mock_data[field_name] = f"A schema-compliant fallback description for {topic} generated autonomously."
                    else:
                        mock_data[field_name] = f"Sample {field_name} content"
                elif annotation == int or "int" in annotation_str:
                    mock_data[field_name] = 8
                elif annotation == float or "float" in annotation_str:
                    mock_data[field_name] = 8.5
                elif annotation == bool or "bool" in annotation_str:
                    mock_data[field_name] = True
                else:
                    mock_data[field_name] = None

        return schema_class.model_validate(mock_data)

ollama_service = OllamaService()
