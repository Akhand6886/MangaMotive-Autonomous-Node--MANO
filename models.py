"""
SQLAlchemy ORM Models for the Intelligence Harness.

Defines database schema for Series, Episodes, Articles, Reviews,
Jobs (pipeline execution state), and ProjectMemory (editorial preferences).
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base


def _utcnow():
    """Returns timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)

class Series(Base):
    """
    Represents an Anime, Manga, or Manhwa series tracked by the agent.
    Acts as the local source of truth to avoid duplicate ingestions.
    """
    __tablename__ = "series"

    id = Column(String, primary_key=True, index=True, comment="Contentful SysID or local UUID")
    title = Column(String, index=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    contentful_id = Column(String, unique=True, index=True, nullable=True)
    series_type = Column(String, default="animeSeries", comment="animeSeries, mangaSeries, manhwaSeries")
    metadata_payload = Column(JSON, default=dict, comment="Cached raw metadata from APIs")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    episodes = relationship("Episode", back_populates="series", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="series", cascade="all, delete-orphan")
    articles = relationship("Article", back_populates="series", cascade="all, delete-orphan")


class Episode(Base):
    """
    Represents an Episode Summary entry in Contentful.
    """
    __tablename__ = "episodes"

    id = Column(String, primary_key=True, index=True)
    series_id = Column(String, ForeignKey("series.id"), nullable=False)
    episode_number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    contentful_id = Column(String, unique=True, index=True, nullable=True)
    release_date = Column(String, nullable=True)
    summary_rich_text = Column(JSON, nullable=True, comment="Contentful Rich Text structure")
    key_moments_rich_text = Column(JSON, nullable=True)
    personal_thoughts_rich_text = Column(JSON, nullable=True)
    rating = Column(Float, nullable=True)
    arc = Column(String, nullable=True)
    thumbnail_asset_id = Column(String, nullable=True)
    impactful_lines = Column(JSON, default=list, comment="Array of up to 3 impactful quote strings")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    series = relationship("Series", back_populates="episodes")


class Article(Base):
    """
    Represents a Blog Post / Editorial Article in Contentful.
    """
    __tablename__ = "articles"

    id = Column(String, primary_key=True, index=True)
    series_id = Column(String, ForeignKey("series.id"), nullable=True)
    title = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    contentful_id = Column(String, unique=True, index=True, nullable=True)
    publish_date = Column(String, nullable=True)
    excerpt = Column(Text, nullable=True)
    body_rich_text = Column(JSON, nullable=True, comment="Contentful Rich Text structure")
    tags = Column(JSON, default=list)
    categories = Column(JSON, default=list)
    cover_image_asset_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    series = relationship("Series", back_populates="articles")


class Review(Base):
    """
    Represents a Manga/Anime Review entry in Contentful.
    """
    __tablename__ = "reviews"

    id = Column(String, primary_key=True, index=True)
    series_id = Column(String, ForeignKey("series.id"), nullable=False)
    title = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    contentful_id = Column(String, unique=True, index=True, nullable=True)
    score = Column(Integer, nullable=False)
    positive_summary = Column(String, nullable=True)
    negative_summary = Column(String, nullable=True)
    verdict = Column(String, nullable=True)
    review_body_rich_text = Column(JSON, nullable=True, comment="Contentful Rich Text structure")
    media_asset_ids = Column(JSON, default=list)
    published_date = Column(String, nullable=True)
    seo_title = Column(String, nullable=True)
    seo_description = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    series = relationship("Series", back_populates="reviews")


class Job(Base):
    """
    Represents an asynchronous pipeline execution job for the agentic workers.
    Tracks state transitions across the 7 specialized workers.
    """
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True, comment="Job UUID")
    target_type = Column(String, nullable=False, comment="episode_recap, series_review, editorial_blog, youtube_short, general_request")
    series_id = Column(String, nullable=True, comment="Associated Series ID if applicable")
    series_title = Column(String, nullable=False, comment="Series Title for context")
    episode_number = Column(Integer, nullable=True, comment="Episode number if target_type is episode_recap")
    status = Column(String, default="queued", index=True, comment="queued, planning, running, completed, failed")
    
    # Worker payloads & state progression
    collector_data = Column(JSON, default=dict, comment="Output from Data Collector Worker")
    theme_data = Column(JSON, default=dict, comment="Output from Theme Extractor Worker")
    writer_data = Column(JSON, default=dict, comment="Output from Review Writer Worker")
    seo_data = Column(JSON, default=dict, comment="Output from SEO Worker")
    formatter_data = Column(JSON, default=dict, comment="Output from Formatting Worker")
    publisher_data = Column(JSON, default=dict, comment="Final Output from Publishing Worker")
    
    # Intelligence Harness extensions
    structured_task = Column(JSON, default=dict, comment="Parsed request metadata")
    execution_plan = Column(JSON, default=list, comment="List of dynamically generated plan steps")
    evaluations = Column(JSON, default=dict, comment="Factual consistency, style compliance, and engagement score evaluations")
    memory_logs = Column(JSON, default=list, comment="Logs of memories read or written")

    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<Job(id={self.id!r}, status={self.status!r}, series={self.series_title!r})>"


class ProjectMemory(Base):
    """
    Cumulative editorial preference and long-term memory.
    """
    __tablename__ = "project_memory"

    key = Column(String, primary_key=True, index=True, comment="Memory key: preferred_tone, banned_phrases, etc.")
    value = Column(JSON, default=list, comment="JSON array or object storing memory values")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class LLMCache(Base):
    """
    Cache for LLM prompt completions to avoid redundant requests and improve execution speed.
    """
    __tablename__ = "llm_cache"

    prompt_hash = Column(String, primary_key=True, index=True, comment="SHA256 hash of the system prompt and user input")
    prompt = Column(Text, nullable=False, comment="The prompt sent to the LLM")
    response = Column(Text, nullable=False, comment="The cached text response from the LLM")
    created_at = Column(DateTime, default=_utcnow)

