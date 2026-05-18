import logging
from schemas import CollectorOutput, ThemeExtractorOutput
from services.ollama_service import ollama_service

logger = logging.getLogger("ThemeExtractorWorker")

class ThemeExtractorWorker:
    """
    Worker 3: Theme Extractor Worker
    Uses a small LLM (Gemma 4 E2B / Qwen2.5) to analyze cleaned transcript chunks.
    Identifies emotional themes, pacing, standout moments, strengths/weaknesses.
    Converts chaotic raw text into structured editorial intelligence.
    """
    async def process(self, collector_output: CollectorOutput) -> ThemeExtractorOutput:
        logger.info(f"[ThemeExtractor] Extracting themes and pacing for: '{collector_output.title}'...")

        prompt = (
            f"Analyze the following raw synopsis and subtitle transcript for the anime/manga '{collector_output.title}'.\n\n"
            f"--- SYNOPSIS ---\n{collector_output.summary}\n\n"
            f"--- TRANSCRIPT CHUNKS ---\n{collector_output.subtitles}\n\n"
            f"--- CHARACTERS INVOLVED ---\n{', '.join(collector_output.characters)}\n\n"
            f"Based on this data, extract the core emotional themes, pacing analysis, standout moments, strengths, weaknesses, and overall narrative direction."
        )

        theme_output = await ollama_service.generate_structured(
            prompt=prompt,
            schema_class=ThemeExtractorOutput
        )

        logger.info(f"[ThemeExtractor] Successfully extracted themes: {theme_output.main_theme} (Tone: {theme_output.tone})")
        return theme_output

theme_extractor_worker = ThemeExtractorWorker()
