#!/usr/bin/env python3
"""Re-translate all pending articles from Dutch to English via Claude."""
import asyncio
import sqlite3

from config import SUPABASE_URL, SUPABASE_KEY
from translation import translate_to_slovak


async def main():
    from supabase import create_client
    conn = sqlite3.connect("pozemak.db")
    conn.execute("PRAGMA journal_mode=WAL")
    db = create_client(SUPABASE_URL, SUPABASE_KEY)

    rows = conn.execute(
        "SELECT supabase_id FROM processed_articles WHERE status='pending'"
    ).fetchall()
    ids = [r[0] for r in rows]
    print(f"Translating {len(ids)} articles...", flush=True)

    for i, sid in enumerate(ids, 1):
        result = db.table("articles").select("title, text").eq("id", sid).execute()
        if not result.data:
            print(f"  [{i}/{len(ids)}] skip {sid}", flush=True)
            continue

        row = result.data[0]
        orig_title = (row.get("title") or "").strip()
        orig_text  = (row.get("text") or "").strip()

        if not orig_title and not orig_text:
            print(f"  [{i}/{len(ids)}] empty {sid}", flush=True)
            continue

        title_en = (await translate_to_slovak(orig_title)).lstrip('#').strip()
        body_en  = await translate_to_slovak(orig_text) if orig_text else ""

        conn.execute(
            "UPDATE processed_articles SET title_sk=?, body_sk=? WHERE supabase_id=?",
            (title_en, body_en, sid),
        )
        conn.commit()
        db.table("articles").update({"title_sk": title_en, "text_sk": body_en}).eq("id", sid).execute()
        print(f"  [{i}/{len(ids)}] ✅ {title_en[:70]}", flush=True)

    conn.close()
    print("\nAll done.", flush=True)


asyncio.run(main())
