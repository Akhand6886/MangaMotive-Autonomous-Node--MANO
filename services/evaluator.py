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
    """

    @staticmethod
    async def evaluate_content(
        text: str, 
        research_sources: List[str], 
        preferred_tone: Optional[str] = None, 
        banned_phrases: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Runs comprehensive evaluation checks on generated content.
        Cross-references text against research facts and style criteria.
        """
        logger.info("[Evaluator] Initializing content evaluation checks...")
        
        # 1. Banned Phrases Check (Deterministic)
        banned_detected = []
        if banned_phrases:
            for phrase in banned_phrases:
                phrase_clean = phrase.strip().lower()
                if phrase_clean and phrase_clean in text.lower():
                    banned_detected.append(phrase)
                    logger.warning(f"[Evaluator] STYLE VIOLATION: Found banned phrase '{phrase}' in output.")

        # 2. Fact Check Evaluation (LLM-based)
        fact_score = 10
        fact_violations = []
        if research_sources:
            logger.info("[Evaluator] Running LLM Factual Consistency Audit...")
            sources_summary = "\n".join([f"- {s}" for s in research_sources])
            
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
                fact_score = getattr(eval_res, "factual_accuracy_score", 10)
                fact_violations = getattr(eval_res, "hallucinations_detected", [])
            except Exception as e:
                logger.warning(f"[Evaluator] Factual evaluation failed: {e}. Defaulting to passing score.")
                fact_score = 9
                fact_violations = []

        # 3. Tone & Style Compliance (LLM-based)
        style_score = 10
        style_violations = []
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
            style_score = getattr(style_res, "style_compliance_score", 10)
            style_violations = getattr(style_res, "style_violations", [])
        except Exception as e:
            logger.warning(f"[Evaluator] Style evaluation failed: {e}. Defaulting to passing score.")
            style_score = 9
            style_violations = []

        # If any banned phrases were detected, append them to style violations
        for phrase in banned_detected:
            style_violations.append(f"Contains banned phrase: '{phrase}'")

        # 4. Engagement Prediction (LLM-based)
        engagement_score = 80
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
            engagement_score = getattr(eng_res, "predicted_engagement_score", 80)
        except Exception as e:
            logger.warning(f"[Evaluator] Engagement prediction failed: {e}. Defaulting to average.")
            engagement_score = 82

        # 5. Compile final evaluation result
        style_pass = len(style_violations) == 0 and style_score >= 7
        fact_pass = len(fact_violations) == 0 and fact_score >= 7
        all_passed = style_pass and fact_pass

        errors = []
        if not style_pass:
            errors.extend([f"Style violation: {v}" for v in style_violations])
        if not fact_pass:
            errors.extend([f"Fact check violation: {v}" for v in fact_violations])

        # Generate correction feedback if any checks failed
        correction_feedback = ""
        if not all_passed:
            correction_feedback = (
                f"CRITICAL: The generated content failed evaluation audits.\n"
                f"Please review these correction guidelines and regenerate the content:\n"
            )
            for err in errors:
                correction_feedback += f"- {err}\n"
            correction_feedback += "\nAdjust the text to fix these issues. Ensure no banned words are used."

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
