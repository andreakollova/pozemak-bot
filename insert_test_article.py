#!/usr/bin/env python3
"""Insert a test article directly into Supabase so the bot picks it up."""
import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

db = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

result = db.table("articles").insert({
    "url": "https://www.pozemak.sk/test-bot-article",
    "title": "Netherlands wins field hockey tournament in Amsterdam",
    "text": "The Dutch national field hockey team won the gold medal at the international tournament in Amsterdam. In a dramatic final they beat Belgium 3-2 after extra time.",
    "title_sk": None,
    "text_sk": None,
    "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/20/Soccerball.svg/240px-Soccerball.svg.png",
    "published": False,
}).execute()

print("Inserted:", result.data)
