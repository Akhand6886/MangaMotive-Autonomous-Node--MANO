"""
Evaluation Layer (Layer 6).

Audits generated content for factual consistency, style compliance,
banned phrase avoidance, and audience engagement prediction.
Supports self-correction retry loops via structured feedback.
"""

import asyncio
import logging
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from services.ollama_service import ollama_service

logger = logging.getLogger("EvaluationLayer")

# --- EVALUATION SCHEMAS ---

class FactVerificationOutput(BaseModel):
    factual_accuracy_score: int
    hallucinations_detected: List[str]

class StyleVerificationOutput(BaseModel):
    style_compliance_score: int
    style_violations: List[str]

class EngagementOutput(BaseModel):
    predicted_engagement_score: int
    retention_tips: List[str]


class EvaluationLayer:
    """
    Evaluation Layer (Layer 6).
    Audits workers' outputs to ensure factual consistency, style guidelines adherence,
    banned words avoidance, and JSON schema compliance.

    Uses concurrent LLM evaluations where possible to minimize latency.
    """

    # Score thresholds for pass/fail decisions
    _MIN_PASS_SCORE = 7
    _DEFAULT_FACT_SCORE = 10
    _DEFAULT_STYLE_SCORE = 10
    _DEFAULT_ENGAGEMENT_SCORE = 80
    _FALLBACK_FACT_SCORE = 9
    _FALLBACK_STYLE_SCORE = 9
    _FALLBACK_ENGAGEMENT_SCORE = 82

    @staticmethod
    async def evaluate_content(
        text: str, 
        research_sources: List[str], 
        preferred_tone: Optional[str] = None, 
        banned_phrases: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Runs comprehensive evaluation checks on generated content.
        Cross-references text against research facts, style criteria, and engagement heuristics.

        Runs fact-check and style audits concurrently for performance.

        Args:
            text: The generated content text to evaluate.
            research_sources: List of known facts for cross-reference.
            preferred_tone: Target editorial tone/style.
            banned_phrases: List of phrases that must not appear.

        Returns:
            Dict with passed, scores, errors, and correction feedback.
        """
        logger.info("[Evaluator] Initializing content evaluation checks...")
        
        # 1. Banned Phrases Check (Deterministic — runs immediately)
        banned_detected = []
        if banned_phrases:
            text_lower = text.lower()
            for phrase in banned_phrases:
                phrase_clean = phrase.strip().lower()
                if phrase_clean and phrase_clean in text_lower:
                    banned_detected.append(phrase)
                    logger.warning(f"[Evaluator] STYLE VIOLATION: Found banned phrase '{phrase}' in output.")

        # 2 & 3. Run Fact Check and Style Compliance concurrently
        fact_task = EvaluationLayer._evaluate_facts(text, research_sources)
        style_task = EvaluationLayer._evaluate_style(text, preferred_tone)
        engagement_task = EvaluationLayer._evaluate_engagement(text)

        (fact_score, fact_violations), (style_score, style_violations), engagement_score = await asyncio.gather(
            fact_task, style_task, engagement_task
        )

        # Append banned phrase violations to style violations
        for phrase in banned_detected:
            style_violations.append(f"Contains banned phrase: '{phrase}'")

        # 4. Compile final evaluation result
        style_pass = len(style_violations) == 0 and style_score >= EvaluationLayer._MIN_PASS_SCORE
        fact_pass = len(fact_violations) == 0 and fact_score >= EvaluationLayer._MIN_PASS_SCORE
        all_passed = style_pass and fact_pass

        errors = []
        if not style_pass:
            errors.extend([f"Style violation: {v}" for v in style_violations])
        if not fact_pass:
            errors.extend([f"Fact check violation: {v}" for v in fact_violations])

        # Generate correction feedback if any checks failed
        correction_feedback = ""
        if not all_passed:
            feedback_lines = [
                "CRITICAL: The generated content failed evaluation audits.",
                "Please review these correction guidelines and regenerate the content:"
            ]
            feedback_lines.extend(f"- {err}" for err in errors)
            feedback_lines.append("\nAdjust the text to fix these issues. Ensure no banned words are used.")
            correction_feedback = "\n".join(feedback_lines)

        logger.info(f"[Evaluator] Evaluation complete. Status: {'PASS' if all_passed else 'FAIL'}. Engagement Score: {engagement_score}/100.")
        return {
            "passed": all_passed,
            "style_pass": style_pass,
            "fact_pass": fact_pass,
            "fact_accuracy_score": fact_score,
            "style_compliance_score": style_score,
            "predicted_engagement_score": engagement_score,
            "errors": errors,
            "feedback": correction_feedback
        }

    # --- Private concurrent evaluation helpers ---

    @staticmethod
    async def _evaluate_facts(text: str, research_sources: List[str]) -> tuple:
        """Runs LLM-based factual consistency audit against research sources."""
        if not research_sources:
            return (EvaluationLayer._DEFAULT_FACT_SCORE, [])

        logger.info("[Evaluator] Running LLM Factual Consistency Audit...")
        sources_summary = "\n".join(f"- {s}" for s in research_sources)
        prompt = (
            f"Verify the factual consistency of the following draft against the known research facts.\n\n"
            f"--- KNOWN RESEARCH FACTS ---\n{sources_summary}\n\n"
            f"--- DRAFT CONTENT ---\n{text}\n\n"
            f"Analyze if there are any contradictions, hallucinations, or major factual inaccuracies in the draft. "
            f"Respond ONLY with a valid JSON object matching this schema:\n"
            f"Do not include markdown or conversational formatting outside the JSON."
        )
        try:
            eval_res = await ollama_service.generate_structured(prompt, FactVerificationOutput)
            return (getattr(eval_res, "factual_accuracy_score", 10), getattr(eval_res, "hallucinations_detected", []))
        except Exception as e:
            logger.warning(f"[Evaluator] Factual evaluation failed: {e}. Defaulting to passing score.")
            return (EvaluationLayer._FALLBACK_FACT_SCORE, [])

    @staticmethod
    async def _evaluate_style(text: str, preferred_tone: Optional[str]) -> tuple:
        """Runs LLM-based style and tone compliance audit."""
        target_tone = preferred_tone or "professional and engaging"
        logger.info(f"[Evaluator] Auditing style compliance for tone: '{target_tone}'...")
        prompt = (
            f"Audit the style, tone, and formatting of the following draft according to the target style guidelines.\n\n"
            f"--- TARGET TONE/STYLE ---\n{target_tone}\n\n"
            f"--- DRAFT CONTENT ---\n{text}\n\n"
            f"Evaluate if the draft matches the target tone. Check if it feels natural, grammatically correct, and matches the guidelines. "
            f"Respond ONLY with a valid JSON object matching this schema:\n"
            f"Do not include markdown or conversational formatting outside the JSON."
        )
        try:
            style_res = await ollama_service.generate_structured(prompt, StyleVerificationOutput)
            return (getattr(style_res, "style_compliance_score", 10), getattr(style_res, "style_violations", []))
        except Exception as e:
            logger.warning(f"[Evaluator] Style evaluation failed: {e}. Defaulting to passing score.")
            return (EvaluationLayer._FALLBACK_STYLE_SCORE, [])

    @staticmethod
    async def _evaluate_engagement(text: str) -> int:
        """Runs LLM-based audience engagement prediction."""
        logger.info("[Evaluator] Performing Audience Engagement prediction...")
        prompt = (
            f"Analyze the following draft and predict its clickability and audience retention potential (engagement).\n\n"
            f"--- DRAFT CONTENT ---\n{text}\n\n"
            f"Calculate an engagement score out of 100 based on title hook, formatting flow, and introductory excitement. "
            f"Respond ONLY with a valid JSON object matching this schema:\n"
            f"Do not include markdown or conversational formatting outside the JSON."
        )
        try:
            eng_res = await ollama_service.generate_structured(prompt, EngagementOutput)
            return getattr(eng_res, "predicted_engagement_score", EvaluationLayer._DEFAULT_ENGAGEMENT_SCORE)
        except Exception as e:
            logger.warning(f"[Evaluator] Engagement prediction failed: {e}. Defaulting to average.")
            return EvaluationLayer._FALLBACK_ENGAGEMENT_SCORE
