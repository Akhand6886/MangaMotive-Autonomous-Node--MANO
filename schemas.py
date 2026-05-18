from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- JOB SCHEMAS ---

class JobBase(BaseModel):
    target_type: str = Field(..., description="episode_recap, series_review, editorial_blog")
    series_id: Optional[str] = Field(None, description="Contentful SysID or local UUID of Series")
    series_title: str = Field(..., description="Name of the anime/manga series")
    episode_number: Optional[int] = Field(None, description="Episode number if target_type is episode_recap")

class JobCreate(JobBase):
    pass

class JobResponse(JobBase):
    id: str
    status: str
    collector_data: Dict[str, Any]
    theme_data: Dict[str, Any]
    writer_data: Dict[str, Any]
    seo_data: Dict[str, Any]
    formatter_data: Dict[str, Any]
    publisher_data: Dict[str, Any]
    error_message: Optional[str] = None
    retry_count: int
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
