import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
WEBSITE_API_URL = os.getenv("WEBSITE_API_URL", "")
WEBSITE_API_KEY = os.getenv("WEBSITE_API_KEY", "")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_ACCOUNT_ID = "17841413427897379"  # fixed — never read from env
FACEBOOK_PAGE_ID     = "2171198413191158"   # Hockey Refresh Facebook Page
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "")
CANVA_API_KEY = os.getenv("CANVA_API_KEY", "")
CANVA_TEMPLATE_ID = os.getenv("CANVA_TEMPLATE_ID", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))
