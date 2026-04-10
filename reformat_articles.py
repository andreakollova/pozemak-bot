#!/usr/bin/env python3
"""Reformat all existing articles in Supabase with emoji subheadings using GPT-4o."""
import asyncio
import os
import re
import logging

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
from translation import translate_to_english, SYSTEM_PROMPT
from config import SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

EMAIL_SENTENCE_RE = re.compile(r'[^.!?\n]*@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}[^.!?\n]*[.!?]?')

REFORMAT_PROMPT = SYSTEM_PROMPT + """

IMPORTANT: The text you receive is already in English. Do NOT translate it.
Rewrite it with proper structure: 2–4 sections each starting with a short emoji subheading.
Keep all facts, names, scores and quotes exactly as-is.
"""


async def reformat(text: str) -> str:
    if not OPENAI_API_KEY or not text.strip():
        return text
    from openai import AsyncOpenAI
    import httpx, certifi
    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        http_client=httpx.AsyncClient(verify=certifi.where()),
    )
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": REFORMAT_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.4,
        max_tokens=4096,
    )
    result = resp.choices[0].message.content.strip()
    # Also strip any email sentences that snuck back in
    result = EMAIL_SENTENCE_RE.sub('', result)
    return re.sub(r' {2,}', ' ', result).strip()


async def main():
    db = create_client(SUPABASE_URL, SUPABASE_KEY)

    page, page_size = 0, 100
    total, done, skipped = 0, 0, 0

    while True:
        result = (
            db.table("articles")
            .select("id, text, text_sk, title_sk")
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
        )
        if not result.data:
            break
        total += len(result.data)

        for article in result.data:
            sid = article["id"]
            # Use existing English text_sk if available, otherwise original text
            source = (article.get("text_sk") or article.get("text") or "").strip()
            if not source or len(source) < 100:
                skipped += 1
                continue

            try:
                new_text_sk = await reformat(source)
                db.table("articles").update({"text_sk": new_text_sk}).eq("id", sid).execute()
                done += 1
                title = (article.get("title_sk") or "")[:60]
                logger.info(f"[{done}] Reformatted: {title}")
                # Small delay to avoid hitting rate limits
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Failed {sid}: {e}")
                skipped += 1

        if len(result.data) < page_size:
            break
        page += 1

    print(f"\n✅ Done — {done} reformatted, {skipped} skipped (too short / no text).")


if __name__ == "__main__":
    asyncio.run(main())
