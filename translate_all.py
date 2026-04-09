#!/usr/bin/env python3
"""
Preloží všetky existujúce články v Supabase ktoré nemajú slovenský preklad.
Používa DeepL API (rovnaký kľúč ako bot).

Spustenie:
    python3 translate_all.py
"""

import asyncio
import os
from pathlib import Path

_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from supabase import create_client
from translation import translate_to_slovak


async def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("❌ SUPABASE_URL alebo SUPABASE_KEY nie sú nastavené v .env")
        return

    db = create_client(url, key)

    # Načítaj všetky články bez slovenského prekladu
    res = db.table("articles").select("id, title, text, title_sk, text_sk").execute()
    articles = [a for a in res.data if not a.get("title_sk")]

    print(f"Článkov na preklad: {len(articles)}")
    if not articles:
        print("✅ Všetky články sú už preložené.")
        return

    for i, article in enumerate(articles, 1):
        title = article.get("title") or ""
        text  = article.get("text")  or ""
        print(f"  [{i}/{len(articles)}] {title[:70]}…")

        try:
            title_sk = await translate_to_slovak(title) if title else ""
            text_sk  = await translate_to_slovak(text)  if text  else ""

            db.table("articles").update({
                "title_sk": title_sk,
                "text_sk":  text_sk,
            }).eq("id", article["id"]).execute()

            print(f"    ✓ {title_sk[:60]}")
        except Exception as e:
            print(f"    ✗ Chyba: {e}")

        # Krátka pauza aby sme nezahlcili DeepL API
        await asyncio.sleep(0.5)

    print("\n✅ Hotovo!")


if __name__ == "__main__":
    asyncio.run(main())
