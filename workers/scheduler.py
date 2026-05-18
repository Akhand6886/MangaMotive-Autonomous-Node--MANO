import logging
import uuid
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Job, Series
from services.anime_schedule import anime_schedule_service

logger = logging.getLogger("SchedulerWorker")

class SchedulerWorker:
    """
    Worker 1: Scheduler Worker
    Controls the continuous autonomous execution loop (Pillar 1).
    Polls AnimeSchedule.net timetable daily/periodically, checks local SQLite database,
    and queues new jobs for newly aired anime episodes.
    """
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(self.check_schedule_and_queue, 'interval', minutes=60, id='timetable_check')

    def start(self):
        """Starts the APScheduler background daemon."""
        logger.info("[Scheduler] Starting continuous autonomous execution loop daemon...")
        self.scheduler.start()

    def stop(self):
        """Stops the scheduler."""
        self.scheduler.shutdown()

    async def check_schedule_and_queue(self):
        """
        Polls timetable data and queues jobs for new episodes.
        """
        logger.info("[Scheduler] Waking up. Analyzing current state of the anime world...")
        db: Session = SessionLocal()
        try:
            timetable = await anime_schedule_service.get_timetable(air_type="sub")
            items = timetable.get("items", [])
            
            for item in items:
                series_title = item.get("title")
                episode_number = item.get("episodeNumber")
                synopsis = item.get("synopsis", "")
                media_url = item.get("imageVersionRoute")

                if not series_title or not episode_number:
                    continue

                # Check if this episode job is already queued or completed
                existing_job = db.query(Job).filter(
                    Job.series_title == series_title,
                    Job.episode_number == episode_number,
                    Job.target_type == "episode_recap"
                ).first()

                if existing_job:
                    logger.debug(f"[Scheduler] Job already exists for {series_title} Ep {episode_number}. Skipping.")
                    continue

                # Look up existing series in local DB for linking
                series = db.query(Series).filter(Series.title == series_title).first()
                series_id = series.id if series else None

                # Create new Job entry in SQLite
                job_id = str(uuid.uuid4())
                new_job = Job(
                    id=job_id,
                    target_type="episode_recap",
                    series_id=series_id,
                    series_title=series_title,
                    episode_number=episode_number,
                    status="queued",
                    collector_data={
                        "title": f"{series_title} Episode {episode_number}",
                        "series_id": series_id,
                        "episode_number": episode_number,
                        "summary": synopsis,
                        "subtitles": f"Auto-generated transcript simulation for {series_title} episode {episode_number}. {synopsis}",
                        "characters": ["Main Protagonist", "Rival", "Antagonist"],
                        "raw_synopsis": synopsis,
                        "media_url": media_url
                    }
                )
                db.add(new_job)
                db.commit()
                logger.info(f"[Scheduler] Successfully queued new job {job_id} for {series_title} Ep {episode_number}")

        except Exception as e:
            logger.error(f"[Scheduler] Critical daemon error during schedule check: {e}")
            db.rollback()
        finally:
            db.close()
            logger.info("[Scheduler] Tasks complete. Going back to sleep.")

scheduler_worker = SchedulerWorker()
