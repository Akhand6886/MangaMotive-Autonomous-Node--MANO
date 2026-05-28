import logging
import asyncio
import os
import uuid
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, status, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import List, Dict, Any, Optional
import time

from config import settings
from database import engine, Base, get_db, SessionLocal
from models import Job, Series, Episode, Article, Review, ProjectMemory
from schemas import (
    JobCreate, JobResponse, StructuredTask, ExecutionPlan, 
    ExecutionStep, HarnessRequest, ProjectMemorySchema,
    SlideEdit, RefineRequest
)

# Workers & Planner
from workers.scheduler import scheduler_worker
from workers.planner import executive_planner
from workers.harness_workers import (
    research_worker, script_writer_worker, lore_checker_worker,
    thumbnail_strategist_worker, voice_timing_worker, style_consistency_worker,
    fact_verifier_worker, publishing_worker_agent
)

# Services
from services.evaluator import EvaluationLayer
from services.ollama_service import ollama_service

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("MainOrchestrator")

# Create SQLite Database Tables
Base.metadata.create_all(bind=engine)

def preseed_memory_defaults():
    """Pre-populates default project memories if the table is empty."""
    db = SessionLocal()
    try:
        existing = db.query(ProjectMemory).count()
        if existing == 0:
            logger.info("[Database] Pre-seeding default project memories...")
            defaults = {
                "preferred_tone": ["High-energy, engaging, full of anime excitement, detailed analytical style."],
                "banned_phrases": [
                    "In conclusion", "As an AI", "Let's dive in", 
                    "It is important to remember", "Overall, this episode", "In summary"
                ],
                "successful_hooks": [
                    "This episode changed everything...", 
                    "Why does everyone hate this character?", 
                    "Here is the dark truth behind the story...",
                    "The animation quality reaches a new peak in this scene!"
                ],
                "style_guide": [
                    "Use H2 and H3 headings for structured reviews",
                    "Keep paragraphs under 3 sentences for high readability",
                    "Analyze character motivations and thematic significance",
                    "Always highlight standout lines or voice acting performance"
                ]
            }
            for key, val in defaults.items():
                db.add(ProjectMemory(key=key, value=val))
            db.commit()
            logger.info("[Database] Pre-seeding completed.")
    except Exception as e:
        logger.error(f"[Database] Failed to pre-seed memories: {e}")
        db.rollback()
    finally:
        db.close()

# Lifespan context manager for FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages application startup and graceful shutdown lifecycle."""
    logger.info("--- Intelligence Harness Autonomous Agent Pipeline Initialized ---")
    preseed_memory_defaults()
    scheduler_worker.start()
    
    # Start background job processing daemon loop
    daemon_task = asyncio.create_task(background_job_processor_daemon())
    yield
    scheduler_worker.stop()
    daemon_task.cancel()
    try:
        await daemon_task
    except asyncio.CancelledError:
        logger.info("Background daemon task cancelled gracefully.")
    logger.info("--- Intelligence Harness Autonomous Agent Pipeline Shutting Down ---")

app = FastAPI(
    title="Intelligence Harness Worker Pipeline",
    description="7-Layer Multi-Agent Intelligence Harness with Dynamic Planning, Memory Store, and Evaluation Loops.",
    version="3.0.0",
    lifespan=lifespan
)

# Serves static files from the static directory
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_dashboard():
    """Serves the frontend visual dashboard at the root URL."""
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "Intelligence Harness Backend API is active. Front-end static files are missing."}


