import io
import logging
import textwrap
from pathlib import Path

import httpx

from config import CANVA_API_KEY, CANVA_TEMPLATE_ID

logger = logging.getLogger(__name__)

TEMPLATE_PATH     = Path(__file__).parent / "template.png"
TEMPLATE_PATH_GBR = Path(__file__).parent / "template-gbr.png"

# Domain → template file mapping for additional countries
COUNTRY_TEMPLATES: dict[str, Path] = {
    "greatbritainhockey": Path(__file__).parent / "template-gbr.png",
    "hockey.ie":           Path(__file__).parent / "template-ireland.png",
    "scottish-hockey":     Path(__file__).parent / "template-scotland.png",
    "hockey.org.au":       Path(__file__).parent / "template-australia.png",
    "eshockey.es":         Path(__file__).parent / "template-spain.png",
    "cahockey.org.ar":     Path(__file__).parent / "template-argentina.png",
    "hockey.de":           Path(__file__).parent / "template-germany.png",
    "hockey.be":           Path(__file__).parent / "template-belgium.png",
    "hockeyindia.org":     Path(__file__).parent / "template-india.png",
    "eurohockey.org":      Path(__file__).parent / "template-worldwide.png",
    "fih.hockey":          Path(__file__).parent / "template-worldwide.png",
}


def _template_for_url(source_url: str) -> Path:
    """Return the correct template PNG path based on the article source URL."""
    for domain, path in COUNTRY_TEMPLATES.items():
        if domain in source_url:
            if path.exists():
                return path
            logger.warning(f"Template not found for {domain}: {path}")
            break
    return TEMPLATE_PATH

# Instagram post dimensions — matches the template.png (portrait 4:5)
IMG_WIDTH  = 1080
IMG_HEIGHT = 1350

# Branding colours (R, G, B)
GREEN = (0, 180, 80)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


async def create_instagram_image_canva(title: str, image_url: str) -> bytes:
    """Generate an Instagram image via the Canva Connect API.

    Uses CANVA_API_KEY and CANVA_TEMPLATE_ID from config.
    Raises on any HTTP or API error so the caller can fall back to Pillow.
    """
    if not CANVA_API_KEY or not CANVA_TEMPLATE_ID:
        raise ValueError("Canva API key or template ID not configured")

    headers = {
        "Authorization": f"Bearer {CANVA_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        # 1. Create a design from a template
        create_resp = await client.post(
            "https://api.canva.com/rest/v1/designs",
            headers=headers,
            json={
                "design_type": {"type": "preset", "name": "InstagramPost"},
                "asset_id": CANVA_TEMPLATE_ID,
            },
        )
        create_resp.raise_for_status()
        design_id = create_resp.json()["design"]["id"]
        logger.debug(f"Created Canva design: {design_id}")

        # 2. Export the design as PNG
        export_resp = await client.post(
            f"https://api.canva.com/rest/v1/designs/{design_id}/exports",
            headers=headers,
            json={"format": "png"},
        )
        export_resp.raise_for_status()
        export_job = export_resp.json()["job"]
        export_id = export_job["id"]

        # 3. Poll until the export is ready
        import asyncio
        for _ in range(20):
            await asyncio.sleep(3)
            status_resp = await client.get(
                f"https://api.canva.com/rest/v1/designs/{design_id}/exports/{export_id}",
                headers=headers,
            )
            status_resp.raise_for_status()
            job_data = status_resp.json()["job"]
            if job_data["status"] == "success":
                download_url = job_data["urls"][0]
                break
            if job_data["status"] == "failed":
                raise RuntimeError(f"Canva export failed: {job_data}")
        else:
            raise TimeoutError("Canva export did not complete in time")

        # 4. Download the exported PNG
        img_resp = await client.get(download_url)
        img_resp.raise_for_status()
        return img_resp.content


def create_instagram_image_pillow(
    photo_bytes: bytes | None = None,
    gbr: bool = False,
    source_url: str = "",
) -> bytes:
    """Composite article photo under the PNG template overlay.

    Layout:
      - Photo stretched/cropped to template size (background)
      - template.png (RGBA with transparency) composited on top
    Falls back to a solid black background if no photo provided.
    Pass source_url for automatic country template selection.
    """
    from PIL import Image

    if source_url:
        tmpl_path = _template_for_url(source_url)
    elif gbr:
        tmpl_path = TEMPLATE_PATH_GBR
    else:
        tmpl_path = TEMPLATE_PATH
    if not tmpl_path.exists():
        raise FileNotFoundError(f"Template not found: {tmpl_path}")

    template = Image.open(tmpl_path).convert("RGBA")
    tw, th = template.size

    # Background: photo or solid black
    if photo_bytes:
        try:
            photo = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
            # Crop to same aspect ratio as template, then resize
            photo_ratio = photo.width / photo.height
            tmpl_ratio  = tw / th
            if photo_ratio > tmpl_ratio:
                # Photo is wider — crop sides
                new_w = int(photo.height * tmpl_ratio)
                offset = (photo.width - new_w) // 2
                photo = photo.crop((offset, 0, offset + new_w, photo.height))
            else:
                # Photo is taller — crop top/bottom from center
                new_h = int(photo.width / tmpl_ratio)
                offset = (photo.height - new_h) // 2
                photo = photo.crop((0, offset, photo.width, offset + new_h))
            photo = photo.resize((tw, th), Image.LANCZOS)
        except Exception as exc:
            logger.warning(f"Could not process photo: {exc}")
            photo = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
    else:
        photo = Image.new("RGBA", (tw, th), (0, 0, 0, 255))

    # Template goes ON TOP of photo
    result = Image.alpha_composite(photo, template)

    buffer = io.BytesIO()
    result.convert("RGB").save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


async def create_instagram_image(
    photo_bytes: bytes | None = None,
    gbr: bool = False,
    source_url: str = "",
) -> bytes:
    """Apply the PNG template over the article photo and return JPEG bytes."""
    return create_instagram_image_pillow(photo_bytes, gbr=gbr, source_url=source_url)
