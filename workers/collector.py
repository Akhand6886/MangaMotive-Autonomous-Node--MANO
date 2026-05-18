import logging
from typing import Dict, Any
from models import Job
from schemas import CollectorOutput

logger = logging.getLogger("DataCollectorWorker")

class DataCollectorWorker:
    """
    Worker 2: Data Collector Worker
    Collects raw information (episode metadata, subtitles, synopsis, ratings, character data).
    Usually No AI Needed. Mostly APIs + scraping.
    Produces structured CollectorOutput.
    """
    async def process(self, job: Job) -> CollectorOutput:
        logger.info(f"[Collector] Gathering raw data for Job {job.id} ({job.series_title})...")
        
        # Extract pre-seeded collector data from Scheduler or provide rich fallback defaults
        data = job.collector_data or {}
        
        title = data.get("title") or (f"{job.series_title} Episode {job.episode_number}" if job.episode_number else job.series_title)
        summary = data.get("summary") or f"An exciting installment in the {job.series_title} series filled with intense battles and dramatic character progression."
        subtitles = data.get("subtitles") or f"[00:01] {job.series_title} opening plays.\n[00:05] 'We must protect our friends at all costs!'\n[00:15] Dramatic clash ensues.\n[00:20] To be continued..."
        characters = data.get("characters") or ["Protagonist", "Deuteragonist", "Antagonist"]
        raw_synopsis = data.get("raw_synopsis") or summary
        media_url = data.get("media_url") or "https://images.unsplash.com/photo-1541963463532-d68292c34b19"

        collector_output = CollectorOutput(
            title=title,
            series_id=job.series_id,
            episode_number=job.episode_number,
            summary=summary,
            subtitles=subtitles,
            characters=characters,
            raw_synopsis=raw_synopsis,
            media_url=media_url
        )

        logger.info(f"[Collector] Data gathering complete for '{title}'.")
        return collector_output

data_collector_worker = DataCollectorWorker()
