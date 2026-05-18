from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base

class Series(Base):
    """
    Represents an Anime, Manga, or Manhwa series tracked by the agent.
    Acts as the local source of truth to avoid duplicate ingestions.
    """
    __tablename__ = "series"

    id = Column(String, primary_key=True, index=True, description="Contentful SysID or local UUID")
    title = Column(String, index=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    contentful_id = Column(String, unique=True, index=True, nullable=True)
    series_type = Column(String, default="animeSeries", description="animeSeries, mangaSeries, manhwaSeries")
    metadata_payload = Column(JSON, default={}, description="Cached raw metadata from APIs")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    summary_rich_text = Column(JSON, nullable=True, description="Contentful Rich Text structure")
    key_moments_rich_text = Column(JSON, nullable=True)
    personal_thoughts_rich_text = Column(JSON, nullable=True)
    rating = Column(Float, nullable=True)
    arc = Column(String, nullable=True)
    thumbnail_asset_id = Column(String, nullable=True)
    impactful_lines = Column(JSON, default=[], description="Array of up to 3 impactful quote strings")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    body_rich_text = Column(JSON, nullable=True, description="Contentful Rich Text structure")
    tags = Column(JSON, default=[])
    categories = Column(JSON, default=[])
    cover_image_asset_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    review_body_rich_text = Column(JSON, nullable=True, description="Contentful Rich Text structure")
    media_asset_ids = Column(JSON, default=[])
    published_date = Column(String, nullable=True)
    seo_title = Column(String, nullable=True)
    seo_description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    series = relationship("Series", back_populates="reviews")


class Job(Base):
    """
    Represents an asynchronous pipeline execution job for the agentic workers.
    Tracks state transitions across the 7 specialized workers.
    """
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True, description="Job UUID")
    target_type = Column(String, nullable=False, description="episode_recap, series_review, editorial_blog")
    series_id = Column(String, nullable=True, description="Associated Series ID if applicable")
    series_title = Column(String, nullable=False, description="Series Title for context")
    episode_number = Column(Integer, nullable=True, description="Episode number if target_type is episode_recap")
    status = Column(String, default="queued", index=True, description="queued, collecting, extracting, writing, seo, formatting, publishing, completed, failed")
    
    # Worker payloads & state progression
    collector_data = Column(JSON, default={}, description="Output from Data Collector Worker")
    theme_data = Column(JSON, default={}, description="Output from Theme Extractor Worker")
    writer_data = Column(JSON, default={}, description="Output from Review Writer Worker")
    seo_data = Column(JSON, default={}, description="Output from SEO Worker")
    formatter_data = Column(JSON, default={}, description="Output from Formatting Worker")
    publisher_data = Column(JSON, default={}, description="Final Output from Publishing Worker")
    
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
