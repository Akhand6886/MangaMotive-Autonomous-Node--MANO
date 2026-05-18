import httpx
import logging
from typing import Dict, Any, Optional
from config import settings

logger = logging.getLogger("AnimeScheduleService")

class AnimeScheduleService:
    """
    Service client for AnimeSchedule.net API v3.
    Fetches daily/weekly timetables to trigger autonomous recap jobs.
    """
    def __init__(self):
        self.base_url = "https://animeschedule.net/api/v3"
        self.api_key = settings.animeschedule_api_key

    async def get_timetable(self, air_type: str = "sub", params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetches the weekly timetable for airing anime.
        """
        url = f"{self.base_url}/timetables/{air_type}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # If placeholder API key is used, provide fallback mock data for testing/dry-run
        if not self.api_key or self.api_key == "your_api_key_here":
            logger.warning("[AnimeSchedule] Using placeholder API key. Returning mock timetable data.")
            return {
                "items": [
                    {
                        "id": "mock-one-piece",
                        "title": "One Piece",
                        "slug": "one-piece",
                        "episodeNumber": 1129,
                        "airingDate": "2026-05-18T12:00:00Z",
                        "synopsis": "Luffy and his crew face off against Kizaru on Egghead Island in a climactic clash of powers.",
                        "imageVersionRoute": "https://images.unsplash.com/photo-1541963463532-d68292c34b19"
                    },
                    {
                        "id": "mock-jjk",
                        "title": "Jujutsu Kaisen",
                        "slug": "jujutsu-kaisen",
                        "episodeNumber": 47,
                        "airingDate": "2026-05-18T14:30:00Z",
                        "synopsis": "The Shibuya Incident reaches its devastating conclusion as Yuji Itadori confronts Mahito.",
                        "imageVersionRoute": "https://images.unsplash.com/photo-1541963463532-d68292c34b19"
                    }
                ]
            }

        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"[AnimeSchedule] Fetching timetable from {url}")
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"[AnimeSchedule] API Error: {e}")
                raise RuntimeError(f"AnimeSchedule API Error: {e}")

anime_schedule_service = AnimeScheduleService()
