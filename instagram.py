import asyncio
import logging
import uuid

import httpx

from config import INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_ACCOUNT_ID, FACEBOOK_PAGE_ID, SUPABASE_URL, SUPABASE_KEY

GRAPH_BASE = "https://graph.facebook.com/v21.0"
STORAGE_BUCKET = "instagram-images"
logger = logging.getLogger(__name__)


async def post_to_instagram(image_bytes: bytes, caption: str, story_bytes: bytes | None = None) -> str:
    """Upload image_bytes and publish a post to Instagram.

    Steps:
    1. Upload image bytes to ImgBB to get a publicly accessible URL.
    2. Create an Instagram media container with the image URL and caption.
    3. Poll the container status until it reaches FINISHED.
    4. Publish the container via media_publish.

    Returns the published media_id string.
    Raises on any error.
    """
    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        raise ValueError("Instagram credentials not configured (INSTAGRAM_ACCESS_TOKEN / INSTAGRAM_ACCOUNT_ID)")

    async with httpx.AsyncClient(timeout=60) as client:
        # Step 1: upload to Supabase Storage
        public_url = await _upload_to_supabase(image_bytes)
        logger.info(f"Image uploaded to Supabase Storage: {public_url}")

        # Step 2: create media container
        container_resp = await client.post(
            f"{GRAPH_BASE}/{INSTAGRAM_ACCOUNT_ID}/media",
            params={
                "image_url": public_url,
                "caption": caption,
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
        )
        if container_resp.status_code >= 400:
            raise RuntimeError(f"Instagram media error {container_resp.status_code}: {container_resp.text}")
        container_id = container_resp.json()["id"]
        logger.info(f"Created Instagram media container: {container_id}")

        # Step 3: wait for container to be ready
        await _wait_for_container(client, container_id)

        # Step 4: publish
        publish_resp = await client.post(
            f"{GRAPH_BASE}/{INSTAGRAM_ACCOUNT_ID}/media_publish",
            params={
                "creation_id": container_id,
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
        )
        publish_resp.raise_for_status()
        media_id = publish_resp.json()["id"]
        logger.info(f"Published to Instagram: media_id={media_id}")

        # Also post to Facebook Page and Instagram Story
        await _post_to_facebook(client, public_url, caption)
        story_url = await _upload_to_supabase(story_bytes) if story_bytes else public_url
        await _post_to_ig_story(client, story_url)

        return media_id


async def _upload_to_supabase(image_bytes: bytes) -> str:
    """Upload image bytes to Supabase Storage and return the public URL."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase credentials not configured")

    from supabase import create_client
    db = create_client(SUPABASE_URL, SUPABASE_KEY)

    filename = f"{uuid.uuid4().hex}.jpg"
    db.storage.from_(STORAGE_BUCKET).upload(
        path=filename,
        file=image_bytes,
        file_options={"content-type": "image/jpeg"},
    )
    public_url = db.storage.from_(STORAGE_BUCKET).get_public_url(filename)
    logger.debug(f"Supabase Storage upload success: {public_url}")
    return public_url


async def _wait_for_container(
    client: httpx.AsyncClient,
    container_id: str,
    max_tries: int = 10,
):
    """Poll the Instagram container status until it reaches FINISHED.

    Raises RuntimeError if it never reaches FINISHED within max_tries.
    """
    for attempt in range(1, max_tries + 1):
        await asyncio.sleep(6)
        status_resp = await client.get(
            f"{GRAPH_BASE}/{container_id}",
            params={
                "fields": "status_code",
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
        )
        status_resp.raise_for_status()
        data = status_resp.json()
        status_code = data.get("status_code", "")
        logger.debug(f"Container {container_id} status ({attempt}/{max_tries}): {status_code}")

        if status_code == "FINISHED":
            return
        if status_code == "ERROR":
            # Fetch error details
            err_resp = await client.get(
                f"{GRAPH_BASE}/{container_id}",
                params={"fields": "status_code,status", "access_token": INSTAGRAM_ACCESS_TOKEN},
            )
            err_detail = err_resp.json().get("status", status_code)
            raise RuntimeError(f"Instagram container ERROR: {err_detail}")

    raise RuntimeError(
        f"Instagram container {container_id} did not reach FINISHED after {max_tries} attempts"
    )


async def _post_to_ig_story(client: httpx.AsyncClient, image_url: str) -> None:
    """Post the same image as an Instagram Story."""
    try:
        container_resp = await client.post(
            f"{GRAPH_BASE}/{INSTAGRAM_ACCOUNT_ID}/media",
            params={
                "image_url": image_url,
                "media_type": "STORIES",
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
        )
        if container_resp.status_code >= 400:
            logger.error(f"IG Story container failed {container_resp.status_code}: {container_resp.text}")
            return
        container_id = container_resp.json()["id"]
        await _wait_for_container(client, container_id)
        publish_resp = await client.post(
            f"{GRAPH_BASE}/{INSTAGRAM_ACCOUNT_ID}/media_publish",
            params={
                "creation_id": container_id,
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
        )
        if publish_resp.status_code >= 400:
            logger.error(f"IG Story publish failed {publish_resp.status_code}: {publish_resp.text}")
        else:
            logger.info(f"Published to Instagram Story: {publish_resp.json().get('id')}")
    except Exception as e:
        logger.error(f"IG Story error: {e}")


async def _post_to_facebook(client: httpx.AsyncClient, image_url: str, caption: str) -> None:
    """Post a photo to the Hockey Refresh Facebook Page."""
    try:
        resp = await client.post(
            f"{GRAPH_BASE}/{FACEBOOK_PAGE_ID}/photos",
            params={
                "url": image_url,
                "caption": caption,
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
        )
        if resp.status_code >= 400:
            logger.error(f"Facebook post failed {resp.status_code}: {resp.text}")
        else:
            logger.info(f"Published to Facebook: {resp.json().get('id')}")
    except Exception as e:
        logger.error(f"Facebook post error: {e}")
