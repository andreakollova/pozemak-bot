#!/usr/bin/env python3
"""Send a test article to Discord for review (triggers the normal approval flow)."""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from database import add_pending_article

async def main():
    test_id = "test-article-001"
    await add_pending_article(
        supabase_id=test_id,
        discord_message_id="pending",
        channel_id="0",
        title_sk="Holandsko víťazí na turnaji pozemného hokeja v Amsterdame",
        body_sk=(
            "Holandský národný tím pozemného hokeja získal zlatú medailu na medzinárodnom turnaji "
            "v Amsterdame. V dramatickom finále porazili Belgicko 3:2 po predĺžení. "
            "Kapitán tímu označil toto víťazstvo za historický moment pre holandský šport. "
            "Turnaja sa zúčastnilo 12 krajín z celej Európy. Ďalší turnaj sa uskutoční na jeseň."
        ),
        image_url="https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Coat_of_arms_of_Netherlands.svg/800px-Coat_of_arms_of_Netherlands.svg.png",
        source_url="https://www.pozemak.sk",
    )
    print("✅ Testovací článok pridaný do databázy — bot ho pošle do Discordu do ~15 sekúnd")

asyncio.run(main())
