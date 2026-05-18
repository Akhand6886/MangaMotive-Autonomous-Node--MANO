import logging
from schemas import CollectorOutput, ThemeExtractorOutput, ReviewWriterOutput
from services.ollama_service import ollama_service

logger = logging.getLogger("ReviewWriterWorker")

class ReviewWriterWorker:
    """
    Worker 4: Review Writer Worker
    The main content generator. Uses structured outputs from earlier workers.
    The writer does NOT need to analyze everything anymore—heavy reasoning was done earlier.
    This dramatically improves small-model quality on Raspberry Pi 5.
    """
    async def process(self, collector_output: CollectorOutput, theme_output: ThemeExtractorOutput) -> ReviewWriterOutput:
        logger.info(f"[ReviewWriter] Drafting review article for: '{collector_output.title}'...")

        prompt = (
            f"Write a professional, engaging, and beautifully flowing review article for '{collector_output.title}'.\n\n"
            f"You MUST base your writing entirely on the following structured editorial intelligence extracted earlier:\n"
            f"- Main Theme: {theme_output.main_theme}\n"
            f"- Tone: {theme_output.tone}\n"
            f"- Strengths: {', '.join(theme_output.strengths)}\n"
            f"- Weaknesses: {', '.join(theme_output.weaknesses)}\n"
            f"- Standout Moments: {', '.join(theme_output.standout_moments)}\n"
            f"- Pacing Analysis: {theme_output.pacing_analysis}\n"
            f"- Narrative Direction: {theme_output.narrative_direction}\n\n"
            f"Produce an engaging review draft title, a numerical score (1-10), a positive summary, a negative summary, a one-sentence verdict, a multi-paragraph review body in markdown format, and up to 3 impactful quote lines."
        )

        writer_output = await ollama_service.generate_structured(
            prompt=prompt,
            schema_class=ReviewWriterOutput
        )

        logger.info(f"[ReviewWriter] Successfully drafted review: '{writer_output.draft_title}' (Score: {writer_output.score}/10)")
        return writer_output

review_writer_worker = ReviewWriterWorker()
