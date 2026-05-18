import re
import logging
from schemas import ReviewWriterOutput, SEOWorkerOutput, FormatterOutput

logger = logging.getLogger("FormattingWorker")

class FormattingWorker:
    """
    Worker 6: Formatting Worker
    Pure deterministic Python cleanup layer.
    Cleans markdown, fixes heading hierarchy, validates article structure,
    removes duplicate whitespaces, calculates word count, and extracts an excerpt.
    Usually No AI Needed.
    """
    def process(self, writer_output: ReviewWriterOutput, seo_output: SEOWorkerOutput) -> FormatterOutput:
        logger.info(f"[Formatter] Cleaning and formatting markdown for '{seo_output.seo_title}'...")

        raw_md = writer_output.review_body_markdown

        # Remove duplicate newlines and trailing spaces
        cleaned_md = re.sub(r'\n{3,}', '\n\n', raw_md)
        cleaned_md = "\n".join([line.rstrip() for line in cleaned_md.split("\n")])

        # Normalize heading hierarchy (ensure H1 is not used in body if H2 is expected)
        headings_fixed = False
        if "^# " in cleaned_md or "\n# " in cleaned_md:
            cleaned_md = re.sub(r'^# ', '## ', cleaned_md, flags=re.MULTILINE)
            headings_fixed = True

        # Calculate word count
        words = cleaned_md.split()
        word_count = len(words)

        # Extract 1-2 sentence excerpt hook
        sentences = re.split(r'(?<=[.!?])\s+', cleaned_md)
        excerpt = " ".join(sentences[:2]) if sentences else writer_output.verdict
        if len(excerpt) > 200:
            excerpt = excerpt[:197] + "..."

        formatter_output = FormatterOutput(
            cleaned_markdown=cleaned_md,
            validated_title=seo_output.seo_title,
            slug=seo_output.slug,
            word_count=word_count,
            excerpt=excerpt,
            headings_fixed=headings_fixed
        )

        logger.info(f"[Formatter] Formatting complete. Word count: {word_count}. Headings fixed: {headings_fixed}")
        return formatter_output

formatting_worker = FormattingWorker()