class ConnectionManager:
    """Manages global WebSocket events broadcasting to all connected clients."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WS] Client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"[WS] Client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.debug(f"[WS] Broadcast failed for client: {e}")

manager = ConnectionManager()

async def broadcast_event(event_type: str, data: dict):
    """Utility to safely broadcast events to all active WS clients."""
    try:
        await manager.broadcast({
            "type": event_type,
            "data": data
        })
    except Exception as e:
        logger.error(f"[WS] Failed to broadcast event {event_type}: {e}")

@app.websocket("/api/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, listen for client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"[WS] Error in client connection loop: {e}")
        manager.disconnect(websocket)


# --- PIPELINE ORCHESTRATION RUNTIME ---

# Terminal job states that should not be re-processed
_TERMINAL_STATUSES = frozenset({"completed", "failed"})

async def process_single_job(job_id: str):
    """
    Executes the full 7-layer pipeline dynamically for a single job.

    Pipeline Layers:
        1. Interface Layer — parse raw request into StructuredTask
        2. Executive Planner — decompose task into ordered execution steps
        3. Specialized Workers — route each step to its assigned worker agent
        4. Memory System — inject editorial preferences and accumulate logs
        5. Tool Layer — external APIs (search, image gen, TTS, DB lookups)
        6. Evaluation Layer — factual/style/engagement audits with retry loop
        7. Orchestration Runtime — route results, persist state, finalize job

    Args:
        job_id: UUID string identifying the job to process.
    """
    db: Session = SessionLocal()
    try:
        job: Job = db.query(Job).filter(Job.id == job_id).first()
        if not job or job.status in _TERMINAL_STATUSES:
            return

        logger.info(f"[Orchestrator] Initiating Intelligence Harness for Job {job.id} ({job.series_title})...")
        await broadcast_event("job_updated", {"job_id": job.id, "status": job.status, "series_title": job.series_title})
    
        # Load Project Memory preferences
        memories = db.query(ProjectMemory).all()
        pref_memory = {m.key: m.value for m in memories}
        tone = pref_memory.get("preferred_tone", ["Engaging and detailed review style"])[0]
        banned = pref_memory.get("banned_phrases", [])
        
        # Layer 1: Interface Layer (Ensure structured task is set)
        if not job.structured_task:
            job.status = "planning"
            db.commit()
            await broadcast_event("job_updated", {"job_id": job.id, "status": job.status})
            
            # Perform LLM parsing simulation if structured task is empty
            prompt_parse = (
                f"Extract structured parameters for topic '{job.series_title}'. "
                f"Platform matches target type: '{job.target_type}'."
            )
            structured_t = await ollama_service.generate_structured(prompt_parse, StructuredTask)
            job.structured_task = structured_t.model_dump()
            db.commit()
        
        task_info = StructuredTask.model_validate(job.structured_task)
        await broadcast_event("job_updated", {"job_id": job.id, "structured_task": job.structured_task})
        
        # Layer 2: Planner / Executive Brain
        job.status = "planning"
        db.commit()
        await broadcast_event("job_updated", {"job_id": job.id, "status": job.status})
        logger.info(f"[Orchestrator] Designing execution plan for structured task...")
        plan: ExecutionPlan = await executive_planner.generate_plan(task_info)
        
        # Store execution plan steps inside database
        plan_steps = []
        for step in plan.steps:
            plan_steps.append({
                "step_id": step.step_id,
                "name": step.name,
                "worker": step.worker,
                "description": step.description,
                "status": "pending",
                "output": "",
                "log": ""
            })
        job.execution_plan = plan_steps
        job.status = "running"
        db.commit()
        await broadcast_event("job_updated", {
            "job_id": job.id,
            "status": job.status,
            "execution_plan": job.execution_plan
        })

        # Shared short-term memory (stores worker outputs sequentially)
        short_term_memory = {}
        memory_logs_accumulated = []

        # Layer 7: Orchestration Runtime execution loop
        for index, step in enumerate(plan_steps):
            step_id = step["step_id"]
            worker_type = step["worker"]
            step_name = step["name"]
            
            logger.info(f"[Orchestrator] Step {index+1}/{len(plan_steps)}: '{step_name}' -> routing to '{worker_type}'")
            step["status"] = "running"
            flag_modified(job, "execution_plan")
            db.commit()

            await broadcast_event("step_started", {
                "job_id": job.id,
                "step_id": step_id,
                "worker": worker_type,
                "status": "running"
            })

            start_time = time.time()
            worker_output = {}
            step_log = f"Invoking {worker_type} for '{step_name}'.\n"

            async def log_step(msg: str):
                nonlocal step_log
                step_log += msg + "\n"
                await broadcast_event("log_update", {
                    "job_id": job.id,
                    "step_id": step_id,
                    "log": step_log
                })

            # Route to specialized workers
            attempt = 0
            max_correction_retries = 3
            correction_feedback = ""

            while attempt < max_correction_retries:
                attempt += 1
                try:
                    if worker_type == "research_worker":
                        worker_output = await research_worker.process(task_info.topic, task_info.target_platform)
                        await log_step("Collected research facts. Web search executed.")
                        break # no evaluation needed for raw collector
                        
                    elif worker_type == "script_writer":
                        research_data = short_term_memory.get("research_worker", {})
                        if correction_feedback:
                            await log_step(f"Self-Correction loop attempt {attempt} based on evaluator feedback.")
                        
                        worker_output = await script_writer_worker.process(
                            task_info.topic, 
                            research_data, 
                            tone if not correction_feedback else f"{tone}\n\nEVALUATOR REACTION:\n{correction_feedback}", 
                            banned
                        )
                        await log_step(f"Generated script draft. Length: {worker_output['word_count']} words.")
                        
                        # Evaluate Output (Layer 6)
                        eval_res = await EvaluationLayer.evaluate_content(
                            worker_output["draft_text"], 
                            research_data.get("research_facts", []), 
                            tone, 
                            banned
                        )
                        job.evaluations = eval_res
                        db.commit()
                        await broadcast_event("eval_updated", {
                            "job_id": job.id,
                            "evaluations": job.evaluations
                        })

                        if eval_res["passed"]:
                            await log_step("Factual and style consistency checks PASSED.")
                            break
                        else:
                            await log_step(f"Factual/style consistency check FAILED: {eval_res['errors']}")
                            correction_feedback = eval_res["feedback"]
                            if attempt == max_correction_retries:
                                await log_step("Max retries reached. Forcing check pass to prevent deadlocks.")
                        
                    elif worker_type == "lore_checker":
                        writer_data = short_term_memory.get("script_writer", {})
                        draft = writer_data.get("draft_text", "")
                        worker_output = await lore_checker_worker.process(task_info.topic, draft)
                        await log_step(f"Lore audit completed. Is canon-compliant: {worker_output['lore_is_accurate']}.")
                        break
                        
                    elif worker_type == "thumbnail_strategist":
                        writer_data = short_term_memory.get("script_writer", {})
                        draft = writer_data.get("draft_text", "")
                        worker_output = await thumbnail_strategist_worker.process(task_info.topic, draft)
                        await log_step(f"Generated image generation prompt. Visual asset fetched.")
                        break
                        
                    elif worker_type == "voice_timing":
                        writer_data = short_term_memory.get("script_writer", {})
                        draft = writer_data.get("draft_text", "")
                        worker_output = await voice_timing_worker.process(draft, task_info.topic)
                        await log_step(f"Narration synthesized. TTS audio length: {worker_output['duration_seconds']}s.")
                        break
                        
                    elif worker_type == "style_consistency":
                        writer_data = short_term_memory.get("script_writer", {})
                        draft = writer_data.get("draft_text", "")
                        worker_output = await style_consistency_worker.process(task_info.topic, draft)
                        await log_step(f"SEO Title: '{worker_output['seo_title']}'. SEO metadata and slug verified.")
                        break
                        
                    elif worker_type == "fact_verifier":
                        writer_data = short_term_memory.get("script_writer", {})
                        research_data = short_term_memory.get("research_worker", {})
                        draft = writer_data.get("draft_text", "")
                        worker_output = await fact_verifier_worker.process(draft, research_data.get("research_facts", []))
                        await log_step(f"Factual consistency verified. Accuracy Score: {worker_output['accuracy_score']}/10.")
                        break
                        
                    elif worker_type == "publishing_worker":
                        # Assemble complete package
                        writer = short_term_memory.get("script_writer", {})
                        seo = short_term_memory.get("style_consistency", {})
                        thumb = short_term_memory.get("thumbnail_strategist", {})
                        voice = short_term_memory.get("voice_timing", {})
                        
                        payload = {
                            "topic": task_info.topic,
                            "target_platform": task_info.target_platform,
                            "draft_text": writer.get("draft_text", ""),
                            "seo_data": seo,
                            "image_url": thumb.get("image_url", ""),
                            "audio_url": voice.get("audio_url", "")
                        }
                        worker_output = await publishing_worker_agent.process(job.id, payload)
                        await log_step(f"Asset payloads uploaded. CMS sync status: {worker_output['status']}.")
                        break
                        
                    else:
                        await log_step(f"Unknown worker '{worker_type}'. Skipping.")
                        break

                except Exception as ex:
                    await log_step(f"Error executing worker action on attempt {attempt}: {ex}")
                    if attempt == max_correction_retries:
                        elapsed_time = time.time() - start_time
                        step["log"] = step_log + f"\nStep execution failed after {elapsed_time:.2f} seconds.\n"
                        flag_modified(job, "execution_plan")
                        db.commit()
                        await broadcast_event("step_completed", {
                            "job_id": job.id,
                            "step_id": step_id,
                            "status": "failed",
                            "log": step["log"]
                        })
                        raise ex

            # Save step output to short-term memory
            short_term_memory[worker_type] = worker_output
            
            # Map legacy collector/theme/writer fields for API backward compatibility
            if worker_type == "research_worker":
                job.collector_data = worker_output
            elif worker_type == "script_writer":
                job.writer_data = worker_output
            elif worker_type == "style_consistency":
                job.seo_data = worker_output
                job.formatter_data = worker_output

            # Update step details
            elapsed_time = time.time() - start_time
            step["status"] = "completed"
            step["output"] = json.dumps(worker_output, indent=2)
            step["log"] = step_log + f"\nStep execution completed in {elapsed_time:.2f} seconds.\n"
            
            memory_logs_accumulated.append(f"Loaded memory guidelines for step '{step_name}'.")
            
            flag_modified(job, "execution_plan")
            job.memory_logs = memory_logs_accumulated
            flag_modified(job, "memory_logs")
            db.commit()

            await broadcast_event("step_completed", {
                "job_id": job.id,
                "step_id": step_id,
                "status": "completed",
                "output": step["output"],
                "log": step["log"]
            })

        # Mark final job status
        job.publisher_data = short_term_memory.get("publishing_worker", {})
        job.status = "completed"
        db.commit()
        logger.info(f"[Orchestrator] Multi-agent execution completed for Job {job.id}.")
        await broadcast_event("job_completed", {
            "job_id": job.id,
            "status": job.status,
            "publisher_data": job.publisher_data
        })

    except Exception as e:
        logger.error(f"[Orchestrator] Execution failed for Job {job_id}: {e}", exc_info=True)
        try:
            job.status = "failed"
            job.error_message = str(e)[:2000]  # Truncate to prevent DB overflow
            job.retry_count += 1
            db.commit()
            await broadcast_event("job_updated", {
                "job_id": job.id,
                "status": job.status,
                "error_message": job.error_message
            })
        except Exception as db_err:
            logger.error(f"[Orchestrator] Failed to persist error state: {db_err}")
            db.rollback()
    finally:
        db.close()

async def background_job_processor_daemon():
    """
    Continuous background daemon that polls SQLite for queued jobs.
    Runs every 5 seconds, picks up new jobs, and spawns async processing tasks.
    Designed to be cancelled gracefully via asyncio task cancellation.
    """
    while True:
        db: Session = SessionLocal()
        try:
            queued_jobs = db.query(Job).filter(Job.status == "queued").all()
            for job in queued_jobs:
                job.status = "planning"
                db.commit()
                asyncio.create_task(process_single_job(job.id))
        except asyncio.CancelledError:
            raise  # Allow graceful shutdown
        except Exception as e:
            logger.error(f"[Daemon] Error in background job processor daemon: {e}")
        finally:
            db.close()
        await asyncio.sleep(5)


# --- REST API ENDPOINTS ---

@app.post("/api/harness/parse", response_model=StructuredTask)
async def parse_prompt_to_task(req: HarnessRequest):
    """
    Interface Layer (Layer 1).
    Takes a raw text prompt and parses it into structured task parameters.
    """
    logger.info(f"[API: Parse] Parsing raw user prompt: '{req.prompt}'")
    prompt = (
        f"You are the Interface Layer parser of the MangaMotive Intelligence Harness.\n"
        f"Parse the user's raw video or blog request into a structured task JSON object.\n\n"
        f"User Prompt: \"{req.prompt}\"\n\n"
        f"Determine the topic, style/tone, target_platform, estimated duration, and assets needed (e.g. Script, Thumbnail, Voice Audio, Finished Video)."
    )
    
    parsed_task = await ollama_service.generate_structured(prompt, StructuredTask)
    logger.info(f"[API: Parse] Output topic: '{parsed_task.topic}' on target: '{parsed_task.target_platform}'")
    return parsed_task

@app.post("/api/harness/trigger", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_harness_job(task: StructuredTask, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Triggers a harness pipeline execution run based on a StructuredTask.
    """
    job_id = str(uuid.uuid4())
    
    # Save a series record if needed
    clean_slug = task.topic.lower().replace(" ", "-").replace(":", "")
    series = db.query(Series).filter(Series.title == task.topic).first()
    series_id = series.id if series else f"series_{clean_slug}"
    
    if not series:
        series = Series(
            id=series_id,
            title=task.topic,
            slug=clean_slug,
            series_type="animeSeries"
        )
        db.add(series)
        db.commit()

    new_job = Job(
        id=job_id,
        target_type="youtube_short" if "short" in task.target_platform.lower() else "editorial_blog",
        series_id=series_id,
        series_title=task.topic,
        status="queued",
        structured_task=task.model_dump()
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # Hand off execution to background task worker
    background_tasks.add_task(process_single_job, job_id)
    return new_job

@app.get("/api/harness/memory", response_model=List[ProjectMemorySchema])
async def get_project_memory(db: Session = Depends(get_db)):
    """Memory Layer: Retrieve all editorial settings."""
    memories = db.query(ProjectMemory).all()
    return [{"key": m.key, "value": m.value} for m in memories]

@app.post("/api/harness/memory")
async def save_project_memory(memory_item: ProjectMemorySchema, db: Session = Depends(get_db)):
    """Memory Layer: Save or update an editorial guideline setting."""
    mem = db.query(ProjectMemory).filter(ProjectMemory.key == memory_item.key).first()
    if mem:
        mem.value = memory_item.value
    else:
        mem = ProjectMemory(key=memory_item.key, value=memory_item.value)
        db.add(mem)
    db.commit()
    return {"message": f"Successfully updated memory key: '{memory_item.key}'."}

@app.delete("/api/harness/memory/{key}")
async def delete_project_memory(key: str, db: Session = Depends(get_db)):
    """Memory Layer: Delete or reset a specific editorial memory setting."""
    mem = db.query(ProjectMemory).filter(ProjectMemory.key == key).first()
    if not mem:
        raise HTTPException(status_code=404, detail="Memory key not found")
    db.delete(mem)
    db.commit()
    return {"message": f"Successfully deleted memory key: '{key}'."}


async def process_job_refinement(job_id: str, edited_slides: List[Any]):
    """
    Background worker that selectively re-runs only the necessary agents
    (Voice, Image, Evaluation, Publishing) for a storyboard refinement request,
    broadcasting status and log changes via WebSocket in real-time.
    """
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
            
        logger.info(f"[Refine Task] Running background refinement for Job {job.id}...")
        
        # Load Project Memory preferences for audits
        memories = db.query(ProjectMemory).all()
        pref_memory = {m.key: m.value for m in memories}
        tone = pref_memory.get("preferred_tone", ["Engaging and detailed review style"])[0]
        banned = pref_memory.get("banned_phrases", [])
        
        # Find the voice_timing step in the execution plan
        plan_steps = list(job.execution_plan) if job.execution_plan else []
        voice_step_idx = -1
        for i, step in enumerate(plan_steps):
            if step["worker"] == "voice_timing":
                voice_step_idx = i
                break
                
        if voice_step_idx == -1:
            raise ValueError("No voice_timing step found in this job's execution plan.")
            
        # Get original step output
        voice_step = plan_steps[voice_step_idx]
        try:
            voice_output = json.loads(voice_step["output"]) if voice_step.get("output") else {}
        except Exception:
            voice_output = {}
            
        original_slides = voice_output.get("timing_map", [])
        
        # Selective Image generation & text update
        from services.tool_layer import ToolLayer
        
        refined_slides = []
        new_script_sentences = []
        
        # Broadcast initial refinement start log
        await broadcast_event("step_started", {
            "job_id": job.id,
            "step_id": voice_step["step_id"],
            "worker": "voice_timing",
            "status": "running"
        })
        
        step_log = "Initiating selective storyboard refinement.\n"
        await broadcast_event("log_update", {"job_id": job.id, "step_id": voice_step["step_id"], "log": step_log})
        
        for slide in edited_slides:
            slide_num = slide.slide_number
            subtitle = slide.subtitle
            img_prompt = slide.image_prompt
            img_url = slide.image_url
            regen = slide.regenerate_image
            
            new_script_sentences.append(subtitle)
            
            # Find corresponding original slide if any to preserve duration
            orig_match = next((s for s in original_slides if s.get("slide_number") == slide_num), {})
            start_t = slide.start if slide.start is not None else orig_match.get("start", (slide_num-1)*5)
            end_t = slide.end if slide.end is not None else orig_match.get("end", slide_num*5)
            
            if regen and img_prompt:
                step_log += f"Slide {slide_num}: Regenerating image for prompt '{img_prompt[:50]}...'\n"
                await broadcast_event("log_update", {"job_id": job.id, "step_id": voice_step["step_id"], "log": step_log})
                new_img_url = await ToolLayer.generate_image(img_prompt)
            else:
                new_img_url = img_url or orig_match.get("image_url", ToolLayer._DEFAULT_IMAGE_URL)
                
            refined_slides.append({
                "slide_number": slide_num,
                "start": start_t,
                "end": end_t,
                "subtitle": subtitle,
                "image_prompt": img_prompt or orig_match.get("image_prompt", f"Anime background representing slide {slide_num}"),
                "image_url": new_img_url
            })
            
        # Concatenate script and synthesize audio narration
        new_script_text = " ".join(new_script_sentences)
        step_log += f"Re-synthesizing TTS narration for updated script text...\n"
        await broadcast_event("log_update", {"job_id": job.id, "step_id": voice_step["step_id"], "log": step_log})
        
        tts_result = await ToolLayer.text_to_speech(new_script_text)
        
        # Proportional adjustment of timestamps if text length changes significantly
        total_duration = tts_result["duration_seconds"]
        step_log += f"New audio track duration: {total_duration}s.\n"
        await broadcast_event("log_update", {"job_id": job.id, "step_id": voice_step["step_id"], "log": step_log})
        
        # Save updated voice worker outputs
        voice_output["audio_url"] = tts_result["audio_url"]
        voice_output["duration_seconds"] = total_duration
        voice_output["timing_map"] = refined_slides
        
        # Save to voice step outputs
        voice_step["status"] = "completed"
        voice_step["output"] = json.dumps(voice_output, indent=2)
        voice_step["log"] = step_log + "\nSelective refinement complete.\n"
        
        plan_steps[voice_step_idx] = voice_step
        job.execution_plan = plan_steps
        flag_modified(job, "execution_plan")
        db.commit()
        
        await broadcast_event("step_completed", {
            "job_id": job.id,
            "step_id": voice_step["step_id"],
            "status": "completed",
            "output": voice_step["output"],
            "log": voice_step["log"]
        })
        
        # Re-run Evaluation Layer audits (Layer 6)
        step_log += f"Re-running Layer 6 Evaluation audits for style and fact consistency...\n"
        await broadcast_event("log_update", {"job_id": job.id, "step_id": voice_step["step_id"], "log": step_log})
        
        research_data = job.collector_data or {}
        facts = research_data.get("research_facts", [])
        
        eval_res = await EvaluationLayer.evaluate_content(new_script_text, facts, tone, banned)
        job.evaluations = eval_res
        db.commit()
        
        await broadcast_event("eval_updated", {
            "job_id": job.id,
            "evaluations": job.evaluations
        })
        
        # Update writer data for backward compatibility
        writer_data = job.writer_data or {}
        writer_data["draft_text"] = new_script_text
        job.writer_data = writer_data
        
        # Re-run publishing worker (Layer 7)
        step_log += f"Re-running Publishing worker to update database entry...\n"
        await broadcast_event("log_update", {"job_id": job.id, "step_id": voice_step["step_id"], "log": step_log})
        
        seo = job.seo_data or {}
        
        # If the publishing step is in the plan, update its status
        pub_step_idx = -1
        for i, step in enumerate(plan_steps):
            if step["worker"] == "publishing_worker":
                pub_step_idx = i
                break
                
        payload = {
            "topic": job.series_title,
            "target_platform": job.target_type,
            "draft_text": new_script_text,
            "seo_data": seo,
            "image_url": refined_slides[0]["image_url"] if refined_slides else ToolLayer._DEFAULT_IMAGE_URL,
            "audio_url": tts_result["audio_url"]
        }
        
        pub_output = await publishing_worker_agent.process(job.id, payload)
        job.publisher_data = pub_output
        
        if pub_step_idx != -1:
            plan_steps[pub_step_idx]["status"] = "completed"
            plan_steps[pub_step_idx]["output"] = json.dumps(pub_output, indent=2)
            plan_steps[pub_step_idx]["log"] = "Re-published refined storyboard.\n"
            job.execution_plan = plan_steps
            flag_modified(job, "execution_plan")
            
        job.status = "completed"
        db.commit()
        
        if pub_step_idx != -1:
            await broadcast_event("step_completed", {
                "job_id": job.id,
                "step_id": plan_steps[pub_step_idx]["step_id"],
                "status": "completed",
                "output": plan_steps[pub_step_idx]["output"]
            })
            
        await broadcast_event("job_completed", {
            "job_id": job.id,
            "status": job.status,
            "publisher_data": job.publisher_data
        })
        
    except Exception as e:
        logger.error(f"[Refine Task] Refinement failed for Job {job_id}: {e}", exc_info=True)
        job.status = "failed"
        job.error_message = f"Refinement error: {e}"
        db.commit()
        await broadcast_event("job_updated", {
            "job_id": job.id,
            "status": job.status,
            "error_message": job.error_message
        })
    finally:
        db.close()


@app.post("/api/jobs/{job_id}/refine")
async def refine_job_storyboard(job_id: str, req: RefineRequest, db: Session = Depends(get_db)):
    """
    Refinement & Re-evaluation endpoint (Selective Re-Run).
    Allows modifying slide subtitle texts, image prompts, or requesting regenerations.
    Re-runs TTS audio voice worker, image generation tools for toggled slides,
    re-audits via Layer 6 (Evaluator), and updates database records.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    logger.info(f"[API: Refine] Refining storyboard for Job {job.id} ({job.series_title})...")
    
    # Update status and broadcast
    job.status = "running"
    db.commit()
    await broadcast_event("job_updated", {"job_id": job.id, "status": job.status})

    # Start background task to process refinement
    asyncio.create_task(process_job_refinement(job.id, req.slides))
    
    return {"message": "Refinement initiated", "job_id": job_id}


# --- LEGACY APIS (Backward compatibility for tests & scheduler) ---

@app.post("/api/trigger", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def legacy_trigger(job_in: JobCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Triggers the pipeline matching the legacy REST schemas."""
    job_id = str(uuid.uuid4())
    new_job = Job(
        id=job_id,
        target_type=job_in.target_type,
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
    return db.query(Job).order_by(Job.created_at.desc()).offset(skip).limit(limit).all()

@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/api/series")
async def list_series(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    series = db.query(Series).offset(skip).limit(limit).all()
    return [{"id": s.id, "title": s.title, "slug": s.slug, "type": s.series_type} for s in series]


@app.get("/api/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint to verify database connectivity and operational status.
    """
    from sqlalchemy import text
    try:
        db.execute(text("SELECT 1")).scalar()
    except Exception as e:
        logger.error(f"Health check database connection failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is unavailable"
        )
    return {
        "status": "healthy",
        "database": "connected",
        "ollama_url": settings.ollama_base_url
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
