import os
import httpx
import logging
import asyncio
from typing import Dict, Any, Optional, List
from config import settings

logger = logging.getLogger("ContentfulService")

class ContentfulService:
    """
    Python SDK wrapper for Contentful Management API (CMA).
    Mirrors the exact functionality and binary upload flow of ContentfulService.js.
    """
    def __init__(self):
        self.token = settings.contentful_management_token
        self.space_id = settings.contentful_space_id
        self.env_id = settings.contentful_environment_id
        self.base_url = f"https://api.contentful.com/spaces/{self.space_id}/environments/{self.env_id}"
        self.upload_url = f"https://upload.contentful.com/spaces/{self.space_id}/uploads"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def to_rich_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Converts plain text or markdown paragraphs into Contentful Rich Text structure."""
        if not text:
            return None
        
        paragraphs = text.split("\n\n")
        content_nodes = []
        for para in paragraphs:
            clean_para = para.strip()
            if clean_para:
                content_nodes.append({
                    "nodeType": "paragraph",
                    "data": {},
                    "content": [{
                        "nodeType": "text",
                        "value": clean_para,
                        "marks": [],
                        "data": {}
                    }]
                })

        return {
            "nodeType": "document",
            "data": {},
            "content": content_nodes
        }

    def link_entry(self, sys_id: str) -> Dict[str, Any]:
        """Creates a Contentful Entry reference link."""
        return {"sys": {"type": "Link", "linkType": "Entry", "id": sys_id}}

    def link_asset(self, sys_id: str) -> Dict[str, Any]:
        """Creates a Contentful Asset reference link."""
        return {"sys": {"type": "Link", "linkType": "Asset", "id": sys_id}}

    async def download_and_upload_asset(self, url: str, title: str, description: str = "") -> str:
        """
        Downloads an image from a remote URL, uploads binary data to Contentful,
        creates an Asset, processes it, and publishes it.
        """
        if settings.dry_run:
            logger.info(f"[DryRun] Mocking asset upload for: {title} ({url})")
            return f"mock_asset_id_{title.lower().replace(' ', '_')}"

        logger.info(f"[Contentful] Downloading image from: {url}")
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            image_bytes = resp.content
            content_type = resp.headers.get("content-type", "image/jpeg")
            file_name = url.split("/")[-1].split("?")[0] or "image.jpg"

        # 1. Upload binary data to Contentful Upload API
        logger.info(f"[Contentful] Uploading binary data ({len(image_bytes)} bytes) to Contentful...")
        upload_headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/octet-stream"
        }
        async with httpx.AsyncClient() as client:
            upload_resp = await client.post(self.upload_url, content=image_bytes, headers=upload_headers)
            upload_resp.raise_for_status()
            upload_data = upload_resp.json()
            upload_id = upload_data["sys"]["id"]

        # 2. Create Asset pointing to Upload
        logger.info(f"[Contentful] Creating Asset '{title}'...")
        asset_payload = {
            "fields": {
                "title": {"en-US": title},
                "description": {"en-US": description},
                "file": {
                    "en-US": {
                        "contentType": content_type,
                        "fileName": file_name,
                        "uploadFrom": {
                            "sys": {"type": "Link", "linkType": "Upload", "id": upload_id}
                        }
                    }
                }
            }
        }
        async with httpx.AsyncClient() as client:
            asset_resp = await client.post(f"{self.base_url}/assets", json=asset_payload, headers=self.headers)
            asset_resp.raise_for_status()
            asset_data = asset_resp.json()
            asset_id = asset_data["sys"]["id"]
            asset_version = asset_data["sys"]["version"]

        # 3. Process Asset for locale
        logger.info(f"[Contentful] Processing Asset '{title}'...")
        process_headers = {**self.headers, "X-Contentful-Version": str(asset_version)}
        async with httpx.AsyncClient() as client:
            proc_resp = await client.put(f"{self.base_url}/assets/{asset_id}/files/en-US/process", headers=process_headers)
            proc_resp.raise_for_status()

        # Wait for processing to complete
        processed = False
        async with httpx.AsyncClient() as client:
            for _ in range(30):
                await asyncio.sleep(1.0)
                check_resp = await client.get(f"{self.base_url}/assets/{asset_id}", headers=self.headers)
                check_resp.raise_for_status()
                check_data = check_resp.json()
                asset_version = check_data["sys"]["version"]
                url_val = check_data.get("fields", {}).get("file", {}).get("en-US", {}).get("url")
                if url_val:
                    processed = True
                    break

        if not processed:
            raise RuntimeError(f"Asset processing timeout for '{title}'")

        # 4. Publish Asset
        logger.info(f"[Contentful] Publishing Asset '{title}'...")
        pub_headers = {**self.headers, "X-Contentful-Version": str(asset_version)}
        async with httpx.AsyncClient() as client:
            pub_resp = await client.put(f"{self.base_url}/assets/{asset_id}/published", headers=pub_headers)
            pub_resp.raise_for_status()
            pub_data = pub_resp.json()
            return pub_data["sys"]["id"]

    async def upsert_entry(self, content_type_id: str, fields: Dict[str, Any], entry_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Creates or updates a Contentful entry and publishes it.
        Automatically localizes fields to 'en-US'.
        """
        if settings.dry_run:
            logger.info(f"[DryRun] Mocking entry upsert for {content_type_id}: {fields.get('title') or fields.get('name')}")
            return {
                "sys": {"id": entry_id or f"mock_{content_type_id}_{fields.get('slug', 'entry')}", "version": 1},
                "fields": fields
            }

        localized_fields = {}
        for key, value in fields.items():
            if value is not None:
                localized_fields[key] = {"en-US": value}

        async with httpx.AsyncClient() as client:
            # Check if entry exists
            target_entry = None
            if entry_id:
                try:
                    get_resp = await client.get(f"{self.base_url}/entries/{entry_id}", headers=self.headers)
                    if get_resp.status_code == 200:
                        target_entry = get_resp.json()
                except httpx.HTTPError:
                    pass

            # Create or Update
            if target_entry:
                logger.info(f"[Contentful] Updating existing Entry {entry_id} ({content_type_id})...")
                version = target_entry["sys"]["version"]
                update_payload = {"fields": localized_fields}
                update_headers = {**self.headers, "X-Contentful-Version": str(version)}
                save_resp = await client.put(f"{self.base_url}/entries/{entry_id}", json=update_payload, headers=update_headers)
                save_resp.raise_for_status()
                saved_data = save_resp.json()
            else:
                logger.info(f"[Contentful] Creating new Entry ({content_type_id})...")
                create_headers = {**self.headers, "X-Contentful-Content-Type": content_type_id}
                if entry_id:
                    save_resp = await client.put(f"{self.base_url}/entries/{entry_id}", json={"fields": localized_fields}, headers=create_headers)
                else:
                    save_resp = await client.post(f"{self.base_url}/entries", json={"fields": localized_fields}, headers=create_headers)
                save_resp.raise_for_status()
                saved_data = save_resp.json()

            entry_sys_id = saved_data["sys"]["id"]
            entry_version = saved_data["sys"]["version"]

            # Publish Entry
            logger.info(f"[Contentful] Publishing Entry {entry_sys_id}...")
            pub_headers = {**self.headers, "X-Contentful-Version": str(entry_version)}
            pub_resp = await client.put(f"{self.base_url}/entries/{entry_sys_id}/published", headers=pub_headers)
            pub_resp.raise_for_status()
            return pub_resp.json()

contentful_service = ContentfulService()
