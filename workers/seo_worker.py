import logging
from schemas import ReviewWriterOutput, SEOWorkerOutput
from services.ollama_service import ollama_service

logger = logging.getLogger("SEOWorker")

class SEOWorker:
    """
    Worker 5: SEO Worker
    Separate SEO from writing. Generates SEO title, slug, meta description, keywords, and tags.
    Separating SEO logic prevents polluting the writing quality of the main review draft.
    """
    async def process(self, writer_output: ReviewWriterOutput) -> SEOWorkerOutput:
        logger.info(f"[SEOWorker] Generating SEO metadata for draft: '{writer_output.draft_title}'...")

        prompt = (
            f"Analyze the following review article draft and generate highly optimized SEO metadata.\n\n"
            f"--- DRAFT TITLE ---\n{writer_output.draft_title}\n\n"
            f"--- REVIEW BODY ---\n{writer_output.review_body_markdown}\n\n"
            f"Generate an SEO title (under 60 chars), a URL-friendly slug (kebab-case), a compelling meta description (under 160 chars), high-value search keywords, and category tags."
        )

        seo_output = await ollama_service.generate_structured(
            prompt=prompt,
            schema_class=SEOWorkerOutput
        )

        logger.info(f"[SEOWorker] Successfully generated SEO metadata: Slug '{seo_output.slug}'")
        return seo_output

seo_worker = SEOWorker()
