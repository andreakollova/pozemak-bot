import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path

import certifi
import httpx

logger = logging.getLogger(__name__)

# Patterns to detect video URLs inside article text
_VIDEO_PATTERNS = [
    r"https?://(?:www\.)?youtube\.com/watch\?[^\s\"'<>]+",
    r"https?://youtu\.be/[^\s\"'<>]+",
    r"https?://(?:www\.)?vimeo\.com/\d+[^\s\"'<>]*",
    r"https?://[^\s\"'<>]+\.mp4(?:\?[^\s\"'<>]*)?",
]
_VIDEO_RE = re.compile("|".join(_VIDEO_PATTERNS), re.IGNORECASE)


async def find_video_url(text: str) -> str | None:
    """Return the first video URL found in text, or None."""
    match = _VIDEO_RE.search(text or "")
    return match.group(0) if match else None


async def upload_to_catbox(file_path: str) -> str | None:
    """Upload to gofile.io (mobile-friendly download page).
    Falls back to catbox.moe on failure.
    """
    try:
        file_size_mb = os.path.getsize(file_path) / 1024 / 1024
        logger.info(f"Uploading {file_size_mb:.1f} MB to gofile.io…")

        async with httpx.AsyncClient(verify=certifi.where(), timeout=30) as client:
            srv_resp = await client.get("https://api.gofile.io/servers")
            srv_resp.raise_for_status()
            server = srv_resp.json()["data"]["servers"][0]["name"]

        async with httpx.AsyncClient(verify=certifi.where(), timeout=600) as client:
            with open(file_path, "rb") as f:
                resp = await client.post(
                    f"https://{server}.gofile.io/contents/uploadfile",
                    files={"file": (os.path.basename(file_path), f, "video/mp4")},
                )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "ok":
            url = data["data"]["downloadPage"]
            logger.info(f"gofile.io OK: {url}")
            return url
        logger.error(f"gofile.io unexpected: {data}")
    except Exception as exc:
        logger.error(f"gofile.io upload error: {exc}", exc_info=True)

    # Fallback: catbox.moe
    try:
        logger.info("Falling back to catbox.moe…")
        async with httpx.AsyncClient(verify=certifi.where(), timeout=600) as client:
            with open(file_path, "rb") as f:
                resp = await client.post(
                    "https://catbox.moe/user/api.php",
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": (os.path.basename(file_path), f, "video/mp4")},
                )
        resp.raise_for_status()
        url = resp.text.strip()
        if url.startswith("https://"):
            logger.info(f"catbox.moe fallback OK: {url}")
            return url
    except Exception as exc:
        logger.error(f"catbox.moe fallback error: {exc}", exc_info=True)

    return None


async def _cobalt_download(url: str, work_dir: str) -> tuple[str | None, str | None]:
    """Download video via cobalt.tools API — bypasses YouTube IP restrictions on cloud servers."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.cobalt.tools/",
                json={"url": url},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status")
        if status not in ("stream", "redirect", "tunnel"):
            logger.warning(f"cobalt.tools unexpected status: {status} — {data}")
            return None, None

        stream_url = data.get("url")
        if not stream_url:
            return None, None

        logger.info(f"cobalt.tools OK — downloading stream…")
        out_path = os.path.join(work_dir, "video.mp4")
        async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
            async with client.stream("GET", stream_url) as r:
                r.raise_for_status()
                with open(out_path, "wb") as f:
                    async for chunk in r.aiter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            size = os.path.getsize(out_path) / 1024 / 1024
            logger.info(f"cobalt.tools downloaded: {size:.1f} MB")
            return out_path, None

    except Exception as exc:
        logger.warning(f"cobalt.tools failed: {exc}")

    return None, None


async def download_video(url: str, output_dir: str | None = None) -> tuple[str | None, str | None]:
    """Download a video. Tries cobalt.tools first (works on cloud), falls back to yt-dlp.

    Returns (file_path, description). Either can be None on failure.
    """
    work_dir = output_dir or tempfile.mkdtemp(prefix="pozemak_video_")

    # Try cobalt.tools first — works on Render/cloud (bypasses YouTube IP blocks)
    file_path, description = await _cobalt_download(url, work_dir)
    if file_path:
        return file_path, description

    # Fallback: yt-dlp (works locally)
    logger.info("cobalt.tools failed — trying yt-dlp…")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _yt_dlp_download, url, work_dir)
    except Exception as exc:
        logger.error(f"yt-dlp error: {exc}", exc_info=True)
        return None, None

    if result is None:
        return None, None

    file_path, description = result
    if file_path:
        size = os.path.getsize(file_path) / 1024 / 1024
        logger.info(f"yt-dlp downloaded: {file_path} ({size:.1f} MB)")
    return file_path, description


def _yt_dlp_download(url: str, work_dir: str) -> tuple[str | None, str | None] | None:
    """Blocking helper — runs yt-dlp, returns (file_path, description)."""
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        logger.error("yt-dlp is not installed")
        return None

    output_template = os.path.join(work_dir, "%(id)s.%(ext)s")
    ydl_opts = {
        # Prefer pre-merged mp4 streams (720p or 360p) that don't require ffmpeg.
        # Falls back to 'best' (single-stream) which also needs no merging.
        "format": "22/18/best[height<=720][ext=mp4]/best[ext=mp4]/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
        except Exception as exc:
            logger.error(f"yt-dlp extract_info failed for {url}: {exc}")
            return None
        if info is None:
            logger.error("yt-dlp returned no info")
            return None
        description = (info.get("title") or "").strip() or None

    mp4_files = list(Path(work_dir).glob("*.mp4"))
    if not mp4_files:
        all_files = [f for f in Path(work_dir).iterdir() if f.is_file()]
        if not all_files:
            logger.error("yt-dlp: no output file found")
            return None, description
        mp4_files = sorted(all_files, key=lambda f: f.stat().st_size, reverse=True)

    return str(mp4_files[0]), description
