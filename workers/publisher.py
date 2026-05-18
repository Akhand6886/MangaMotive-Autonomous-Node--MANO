import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Job, Review, Article, Episode, Series
from schemas import CollectorOutput, ThemeExtractorOutput, ReviewWriterOutput, SEOWorkerOutput, FormatterOutput, PublisherOutput
from services.contentful_service import contentful_service
from config import settings

logger = logging.getLogger("PublishingWorker")

class PublishingWorker:
    """
    Worker 7: Publishing Worker
    Final automation layer. Uploads media assets, formats Contentful localized payloads,
    publishes to Contentful Management API, and synchronizes state with local SQLite database.
    Usually No AI Needed. Pure API automation.
    """
    async def process(
        self,
        job: Job,
        collector_output: CollectorOutput,
        theme_output: ThemeExtractorOutput,
        writer_output: ReviewWriterOutput,
        seo_output: SEOWorkerOutput,
        formatter_output: FormatterOutput
    ) -> PublisherOutput:
        logger.info(f"[Publisher] Starting publishing workflow for Job {job.id} ({job.target_type})...")

        db: Session = SessionLocal()
        try:
            # 1. Handle Media Assets
            media_url = collector_output.media_url or "https://images.unsplash.com/photo-1541963463532-d68292c34b19"
            asset_title = f"{seo_output.seo_title} Media"
            logger.info(f"[Publisher] Uploading media asset: {media_url}")
            asset_id = await contentful_service.download_and_upload_asset(media_url, asset_title, seo_output.meta_description)

            # 2. Prepare Contentful Fields based on Target Type
            content_type_id = ""
            fields = {}
            local_model_instance = None

            if job.target_type == "series_review":
                content_type_id = "review"
                fields = {
                    "animemangamanhwa": [contentful_service.link_entry(job.series_id)] if job.series_id else [],
                    "title": seo_output.seo_title,
                    "slug": seo_output.slug,
                    "score": writer_output.score,
                    "media": [contentful_service.link_asset(asset_id)],
                    "positive": writer_output.positive_summary,
                    "negative": writer_output.negative_summary,
                    "verdict": writer_output.verdict,
                    "reviewBody": contentful_service.to_rich_text(formatter_output.cleaned_markdown),
                    "publishedDate": datetime.utcnow().isoformat(),
                    "seoTitle": seo_output.seo_title,
                    "seoDescription": seo_output.meta_description
                }

            elif job.target_type == "editorial_blog":
                content_type_id = "blogPost"
                fields = {
                    "title": seo_output.seo_title,
                    "slug": seo_output.slug,
                    "publishDate": datetime.utcnow().isoformat(),
                    "excerpt": formatter_output.excerpt,
                    "body": contentful_service.to_rich_text(formatter_output.cleaned_markdown),
                    "tags": seo_output.tags,
                    "categories": ["Analysis", "Editorial", "Deep Dive"],
                    "animemangareferecne": [contentful_service.link_entry(job.series_id)] if job.series_id else [],
                    "coverImage": contentful_service.link_asset(asset_id)
                }

            elif job.target_type == "episode_recap":
                content_type_id = "episodeSummary"
                lines = writer_output.impactful_lines or ["", "", ""]
                while len(lines) < 3:
                    lines.append("")

                fields = {
                    "anime": contentful_service.link_entry(job.series_id) if job.series_id else None,
                    "episodeNumber": job.episode_number or 1,
                    "title": seo_output.seo_title,
                    "slug": seo_output.slug,
                    "releaseDate": datetime.utcnow().isoformat(),
                    "summary": contentful_service.to_rich_text(collector_output.summary),
                    "keyMoments": contentful_service.to_rich_text(formatter_output.cleaned_markdown),
                    "personalThoughts": contentful_service.to_rich_text(writer_output.verdict),
                    "rating": float(writer_output.score),
                    "arc": theme_output.main_theme,
                    "thumbnail": contentful_service.link_asset(asset_id),
                    "impactfulLine1": lines[0],
                    "impactfulLine2": lines[1],
                    "impactfulLine3": lines[2]
                }

            # Clean up None values
            fields = {k: v for k, v in fields.items() if v is not None}

            # 3. Publish to Contentful Management API
            logger.info(f"[Publisher] Upserting entry to Contentful ({content_type_id})...")
            published_entry = await contentful_service.upsert_entry(content_type_id, fields)
            entry_sys_id = published_entry["sys"]["id"]

            # 4. Synchronize with local SQLite database
            if job.target_type == "series_review":
                local_model_instance = Review(
                    id=entry_sys_id,
                    series_id=job.series_id or "unlinked",
                    title=seo_output.seo_title,
                    slug=seo_output.slug,
                    contentful_id=entry_sys_id,
                    score=writer_output.score,
                    positive_summary=writer_output.positive_summary,
                    negative_summary=writer_output.negative_summary,
                    verdict=writer_output.verdict,
                    review_body_rich_text=fields.get("reviewBody"),
                    media_asset_ids=[asset_id],
                    published_date=fields.get("publishedDate"),
                    seo_title=seo_output.seo_title,
                    seo_description=seo_output.meta_description
                )
                db.merge(local_model_instance)

            elif job.target_type == "editorial_blog":
                local_model_instance = Article(
                    id=entry_sys_id,
                    series_id=job.series_id,
                    title=seo_output.seo_title,
                    slug=seo_output.slug,
                    contentful_id=entry_sys_id,
                    publish_date=fields.get("publishDate"),
                    excerpt=formatter_output.excerpt,
                    body_rich_text=fields.get("body"),
                    tags=seo_output.tags,
                    categories=fields.get("categories"),
                    cover_image_asset_id=asset_id
                )
                db.merge(local_model_instance)

            elif job.target_type == "episode_recap":
                local_model_instance = Episode(
                    id=entry_sys_id,
                    series_id=job.series_id or "unlinked",
                    episode_number=job.episode_number or 1,
                    title=seo_output.seo_title,
                    slug=seo_output.slug,
                    contentful_id=entry_sys_id,
                    release_date=fields.get("releaseDate"),
                    summary_rich_text=fields.get("summary"),
                    key_moments_rich_text=fields.get("keyMoments"),
                    personal_thoughts_rich_text=fields.get("personalThoughts"),
                    rating=float(writer_output.score),
                    arc=theme_output.main_theme,
                    thumbnail_asset_id=asset_id,
                    impactful_lines=writer_output.impactful_lines
                )
                db.merge(local_model_instance)

            db.commit()
            logger.info(f"[Publisher] Successfully published entry {entry_sys_id} and synchronized local SQLite DB.")

            return PublisherOutput(
                contentful_entry_id=entry_sys_id,
                published_url=f"https://app.contentful.com/spaces/{settings.contentful_space_id}/entries/{entry_sys_id}",
                status="DryRun" if settings.dry_run else "Published",
                published_at=datetime.utcnow().isoformat()
            )

        except Exception as e:
            logger.error(f"[Publisher] Error during publishing workflow: {e}")
            db.rollback()
            raise e
        finally:
            db.close()

publishing_worker = PublishingWorker()
