import asyncio
import logging

import discord
from discord.ext import commands

from config import DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID
from database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log"),
    ],
)
logger = logging.getLogger(__name__)


class PozemakBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        await self.load_extension("cogs.article_review")
        logger.info("Extensions loaded")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} ({self.user.id})")
        ch = self.get_channel(DISCORD_CHANNEL_ID)
        if ch:
            logger.info(f"Review channel: #{ch.name} ({ch.id})")
        else:
            logger.warning(
                f"Review channel NOT FOUND — check DISCORD_CHANNEL_ID={DISCORD_CHANNEL_ID}"
            )

    async def on_message(self, message: discord.Message):
        # Ignoruj vlastné správy
        if message.author == self.user:
            return

        # Odpovedaj na DM alebo keď je bot mentioned
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mention = self.user in message.mentions

        if not is_dm and not is_mention:
            return

        text = message.content.lower().strip()
        # Odstráň mention z textu
        text = text.replace(f'<@{self.user.id}>', '').replace(f'<@!{self.user.id}>', '').strip()

        if any(w in text for w in ['ahoj', 'hello', 'hi', 'cau', 'čau', 'hey']):
            reply = f"Hey {message.author.display_name}! 👋 I'm the Pozemak bot — I scrape field hockey news and send it here for review."
        elif any(w in text for w in ['help', 'pomoc', 'pomôž', 'čo vieš', 'co vies']):
            reply = (
                "**What I can do:**\n"
                "📰 Automatically scrape new articles from NL, GB, Ireland, Scotland, Australia, Spain, Argentina, Germany & Belgium\n"
                "🔔 Send them here for approval (every 5 minutes)\n"
                "✅ After approval, publish the article to the website\n"
                "📸 Optionally post to Instagram with country-specific template\n\n"
                "When new articles arrive you'll see a message with buttons."
            )
        elif any(w in text for w in ['stav', 'status', 'ako si', 'funguje']):
            reply = "✅ Online and running! Polling every 5 minutes."
        else:
            reply = f"Hey {message.author.display_name}! 🤖 Type `help` to see what I can do."

        await message.reply(reply)

        await self.process_commands(message)


async def main():
    async with PozemakBot() as bot:
        await bot.start(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
