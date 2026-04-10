#!/usr/bin/env python3
"""One-time script: remove sentences containing email addresses from all articles in Supabase."""
import re
import os
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

EMAIL_SENTENCE_RE = re.compile(r'[^.!?\n]*@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}[^.!?\n]*[.!?]?')


def sanitize(text: str | None) -> str | None:
    if not text:
        return text
    cleaned = EMAIL_SENTENCE_RE.sub('', text)
    cleaned = re.sub(r' {2,}', ' ', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def main():
    db = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Fetch all articles that might contain emails
    page, page_size, total_fixed = 0, 500, 0
    while True:
        result = (
            db.table("articles")
            .select("id, text, text_sk")
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
        )
        if not result.data:
            break

        for article in result.data:
            updates = {}
            new_text    = sanitize(article.get("text"))
            new_text_sk = sanitize(article.get("text_sk"))

            if new_text != article.get("text"):
                updates["text"] = new_text
            if new_text_sk != article.get("text_sk"):
                updates["text_sk"] = new_text_sk

            if updates:
                db.table("articles").update(updates).eq("id", article["id"]).execute()
                total_fixed += 1
                print(f"  Fixed article {article['id']}")

        if len(result.data) < page_size:
            break
        page += 1

    print(f"\n✅ Done — fixed {total_fixed} article(s).")


if __name__ == "__main__":
    main()
