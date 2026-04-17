import httpx
import logging
from datetime import datetime, timezone

from config import WEBSITE_API_URL, WEBSITE_API_KEY

logger = logging.getLogger(__name__)


async def _send_push(title: str, source_url: str) -> None:
    if not WEBSITE_API_URL or not WEBSITE_API_KEY:
        return
    slug = source_url.rstrip('/').split('/')[-1] if source_url else ''
    url = f"/article/{slug}" if slug else '/'
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{WEBSITE_API_URL.rstrip('/')}/api/push/send",
                json={"title": "🏑 New article", "body": title, "url": url},
                headers={"Content-Type": "application/json", "x-api-key": WEBSITE_API_KEY},
            )
        logger.info(f"Push sent for: {title[:60]}")
    except Exception as e:
        logger.warning(f"Push notification failed: {e}")


async def publish_article(
    title: str,
    body: str,
    image_url: str,
    source_url: str,
    supabase_id: str | None = None,
    top_story: bool = False,
) -> dict:
    """Update existing Supabase article with Slovak translation via the website API.

    If supabase_id is provided (normal flow), PATCHes the existing article.
    Falls back to POST (creates new) if no supabase_id given.
    Raises httpx.HTTPStatusError on non-2xx responses.
    Returns the parsed JSON response body.
    """
    if not WEBSITE_API_URL:
        raise ValueError("WEBSITE_API_URL is not configured")

    headers = {
        "X-API-Key": WEBSITE_API_KEY,
        "Content-Type": "application/json",
    }

    logger.info(f"Publishing article to website: {title[:60]!r}")

    async with httpx.AsyncClient(timeout=30) as client:
        if supabase_id:
            # Update existing article with Slovak translation and mark as published
            response = await client.patch(
                f"{WEBSITE_API_URL.rstrip('/')}/api/admin/articles/{supabase_id}",
                json={"title_sk": title, "text_sk": body, "published": True, "top_story": top_story},
                headers=headers,
            )
        else:
            # Fallback: create new article
            payload = {
                "title_sk": title,
                "text_sk": body,
                "image_url": image_url,
                "url": source_url,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
            response = await client.post(
                f"{WEBSITE_API_URL.rstrip('/')}/api/articles",
                json=payload,
                headers=headers,
            )
        response.raise_for_status()
        data = response.json()
        logger.info(f"Article published successfully: {data}")

    await _send_push(title, source_url)
    return data
