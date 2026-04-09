# Pozemak Discord Bot

This bot watches your Supabase database for new field-hockey articles, sends them to a Discord channel for human review, translates them from Dutch to Slovak via DeepL, and then publishes approved articles to your website and Instagram.

---

## Prerequisites

Before you start, make sure the following are installed on your computer:

| Tool | How to install |
|---|---|
| **Python 3.11+** | https://www.python.org/downloads/ — tick "Add Python to PATH" on Windows |
| **ffmpeg** | macOS: `brew install ffmpeg` / Ubuntu: `sudo apt install ffmpeg` / Windows: https://ffmpeg.org/download.html |
| **yt-dlp** | Installed automatically by `pip install -r requirements.txt` |

---

## Step 1 — Get the files

Either clone the repository or copy the entire `pozemak_bot/` folder to your computer.

```
/pozemak_bot/
├── main.py
├── config.py
├── database.py
├── translation.py
├── publisher.py
├── canva.py
├── instagram.py
├── video.py
├── requirements.txt
├── .env.example
└── cogs/
    └── article_review.py
```

Open a terminal (macOS/Linux) or Command Prompt (Windows) and navigate into the folder:

```bash
cd /path/to/pozemak_bot
```

---

## Step 2 — Install Python dependencies

```bash
pip install -r requirements.txt
```

If you have multiple Python versions, use `pip3` instead of `pip`.

---

## Step 3 — Create your `.env` file

Copy the example file:

```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in each value. The sections below explain where to find each one.

---

## Step 4 — Discord bot setup

1. Go to https://discord.com/developers/applications and click **New Application**.
2. Give it a name (e.g. "Pozemak Bot") and click **Create**.
3. Click **Bot** in the left sidebar, then **Add Bot** → **Yes, do it!**
4. Under **Privileged Gateway Intents**, enable **Message Content Intent**.
5. Click **Reset Token** → copy the token → paste it into `.env` as `DISCORD_BOT_TOKEN`.
6. Click **OAuth2 → URL Generator** in the sidebar.
   - Under **Scopes** tick: `bot`, `applications.commands`
   - Under **Bot Permissions** tick: `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`, `View Channels`
7. Copy the generated URL, open it in your browser, and invite the bot to your server.
8. **Get the channel ID**: In Discord, go to *Settings → Advanced* and enable **Developer Mode**. Then right-click the channel where you want articles to appear → **Copy Channel ID**. Paste it into `.env` as `DISCORD_CHANNEL_ID`.

---

## Step 5 — DeepL setup

1. Sign up for a free account at https://www.deepl.com/pro#developer (the free tier allows 500,000 characters/month).
2. After logging in, go to **Account → Authentication Key for DeepL API**.
3. Copy the key and paste it into `.env` as `DEEPL_API_KEY`.

Note: the free tier uses the `api-free.deepl.com` endpoint, which the bot uses automatically.

---

## Step 6 — Website API setup

The bot publishes approved articles by calling your Next.js website's `/api/articles` endpoint.

- `WEBSITE_API_URL` — the base URL of your website, e.g. `https://pozemak.sk`
- `WEBSITE_API_KEY` — a secret string you choose yourself. Set the **same** string as `PUBLISH_API_KEY` in your website's environment variables.

---

## Step 7 — Instagram setup

Instagram publishing requires a **Meta Business account** connected to an **Instagram Professional account**.

1. Go to https://developers.facebook.com/ and create an App (type: **Business**).
2. Add the **Instagram Graph API** product.
3. Generate a **long-lived Page Access Token** with the `instagram_basic`, `instagram_content_publish`, and `pages_read_engagement` permissions.
4. Find your **Instagram Business Account ID**: in Meta Business Suite go to *Settings → Accounts → Instagram Accounts*, click the account, and copy the numeric ID.
5. Paste the token into `.env` as `INSTAGRAM_ACCESS_TOKEN` and the ID as `INSTAGRAM_ACCOUNT_ID`.
6. Sign up for a free **ImgBB** account at https://api.imgbb.com/ to get an `IMGBB_API_KEY`. The bot uses ImgBB to host images temporarily so Instagram can fetch them.

---

## Step 8 — Canva setup (optional)

If you want polished Instagram images generated via Canva instead of the built-in Pillow fallback:

1. Apply for Canva Connect API access at https://www.canva.com/developers/.
2. Create an integration and copy the API key → paste as `CANVA_API_KEY`.
3. In Canva, create an Instagram Post template and note its design ID (visible in the URL when editing) → paste as `CANVA_TEMPLATE_ID`.

If you leave these empty the bot will use the built-in image generator instead (black background + white text + green branding).

---

## Step 9 — Run the bot

```bash
python main.py
```

You should see log output like:

```
2025-01-01 12:00:00 [INFO] __main__: Logged in as Pozemak Bot#1234 (123456789)
2025-01-01 12:00:00 [INFO] __main__: Review channel: #articles-review
```

The bot will check Supabase every 5 minutes (configurable via `POLL_INTERVAL`) and post new articles to Discord.

To keep the bot running permanently on a server, use a process manager such as `screen`, `tmux`, or `systemd`.

---

## How it works

1. The bot polls the `articles` table in Supabase every `POLL_INTERVAL` seconds.
2. New articles are translated from Dutch to Slovak using DeepL and posted to Discord as embeds with three buttons:
   - **✅ Approve** — publishes the article to the website and posts an image to Instagram.
   - **❌ Reject** — marks the article as rejected.
   - **✏️ Edit replacements** — opens a modal where you can specify word substitutions (e.g. `hockey=pozemný hokej`) that will be applied before publishing.
3. If the article body contains a YouTube, Vimeo, or direct `.mp4` link, the video is automatically downloaded and attached to the Discord message.

---

## Testing each stage independently

### Test translation
```python
import asyncio
from translation import translate_to_slovak
print(asyncio.run(translate_to_slovak("Hallo wereld")))
```

### Test publishing
```python
import asyncio
from publisher import publish_article
asyncio.run(publish_article("Test titel", "Test inhoud", "", "https://example.com"))
```

### Test Instagram image generation (Pillow)
```python
from canva import create_instagram_image_pillow
with open("test.jpg", "wb") as f:
    f.write(create_instagram_image_pillow("Test Article Title"))
```

### Test video detection
```python
import asyncio
from video import find_video_url
url = asyncio.run(find_video_url("Check this out: https://youtu.be/dQw4w9WgXcQ"))
print(url)
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `Channel NOT FOUND` in logs | Double-check `DISCORD_CHANNEL_ID` and ensure the bot has been invited with the correct permissions |
| `DeepL translation failed` | Verify `DEEPL_API_KEY` is correct and your free quota has not been exceeded |
| `httpx.HTTPStatusError 401` on publish | `WEBSITE_API_KEY` does not match `PUBLISH_API_KEY` on the website |
| Instagram container stays in `IN_PROGRESS` | The image URL must be publicly accessible; check that ImgBB upload succeeded |
| `yt-dlp` not found | Run `pip install yt-dlp` or ensure it is on your PATH |
| `ffmpeg` not found | Install ffmpeg (see Prerequisites above) |
| Bot goes offline after closing terminal | Use `screen -S pozemak python main.py` to keep it running in the background |
