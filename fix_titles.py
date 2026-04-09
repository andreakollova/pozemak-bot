#!/usr/bin/env python3
"""Fix all article titles to sentence case in Supabase."""
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

from openai import AsyncOpenAI
import certifi, httpx
from config import SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY
from supabase import create_client

SYSTEM = """\
Convert the given English field hockey article headline to sentence case.
Rules:
- Capitalise only the first word and proper nouns (team names, player names, country names, city names, competition names like EHL/FIH/EuroHockey, etc.)
- Abbreviations like EHL, FIH, WC, GB, MO14, U18 must stay fully capitalised
- All other words must be lowercase
- Do NOT change any wording — only fix capitalisation
- Return ONLY the corrected headline, nothing else
"""

async def fix_title(client, title: str) -> str:
    if not title.strip():
        return title
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": title},
        ],
        temperature=0,
        max_tokens=150,
    )
    return response.choices[0].message.content.strip()

async def main():
    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        http_client=httpx.AsyncClient(verify=certifi.where()),
    )

    result = db.table("articles").select("id, title_sk, published").execute()
    articles = [a for a in result.data if a.get("title_sk")]
    print(f"Fixing {len(articles)} article titles...")

    fixed = 0
    for a in articles:
        old = a["title_sk"]
        new = await fix_title(client, old)
        if new != old:
            db.table("articles").update({"title_sk": new}).eq("id", a["id"]).execute()
            print(f"  {'PUB' if a['published'] else '   '} {old[:60]}")
            print(f"       → {new[:60]}")
            fixed += 1
        await asyncio.sleep(0.1)

    print(f"\nDone — fixed {fixed}/{len(articles)} titles.")

asyncio.run(main())
