import aiosqlite
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DB_PATH = "pozemak.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS processed_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supabase_id TEXT UNIQUE NOT NULL,
                discord_message_id TEXT,
                channel_id TEXT,
                status TEXT DEFAULT 'pending',
                word_replacements TEXT DEFAULT '{}',
                title_sk TEXT,
                body_sk TEXT,
                image_url TEXT,
                source_url TEXT,
                created_at TEXT,
                processed_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS processed_videos (
                supabase_id TEXT PRIMARY KEY NOT NULL
            )
        """)
        await db.commit()
    logger.info("Database initialised")


async def is_video_processed(supabase_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM processed_videos WHERE supabase_id = ?", (supabase_id,)
        ) as cursor:
            return await cursor.fetchone() is not None


async def mark_video_processed(supabase_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO processed_videos (supabase_id) VALUES (?)", (supabase_id,)
        )
        await db.commit()


async def is_processed(supabase_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM processed_articles WHERE supabase_id = ?", (supabase_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def add_pending_article(
    supabase_id: str,
    discord_message_id: str,
    channel_id: str,
    title_sk: str,
    body_sk: str,
    image_url: str,
    source_url: str,
):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO processed_articles
                (supabase_id, discord_message_id, channel_id, status,
                 word_replacements, title_sk, body_sk, image_url, source_url, created_at)
            VALUES (?, ?, ?, 'pending', '{}', ?, ?, ?, ?, ?)
            """,
            (supabase_id, discord_message_id, channel_id, title_sk, body_sk, image_url, source_url, now),
        )
        await db.commit()
    logger.debug(f"Added pending article supabase_id={supabase_id} msg={discord_message_id}")


async def get_article_by_message_id(message_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM processed_articles WHERE discord_message_id = ?", (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)


async def update_article_status(message_id: str, status: str):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE processed_articles SET status = ?, processed_at = ? WHERE discord_message_id = ?",
            (status, now, message_id),
        )
        await db.commit()
    logger.debug(f"Updated msg={message_id} status={status}")


async def update_word_replacements(message_id: str, replacements: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE processed_articles SET word_replacements = ? WHERE discord_message_id = ?",
            (json.dumps(replacements, ensure_ascii=False), message_id),
        )
        await db.commit()
    logger.debug(f"Updated word_replacements for msg={message_id}: {replacements}")


async def get_articles_by_message_id(message_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM processed_articles WHERE discord_message_id = ?", (message_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def update_article_status_by_supabase_id(supabase_id: str, status: str):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE processed_articles SET status = ?, processed_at = ? WHERE supabase_id = ?",
            (status, now, supabase_id),
        )
        await db.commit()


async def set_batch_message_id(supabase_ids: list[str], discord_message_id: str, channel_id: str):
    """Update discord_message_id and channel_id for a list of articles."""
    async with aiosqlite.connect(DB_PATH) as db:
        for sid in supabase_ids:
            await db.execute(
                "UPDATE processed_articles SET discord_message_id = ?, channel_id = ? WHERE supabase_id = ?",
                (discord_message_id, channel_id, sid),
            )
        await db.commit()


async def get_all_pending() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM processed_articles WHERE status = 'pending'"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
