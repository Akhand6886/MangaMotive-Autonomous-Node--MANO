import logging
from typing import Dict, Any
from schemas import StructuredTask, ExecutionPlan, ExecutionStep
from services.ollama_service import ollama_service

logger = logging.getLogger("ExecutivePlanner")

class ExecutivePlanner:
    """
    Executive Planner / Executive Cortex (Layer 2).
    Analyzes structured tasks, decomposes them into worker tasks,
    determines the list of execution steps, and allocates worker agents.
    """

    async def generate_plan(self, task: StructuredTask) -> ExecutionPlan:
        logger.info(f"[Planner] Creating execution plan for task topic: '{task.topic}' on platform: '{task.target_platform}'")

        prompt = (
            f"You are the Executive Planner of the MangaMotive Intelligence Harness.\n"
            f"Your job is to plan the complete work pipeline to fulfill the following structured task:\n\n"
            f"--- STRUCTURED TASK ---\n"
            f"- Topic: {task.topic}\n"
            f"- Style/Tone: {task.style}\n"
            f"- Target Platform: {task.target_platform}\n"
            f"- Length/Duration: {task.duration}\n"
            f"- Required Deliverables: {', '.join(task.assets_needed)}\n\n"
            f"Formulate a detailed, step-by-step Execution Plan. Allocate steps to the following workers:\n"
            f"- 'research_worker': Gathers facts, plot synopsis, transcript lines, and references.\n"
            f"- 'script_writer': Writes narration script or articles, incorporating project style and tone.\n"
            f"- 'lore_checker': Audits script/text for anime lore accuracy and continuity.\n"
            f"- 'thumbnail_strategist': Ideates cover styles and generates thumbnail/image prompts.\n"
            f"- 'voice_timing': Handles TTS audio generation and synchronizes voice timings.\n"
            f"- 'style_consistency': Performs formatting checks, SEO tags, metadata, and slug validation.\n"
            f"- 'fact_verifier': Conducts factual audits against collected research to prevent hallucinations.\n"
            f"- 'publishing_worker': Uploads visual assets, registers entries, and publishes the final package.\n\n"
            f"Each step must contain a unique 'step_id' (e.g. step_1, step_2), a 'name' (short title), "
            f"a target 'worker', and a detail 'description' of what that worker should achieve.\n"
            f"Ensure the sequence flows logically (e.g. research must occur before script writing; fact verification must occur before publishing)."
        )

        plan = await ollama_service.generate_structured(
            prompt=prompt,
            schema_class=ExecutionPlan
        )

        logger.info(f"[Planner] Generated execution plan: '{plan.plan_title}' with {len(plan.steps)} steps.")
        return plan

executive_planner = ExecutivePlanner()
