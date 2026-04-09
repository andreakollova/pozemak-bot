#!/usr/bin/env python3
"""Prepare pending Supabase articles and signal the main bot to send them to Discord."""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from config import SUPABASE_URL, SUPABASE_KEY
from translation import translate_to_slovak

TRIGGER_FILE = Path("/tmp/pozemak_poll_now")


async def main():
    from supabase import create_client
    import sqlite3

    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    result = db.table("articles").select("*").order("scraped_at", desc=True).limit(50).execute()

    conn = sqlite3.connect("pozemak.db")

    new_count = 0
    for article in result.data:
        sid = str(article["id"])
        row = conn.execute(
            "SELECT 1 FROM processed_articles WHERE supabase_id = ?", (sid,)
        ).fetchone()
        if row:
            continue

        # Translate if not already done
        title_sk = article.get("title_sk") or ""
        text_sk  = article.get("text_sk")  or ""
        title    = article.get("title", "")
        text     = article.get("text", "")

        if not title_sk or title_sk.strip() == title.strip():
            title_sk = await translate_to_slovak(title)
        if not text_sk or text_sk.strip() == text.strip():
            text_sk = await translate_to_slovak(text)

        # Save translations back to Supabase so the bot uses them
        db.table("articles").update({"title_sk": title_sk, "text_sk": text_sk}).eq("id", sid).execute()
        new_count += 1
        print(f"  Prepared: {title_sk[:60]}")

    conn.close()

    if new_count > 0:
        TRIGGER_FILE.write_text("poll")
        print(f"\n✅ {new_count} article(s) prepared — main bot will send them within 5 seconds.")
    else:
        print("No new articles found.")


asyncio.run(main())
