"""
Pydantic Schemas for API request/response serialization and worker structured output.

Defines validation models for the REST API, worker output schemas,
and Intelligence Harness task/plan schemas.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- JOB SCHEMAS ---

class JobBase(BaseModel):
    """Base schema for job creation with required series metadata."""
    target_type: str = Field(..., description="episode_recap, series_review, editorial_blog")
    series_id: Optional[str] = Field(None, description="Contentful SysID or local UUID of Series")
    series_title: str = Field(..., min_length=1, description="Name of the anime/manga series")
    episode_number: Optional[int] = Field(None, ge=1, description="Episode number if target_type is episode_recap")

class JobCreate(JobBase):
    pass

class JobResponse(JobBase):
    """Full job response schema including all worker outputs and harness extensions."""
    id: str
    status: str
    collector_data: Dict[str, Any]
    theme_data: Dict[str, Any]
    writer_data: Dict[str, Any]
    seo_data: Dict[str, Any]
    formatter_data: Dict[str, Any]
    publisher_data: Dict[str, Any]
    
    # Intelligence Harness extensions
    structured_task: Optional[Dict[str, Any]] = None
    execution_plan: Optional[List[Dict[str, Any]]] = None
    evaluations: Optional[Dict[str, Any]] = None
    memory_logs: Optional[List[str]] = None

    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- WORKER STRUCTURED OUTPUT SCHEMAS ---

class CollectorOutput(BaseModel):
    """Output from Data Collector Worker"""
    title: str = Field(..., description="Full title of the target episode or series")
    series_id: Optional[str] = Field(None, description="Series identifier")
    episode_number: Optional[int] = Field(None, description="Episode number if applicable")
    summary: str = Field(..., description="Raw synopsis or plot summary fetched from APIs")
    subtitles: str = Field(..., description="Cleaned transcript chunks or subtitle text")
    characters: List[str] = Field(default=[], description="List of major characters involved")
    raw_synopsis: Optional[str] = Field(None, description="Original API synopsis text")
    media_url: Optional[str] = Field(None, description="Cover or thumbnail image URL")


class ThemeExtractorOutput(BaseModel):
    """Output from Theme Extractor Worker (Small LLM)"""
    main_theme: str = Field(..., description="Primary emotional or narrative theme identified")
    tone: str = Field(..., description="Overall tone (e.g., intense, melancholic, comedic)")
    strengths: List[str] = Field(..., description="Key storytelling or production strengths")
    weaknesses: List[str] = Field(..., description="Noted pacing flaws or narrative weaknesses")
    standout_moments: List[str] = Field(..., description="Bullet points of standout scenes")
    pacing_analysis: str = Field(..., description="Brief analysis of episode/series pacing")
    narrative_direction: str = Field(..., description="Summary of where the plot is heading")


class ReviewWriterOutput(BaseModel):
    """Output from Review Writer Worker (Small LLM)"""
    draft_title: str = Field(..., description="Engaging working title for the article/review")
    score: int = Field(..., ge=1, le=10, description="Numerical score from 1 to 10")
    positive_summary: str = Field(..., description="Short summary of pros/successes")
    negative_summary: str = Field(..., description="Short summary of cons/failures")
    verdict: str = Field(..., description="One-sentence final judgment")
    review_body_markdown: str = Field(..., description="Detailed multi-paragraph body text in markdown")
    impactful_lines: List[str] = Field(default=[], description="Up to 3 memorable quotes")


class SEOWorkerOutput(BaseModel):
    """Output from SEO Worker (Small LLM)"""
    seo_title: str = Field(..., description="SEO-optimized title (under 60 characters)")
    slug: str = Field(..., description="URL-friendly slug (kebab-case)")
    meta_description: str = Field(..., description="Compelling meta description (under 160 characters)")
    keywords: List[str] = Field(..., description="List of high-value SEO keywords")
    tags: List[str] = Field(..., description="List of category tags for CMS classification")


class FormatterOutput(BaseModel):
    """Output from Formatting Worker (Pure Python Deterministic)"""
    cleaned_markdown: str = Field(..., description="Fully cleaned and structured markdown body")
    validated_title: str = Field(..., description="Final clean title")
    slug: str = Field(..., description="Verified URL slug")
    word_count: int = Field(..., description="Calculated word count")
    excerpt: str = Field(..., description="Extracted 1-2 sentence hook excerpt")
    headings_fixed: bool = Field(..., description="Whether heading hierarchy was normalized")


class PublisherOutput(BaseModel):
    """Output from Publishing Worker"""
    contentful_entry_id: str = Field(..., description="Contentful SysID of the published entry")
    published_url: Optional[str] = Field(None, description="Public URL or API endpoint of entry")
    status: str = Field(..., description="Published status (Published, Draft, DryRun)")
    published_at: str = Field(..., description="ISO timestamp of publishing")


# --- INTELLIGENCE HARNESS SCHEMAS ---

class StructuredTask(BaseModel):
    """Parsed structured task from the Interface Layer."""
    topic: str = Field(..., min_length=1, description="Topic of the task (e.g. Solo Leveling Episode 5)")
    style: str = Field(..., description="Editorial tone or style guidelines (e.g. fast-paced, analytical)")
    target_platform: str = Field(..., description="Target platform (e.g. YouTube Short, TikTok, Editorial Blog, Contentful Recap)")
    duration: str = Field(..., description="Estimated duration or length constraints")
    assets_needed: List[str] = Field(default=[], description="List of assets to generate: Script, Thumbnail, Narration, Video")

class ExecutionStep(BaseModel):
    step_id: str = Field(..., description="Unique step identifier")
    name: str = Field(..., description="Short name of step")
    worker: str = Field(..., description="Worker type (e.g. research_worker, script_writer, fact_verifier)")
    description: str = Field(..., description="Detailed instructions for the worker")

class ExecutionPlan(BaseModel):
    plan_title: str = Field(..., description="Short title of execution plan")
    steps: List[ExecutionStep] = Field(..., description="Ordered list of steps to execute")

from pydantic import BaseModel, Field, field_validator
import re

class HarnessRequest(BaseModel):
    """Raw text request for the Interface Layer parser."""
    prompt: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Raw request string from the user"
    )

    @field_validator("prompt")
    @classmethod
    def sanitize_prompt(cls, v: str) -> str:
        """Sanitizes prompt input by stripping HTML tags and normalizing whitespaces."""
        cleaned = re.sub(r"<[^>]*>", "", v)
        cleaned = " ".join(cleaned.split())
        if not cleaned:
            raise ValueError("Prompt cannot be empty after sanitization")
        return cleaned


class ProjectMemorySchema(BaseModel):
    """Schema for reading/writing editorial preference memory settings."""
    key: str = Field(..., min_length=1, description="Memory identifier (preferred_tone, banned_phrases, style_guide, successful_hooks)")
    value: List[str] = Field(..., description="Array of strings representing memory content")


class SlideEdit(BaseModel):
    """Schema representing an edited slide within a storyboard."""
    slide_number: int = Field(..., description="1-indexed number of the slide")
    start: float = Field(..., description="Start timestamp of the slide in seconds")
    end: float = Field(..., description="End timestamp of the slide in seconds")
    subtitle: str = Field(..., description="Subtitles/script text for the slide")
    image_prompt: Optional[str] = Field(None, description="Image generation prompt for this slide")
    image_url: Optional[str] = Field(None, description="Current image URL of the slide")
    regenerate_image: Optional[bool] = Field(default=False, description="Whether to regenerate the slide's visual asset")


class RefineRequest(BaseModel):
    """Request payload for the selective refinement endpoint."""
    slides: List[SlideEdit] = Field(..., description="List of edited slides to rebuild/re-evaluate")


