"""
Worker Tool Layer (Layer 5).

Provides agents with programmatic tool capabilities: web search,
image generation, text-to-speech, database memory lookup, and video assembly.
All tools are designed with simulation fallbacks for offline operation.
"""

import logging
import asyncio
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Series, Episode, Review, ProjectMemory
from services.ollama_service import ollama_service

logger = logging.getLogger("ToolLayer")

class ToolLayer:
    """
    Worker Tool Layer (Layer 5).
    Provides agents with programmatic capabilities to gather facts,
    generate visuals, synthesize audio, search database memory, and assemble videos.

    All methods are stateless static/class methods designed for concurrent use.
    """

    # --- Class-Level Constants ---

    # Local anime encyclopedia for offline search fallback
    _KNOWLEDGE_BASE: Dict[str, List[str]] = {
        "solo leveling": [
            "Solo Leveling features Sung Jinwoo as the protagonist, who starts as the weakest E-rank hunter.",
            "The Double Dungeon incident in Chapter 1 is the catalyst for Jinwoo receiving the System.",
            "Shadow Monarch is the class Jinwoo unlocks after clearing the Job Change Quest.",
            "Solo Leveling Episode 5 highlights Jinwoo's raid with Hwang Dongsoo's strike squad.",
            "Key characters include Cha Hae-in, Yoo Jinho, and Go Gunhee."
        ],
        "one piece": [
            "One Piece features Monkey D. Luffy, who aims to become the Pirate King.",
            "Egghead Island is the futuristic island of Dr. Vegapunk, where Luffy faces CP0 and Admiral Kizaru.",
            "Luffy unlocks Gear 5 during the Wano Country Arc, fighting Kaido.",
            "The Straw Hat Pirates consist of Zoro, Nami, Usopp, Sanji, Chopper, Robin, Franky, Brook, and Jinbe.",
            "One Piece Episode 1129 features Kizaru's intense clash with the Straw Hat crew."
        ],
        "jujutsu kaisen": [
            "Jujutsu Kaisen features Yuji Itadori, who consumes the fingers of Ryomen Sukuna.",
            "The Shibuya Incident is a major arc where Gojo Satoru is sealed in the Prison Realm.",
            "Megumi Fushiguro uses the Ten Shadows Technique to summon Divine Dogs and Mahoraga.",
            "Jujutsu Kaisen Episode 47 covers the climax of the Shibuya Incident and Itadori vs Mahito.",
            "Ryomen Sukuna is the King of Curses who takes over Itadori's body."
        ],
        "demon slayer": [
            "Demon Slayer (Kimetsu no Yaiba) features Tanjiro Kamado, who seeks to cure his demon sister Nezuko.",
            "Tanjiro uses Hinokami Kagura (Dance of the Fire God), inherited from his father.",
            "The Hashira are the elite swordsmen of the Demon Slayer Corps, including Giyu Tomioka and Kyojuro Rengoku.",
            "Season 4 features the Hashira Training Arc, preparing the corps for the final battle with Muzan Kibutsuji.",
            "Muzan Kibutsuji is the first and most powerful demon, creator of all other demons."
        ],
        "attack on titan": [
            "Attack on Titan features Eren Yeager, Mikasa Ackerman, and Armin Arlert.",
            "The Rumbling is Eren's catastrophic plan to destroy all life outside Paradis Island using Wall Titans.",
            "Eren possesses the Attack Titan, Founding Titan, and War Hammer Titan.",
            "Levi Ackerman is humanity's strongest soldier, captain of the Special Operations Squad.",
            "Paradis Island is surrounded by three massive walls: Maria, Rose, and Sheena."
        ]
    }

    # Curated Unsplash image URLs mapped by keyword
    _IMAGE_KEYWORDS: Dict[str, str] = {
        "solo leveling": "https://images.unsplash.com/photo-1578632767115-351597cf2477?w=800&auto=format&fit=crop&q=80",
        "one piece": "https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?w=800&auto=format&fit=crop&q=80",
        "fight": "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=800&auto=format&fit=crop&q=80",
        "dark": "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=800&auto=format&fit=crop&q=80",
        "cyberpunk": "https://images.unsplash.com/photo-1578894381163-e72c17f2d45f?w=800&auto=format&fit=crop&q=80",
        "gaming": "https://images.unsplash.com/photo-1538481199705-c710c4e965fc?w=800&auto=format&fit=crop&q=80",
        "anime": "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=800&auto=format&fit=crop&q=80"
    }

    _DEFAULT_IMAGE_URL = "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=80"
    _SAMPLE_AUDIO_URL = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"
    _SAMPLE_VIDEO_URL = "https://assets.mixkit.co/videos/preview/mixkit-stars-in-space-background-1611-large.mp4"

    # Average reading speed: ~150 words per minute = 2.5 words/second
    _WORDS_PER_SECOND = 2.5

    @staticmethod
    async def web_search(query: str) -> List[str]:
        """
        Simulated web search tool (Google/DuckDuckGo/MyAnimeList).
        Checks local knowledge base first, then falls back to LLM synthesis.

        Args:
            query: Search query string.

        Returns:
            List of factual snippet strings (up to 5).
        """
        logger.info(f"[Tool: Web Search] Searching for: '{query}'")
        await asyncio.sleep(0.5)  # Simulate network latency
        
        query_lower = query.lower()

        # Check if query matches any known franchise
        for key, facts in ToolLayer._KNOWLEDGE_BASE.items():
            if key in query_lower:
                logger.info(f"[Tool: Web Search] Found local knowledge database entry for '{key}'.")
                return facts

        # Dynamic fallback: Use LLM to synthesize factual snippets if offline
        logger.info(f"[Tool: Web Search] No local database match. Synthesizing research facts dynamically.")
        prompt = (
            f"Generate a list of 5 brief, highly accurate, bulleted facts about the following search topic:\n"
            f"Topic: {query}\n\n"
            f"Focus on names of characters, events, lore, and release facts. Keep each bullet under 25 words."
        )
        try:
            facts_text = await ollama_service.generate_text(prompt)
            lines = [line.strip().lstrip("- ").lstrip("* ") for line in facts_text.split("\n") if line.strip()]
            return [line for line in lines if len(line) > 10][:5]
        except Exception:
            return [
                f"Fact 1: Search query '{query}' relates to major animated and printed media.",
                f"Fact 2: Main characters and conflicts are central to current fan discussions.",
                f"Fact 3: Recent episodes have generated massive engagement across streaming sites.",
                f"Fact 4: Production elements like music scoring and direction have received high scores.",
                f"Fact 5: Lore databases are tracking plot changes compared to the manga canon."
            ]

    @staticmethod
    async def generate_image(prompt: str) -> str:
        """
        Simulated Image Generation Tool (DALL-E 3 / Stable Diffusion style).
        Returns a curated Unsplash image URL matched to prompt keywords.

        Args:
            prompt: Descriptive text for the desired image.

        Returns:
            URL string of the generated/selected image.
        """
        logger.info(f"[Tool: Image Gen] Generating image for prompt: '{prompt}'")
        await asyncio.sleep(0.8)  # Simulate generation latency

        prompt_lower = prompt.lower()
        
        # Match against curated keyword-to-URL map
        for kw, url in ToolLayer._IMAGE_KEYWORDS.items():
            if kw in prompt_lower:
                logger.info(f"[Tool: Image Gen] Found matching asset for keyword '{kw}': {url}")
                return url

        # Default fallback
        logger.info(f"[Tool: Image Gen] Returning default aesthetic backdrop: {ToolLayer._DEFAULT_IMAGE_URL}")
        return ToolLayer._DEFAULT_IMAGE_URL

    @staticmethod
    async def text_to_speech(text: str) -> Dict[str, Any]:
        """
        Simulated TTS Audio Engine.
        Synthesizes text input into a mock narration file, calculating speech duration.

        Args:
            text: Script text to synthesize.

        Returns:
            Dict with audio_url, duration_seconds, and narration_text.
        """
        logger.info(f"[Tool: TTS] Synthesizing speech for {len(text)} characters...")
        await asyncio.sleep(0.4)
        
        word_count = len(text.split())
        estimated_duration_seconds = max(2, int(word_count / ToolLayer._WORDS_PER_SECOND))
        
        clean_preview = text[:40] + "..." if len(text) > 40 else text
        
        logger.info(f"[Tool: TTS] Completed. Generated audio duration: {estimated_duration_seconds}s. Preview: '{clean_preview}'")
        return {
            "audio_url": ToolLayer._SAMPLE_AUDIO_URL,
            "duration_seconds": estimated_duration_seconds,
            "narration_text": text
        }

    @staticmethod
    def database_lookup(query: str) -> Dict[str, Any]:
        """
        Database Memory Query Tool.
        Searches SQLite project memories, series records, and jobs.
        """
        logger.info(f"[Tool: DB Lookup] Querying local database for: '{query}'")
        db: Session = SessionLocal()
        try:
            query_lower = query.lower()
            
            # 1. Search series table
            series = db.query(Series).filter(Series.title.ilike(f"%{query_lower}%")).all()
            series_list = [{"id": s.id, "title": s.title, "slug": s.slug, "type": s.series_type} for s in series]
            
            # 2. Search project memory settings
            memories = db.query(ProjectMemory).all()
            memory_dict = {m.key: m.value for m in memories}
            
            logger.info(f"[Tool: DB Lookup] Found {len(series_list)} matching series and {len(memory_dict)} memory keys.")
            return {
                "matched_series": series_list,
                "project_preferences": memory_dict
            }
        except Exception as e:
            logger.error(f"[Tool: DB Lookup] Error during DB lookup: {e}")
            return {"error": str(e)}
        finally:
            db.close()

    @staticmethod
    async def ffmpeg_assemble(script: str, audio_url: str, image_urls: List[str]) -> Dict[str, Any]:
        """
        Simulated Video Assembler & FFmpeg pipeline.
        Compiles narration script, TTS audio, and visual thumbnails into a storyboard.

        Args:
            script: Narration script text to split into slides.
            audio_url: URL of the synthesized audio track.
            image_urls: List of image URLs to cycle through for slides.

        Returns:
            Dict with video_url, duration_seconds, slides_count, and storyboard.
        """
        logger.info(f"[Tool: FFmpeg] Compiling narration track and {len(image_urls)} slides into high-retention video short.")
        await asyncio.sleep(1.0)  # Simulate video compilation encoding

        # Extract storyboard slides based on sentence boundaries
        try:
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', script) if s.strip()]
        except re.error:
            # Fallback: split on periods if regex fails
            sentences = [s.strip() for s in script.split(".") if s.strip()]

        if not sentences:
            sentences = [script[:200] or "Narration content"]

        fallback_image = ToolLayer._DEFAULT_IMAGE_URL
        slides = []
        for i, sent in enumerate(sentences):
            img_index = i % len(image_urls) if image_urls else 0
            slides.append({
                "slide_number": i + 1,
                "timestamp": f"00:{i*5:02d}",
                "text": sent,
                "image_url": image_urls[img_index] if image_urls else fallback_image
            })

        logger.info(f"[Tool: FFmpeg] Video compilation completed. Total slides: {len(slides)}")
        return {
            "video_url": ToolLayer._SAMPLE_VIDEO_URL,
            "duration_seconds": len(slides) * 5,
            "slides_count": len(slides),
            "storyboard": slides
        }
