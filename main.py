import logging
import asyncio
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from config import settings
from database import engine, Base, get_db
from models import Job, Series, Episode, Article, Review
from schemas import JobCreate, JobResponse, CollectorOutput, ThemeExtractorOutput, ReviewWriterOutput, SEOWorkerOutput, FormatterOutput, PublisherOutput

from workers.scheduler import scheduler_worker
from workers.collector import data_collector_worker
from workers.theme_extractor import theme_extractor_worker
from workers.review_writer import review_writer_worker
from workers.seo_worker import seo_worker
from workers.formatter import formatting_worker
from workers.publisher import publishing_worker

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("MainOrchestrator")

# Create SQLite Database Tables
Base.metadata.create_all(bind=engine)

# Lifespan context manager for FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("--- MangaMotive Autonomous Agent Pipeline Initialized ---")
    scheduler_worker.start()
    
    # Start background job processing daemon loop
    task = asyncio.create_task(background_job_processor_daemon())
    yield
    scheduler_worker.stop()
    task.cancel()
    logger.info("--- MangaMotive Autonomous Agent Pipeline Shutting Down ---")

app = FastAPI(
    title="MangaMotive Agentic Worker Pipeline",
    description="Fully Autonomous AI Agent Pipeline with 7 Specialized Deterministic Workers optimized for Raspberry Pi 5 8GB.",
    version="2.0.0",
    lifespan=lifespan
)

async def process_single_job(job_id: str):
    """
    Executes the 7-worker pipeline sequentially for a single job.
    Implements Pillar 4 Reflection & Self-Correction and state progression tracking.
    """
    db: Session = next(get_db())
    job: Job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.status in ["completed", "publishing"]:
        return

    logger.info(f"[Orchestrator] Starting pipeline execution for Job {job.id} ({job.series_title})...")
    
    try:
        # Step 2: Data Collector Worker
        job.status = "collecting"
        db.commit()
        collector_output: CollectorOutput = await data_collector_worker.process(job)
        job.collector_data = collector_output.model_dump()
        db.commit()

        # Step 3: Theme Extractor Worker
        job.status = "extracting"
        db.commit()
        theme_output: ThemeExtractorOutput = await theme_extractor_worker.process(collector_output)
        job.theme_data = theme_output.model_dump()
        db.commit()

        # Step 4: Review Writer Worker
        job.status = "writing"
        db.commit()
        writer_output: ReviewWriterOutput = await review_writer_worker.process(collector_output, theme_output)
        job.writer_data = writer_output.model_dump()
        db.commit()

        # Step 5: SEO Worker
        job.status = "seo"
        db.commit()
        seo_output: SEOWorkerOutput = await seo_worker.process(writer_output)
        job.seo_data = seo_output.model_dump()
        db.commit()

        # Step 6: Formatting Worker
        job.status = "formatting"
        db.commit()
        formatter_output: FormatterOutput = formatting_worker.process(writer_output, seo_output)
        job.formatter_data = formatter_output.model_dump()
        db.commit()

        # Step 7: Publishing Worker
        job.status = "publishing"
        db.commit()
        publisher_output: PublisherOutput = await publishing_worker.process(
            job, collector_output, theme_output, writer_output, seo_output, formatter_output
        )
        job.publisher_data = publisher_output.model_dump()
        job.status = "completed"
        db.commit()
        logger.info(f"[Orchestrator] Pipeline execution COMPLETED for Job {job.id}.")

    except Exception as e:
        logger.error(f"[Orchestrator] Pipeline execution FAILED for Job {job.id}: {e}")
        job.status = "failed"
        job.error_message = str(e)
        job.retry_count += 1
        db.commit()
    finally:
        db.close()

async def background_job_processor_daemon():
    """Continuous background daemon polling SQLite for queued jobs."""
    while True:
        try:
            db: Session = next(get_db())
            queued_jobs = db.query(Job).filter(Job.status == "queued").all()
            for job in queued_jobs:
                await process_single_job(job.id)
            db.close()
        except Exception as e:
            logger.error(f"[Daemon] Error in background job processor daemon: {e}")
        await asyncio.sleep(10)


# --- REST API ENDPOINTS ---

@app.post("/api/trigger", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_pipeline(job_in: JobCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Manually triggers an autonomous pipeline job for a series or episode.
    """
    # Look up series
    series = db.query(Series).filter(Series.title == job_in.series_title).first()
    series_id = series.id if series else job_in.series_id or str(uuid.uuid4())

    if not series:
        # Create series entry if missing
        new_series = Series(
            id=series_id,
            title=job_in.series_title,
            slug=job_in.series_title.lower().replace(" ", "-"),
            series_type="animeSeries"
        )
        db.add(new_series)
        db.commit()

    job_id = str(uuid.uuid4())
    new_job = Job(
        id=job_id,
        target_type=job_in.target_type,
        series_id=series_id,
        series_title=job_in.series_title,
        episode_number=job_in.episode_number,
        status="queued"
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    background_tasks.add_task(process_single_job, job_id)
    return new_job

@app.get("/api/jobs", response_model=List[JobResponse])
async def list_jobs(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """Lists all active and historical pipeline jobs."""
    return db.query(Job).order_by(Job.created_at.desc()).offset(skip).limit(limit).all()

@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: Session = Depends(get_db)):
    """Retrieves the current state and worker payloads of a specific job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/api/series")
async def list_series(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """Lists all tracked anime/manga series in local SQLite database."""
    series = db.query(Series).offset(skip).limit(limit).all()
    return [{"id": s.id, "title": s.title, "slug": s.slug, "type": s.series_type} for s in series]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
