#!/usr/bin/env python3
"""Update existing Discord pending messages with the corrected titles from Supabase."""
import asyncio
import sqlite3
from dotenv import load_dotenv
load_dotenv()

import discord
from config import DISCORD_BOT_TOKEN as DISCORD_TOKEN, DISCORD_CHANNEL_ID, SUPABASE_URL, SUPABASE_KEY
from supabase import create_client

async def main():
    db = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Load all pending articles with discord message IDs from local SQLite
    conn = sqlite3.connect("pozemak.db")
    rows = conn.execute(
        "SELECT supabase_id, discord_message_id FROM processed_articles "
        "WHERE status='pending' AND discord_message_id != 'pending'"
    ).fetchall()
    conn.close()

    print(f"Found {len(rows)} pending articles to update in Discord")

    # Get updated titles from Supabase
    result = db.table("articles").select("id, title_sk").execute()
    title_map = {str(a["id"]): a["title_sk"] for a in result.data}

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    updated = 0

    @client.event
    async def on_ready():
        nonlocal updated
        print(f"Logged in as {client.user}")
        channel = client.get_channel(DISCORD_CHANNEL_ID)
        if not channel:
            print(f"Channel {DISCORD_CHANNEL_ID} not found")
            await client.close()
            return

        for supabase_id, message_id in rows:
            new_title = title_map.get(supabase_id)
            if not new_title:
                continue
            try:
                msg = await channel.fetch_message(int(message_id))
                if not msg.embeds:
                    continue
                emb = msg.embeds[0].copy()
                # Only update if title actually changed
                current = emb.title or ""
                expected = f"{'🇳🇱🇬🇧🇮🇪🏴󠁧󠁢󠁳󠁣󠁴󠁿🇦🇺🇪🇸🇦🇷🇩🇪🇧🇪🇮🇳'[0]} {new_title}"
                # Rebuild title with correct flag
                flag_part = current.split(" ")[0] if current else ""
                new_embed_title = f"{flag_part} {new_title}"[:256]
                if new_embed_title != current:
                    emb.title = new_embed_title
                    await msg.edit(embed=emb)
                    print(f"  Updated: {new_embed_title[:80]}")
                    updated += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"  Error on {message_id}: {e}")

        print(f"\nDone — updated {updated} Discord embeds.")
        await client.close()

    await client.start(DISCORD_TOKEN)

asyncio.run(main())
