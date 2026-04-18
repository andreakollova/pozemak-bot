import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

TRIGGER_FILE = Path("/tmp/pozemak_poll_now")

import discord
from discord.ext import commands, tasks

from config import DISCORD_CHANNEL_ID, POLL_INTERVAL, SUPABASE_URL, SUPABASE_KEY
from database import (
    is_processed,
    add_pending_article,
    update_article_status_by_supabase_id,
    set_batch_message_id,
    get_all_pending,
)
from translation import translate_to_english, generate_video_adjectives
from publisher import publish_article
from instagram import post_to_instagram
from canva import create_instagram_image
from video import find_video_url, download_video, upload_to_catbox

logger = logging.getLogger(__name__)

_ig_reminder_channel: int | None = None  # set in ArticleReviewCog.cog_load

async def _ig_reminder(supabase_id: str):
    """Send a Discord notification 30 minutes after an Instagram post."""
    import discord as _discord
    if _ig_reminder_channel is None:
        return
    try:
        # We need the bot instance — stored as a module-level reference
        bot = _ig_reminder_bot
        if bot is None:
            return
        channel = bot.get_channel(_ig_reminder_channel)
        if channel:
            await channel.send(
                "⏰ 30 minutes since the last Instagram post — you can add another one!"
            )
    except Exception as exc:
        logger.error(f"IG reminder error: {exc}")

_ig_reminder_bot = None   # set in cog_load


_SOURCE_FLAGS: list[tuple[str, str, str]] = [
    # (domain_fragment, flag_emoji, credit_name)
    ("greatbritainhockey",  "🇬🇧", "GB Hockey"),
    ("hockey.ie",           "🇮🇪", "Hockey Ireland"),
    ("scottish-hockey",     "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Scottish Hockey"),
    ("hockey.org.au",       "🇦🇺", "Hockey Australia"),
    ("eshockey.es",         "🇪🇸", "Real Federación Española de Hockey"),
    ("cahockey.org.ar",     "🇦🇷", "Argentina Hockey"),
    ("hockey.de",           "🇩🇪", "Hockey Germany"),
    ("hockey.be",           "🇧🇪", "Hockey Belgium"),
    ("hockey.nl",           "🇳🇱", "HockeyNL"),
    ("hockeyindia.org",     "🇮🇳", "Hockey India"),
    ("eurohockey.org",      "🇪🇺", "EuroHockey"),
    ("fih.hockey",          "🏑", "FIH Hockey"),
]


def _source_info(source_url: str) -> tuple[str, str]:
    """Return (flag_emoji, credit_name) for the article's source."""
    for fragment, flag, credit in _SOURCE_FLAGS:
        if fragment in source_url:
            return flag, credit
    return "🇳🇱", "HockeyNL"


def _source_flag(source_url: str) -> str:
    """Return the correct flag emoji for the article's source."""
    return _source_info(source_url)[0]


def _ig_len(s: str) -> int:
    """Instagram counts string length as UTF-16 code units (like JavaScript).
    Characters above U+FFFF (most emojis, including flag sequences) cost 2 each."""
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)


_PARA_EMOJIS = ["🏑", "⚡", "💪", "🔥", "🎯", "🌍", "🏆", "💥", "🚀", "👊"]


_SUBHEAD_EMOJI_RE = re.compile(r'^[\U0001F300-\U0001FAFF]\s*(.{1,80})$')


def _mark_subheadings(body: str) -> str:
    """Replace subheading paragraphs with 'Heading text -' so they act as natural separators."""
    result = []
    for para in body.split('\n\n'):
        p = para.strip()
        m = _SUBHEAD_EMOJI_RE.match(p)
        # A subheading is short, starts with emoji, has no mid-sentence punctuation
        if m and '.' not in p and '!' not in p and '?' not in p:
            heading_text = m.group(1).strip()
            if heading_text:
                result.append(heading_text + ' -')
        else:
            result.append(para)
    return '\n\n'.join(result)


def build_instagram_caption(title: str, body: str, flag: str = "🇳🇱", credit: str = "HockeyNL") -> str:
    # Convert subheadings to "Heading -" so they read naturally in the flattened text
    body = _mark_subheadings(body)
    # Flatten body into plain text, stripping any remaining emojis
    flat = re.sub(r'\s+', ' ', body.replace('\n', ' ')).strip()
    flat = re.sub(r'[\U0001F300-\U0001FAFF]\s*', '', flat).strip()
    full_text = re.sub(r'\s+', ' ', flat)

    # Split into individual sentences, cap at 10
    all_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_text) if s.strip()]
    if not all_sentences:
        all_sentences = [title]
    sentences = all_sentences[:10]

    # Group into chunks of 4 sentences, each chunk becomes one paragraph prefixed with an emoji
    pairs = [" ".join(sentences[i:i+4]) for i in range(0, len(sentences), 4)]
    paragraphs = [f"{_PARA_EMOJIS[i % len(_PARA_EMOJIS)]} {pair}" for i, pair in enumerate(pairs)]

    FOOTER = f"Credit: {credit}\n\n👀 For more hockey news check out hockeyrefresh.com"
    IG_LIMIT = 2190

    header = f"{flag} {title}"
    caption_parts = [header]
    used = _ig_len(header) + 2 + _ig_len(FOOTER)

    for para in paragraphs:
        chunk = "\n\n" + para
        if used + _ig_len(chunk) > IG_LIMIT:
            break
        caption_parts.append(para)
        used += _ig_len(chunk)

    caption_parts.append(FOOTER)
    caption = "\n\n".join(caption_parts)

    # Hard safety: drop last body paragraph if still over limit
    while _ig_len(caption) > IG_LIMIT and len(caption_parts) > 2:
        caption_parts.pop(-2)
        caption = "\n\n".join(caption_parts)

    return caption


def _sanitize_body(text: str) -> str:
    """Remove entire sentences containing email addresses."""
    text = re.sub(r'[^.!?\n]*@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}[^.!?\n]*[.!?]?', '', text)
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def _publish_article(article: dict, post_ig: bool) -> str:
    """Publish article to website and optionally Instagram."""
    title = article["title_sk"] or ""
    body  = _sanitize_body(article["body_sk"] or "")

    await publish_article(
        title, body, article["image_url"] or "", article["source_url"] or "",
        supabase_id=article["supabase_id"],
        top_story=post_ig,
    )
    await update_article_status_by_supabase_id(article["supabase_id"], "approved")

    if not post_ig:
        return "✅ Published to web"

    try:
        import httpx as _httpx
        image_url = article["image_url"] or ""
        if not image_url:
            raise ValueError("Article has no image — Instagram post not possible")
        # Download article photo
        async with _httpx.AsyncClient(timeout=60, follow_redirects=True) as _hc:
            img_resp = await _hc.get(image_url, headers={"User-Agent": "Mozilla/5.0"})
            img_resp.raise_for_status()
            photo_bytes = img_resp.content
        # Apply PNG template overlay (auto-selects country template from source_url)
        src_url = article.get("source_url", "")
        img_bytes = await create_instagram_image(photo_bytes, source_url=src_url)
        flag, credit = _source_info(src_url)
        caption = build_instagram_caption(title, body, flag=flag, credit=credit)
        await post_to_instagram(img_bytes, caption)
        # Schedule 30-minute reminder
        asyncio.get_event_loop().call_later(
            30 * 60,
            lambda: asyncio.ensure_future(_ig_reminder(article["supabase_id"]))
        )
        return "✅ Web + 📸 Instagram"
    except _httpx.ReadTimeout:
        logger.error(f"Instagram rate limit (ReadTimeout) for {article['supabase_id']}")
        return "✅ Web OK — ⚠️ Instagram: too fast, wait ~30 min and try again"
    except Exception as e:
        import traceback
        logger.error(f"Instagram failed for {article['supabase_id']}: {e!r}\n{traceback.format_exc()}")
        return f"✅ Web OK — ⚠️ Instagram failed: {e}"


# ── Edit modal ─────────────────────────────────────────────────────────────────

class ArticleEditModal(discord.ui.Modal, title="Edit article"):
    def __init__(self, view: "ArticleConfirmView"):
        super().__init__()
        self._view = view
        self.title_input = discord.ui.TextInput(
            label="Title",
            default=(view.article.get("title_sk") or "")[:100],
            max_length=250,
            style=discord.TextStyle.short,
        )
        self.body_input = discord.ui.TextInput(
            label="Article text",
            default=(view.article.get("body_sk") or "")[:4000],
            max_length=4000,
            style=discord.TextStyle.paragraph,
            required=False,
        )
        self.add_item(self.title_input)
        self.add_item(self.body_input)

    async def on_submit(self, interaction: discord.Interaction):
        self._view.article["title_sk"] = self.title_input.value.strip()
        self._view.article["body_sk"] = self.body_input.value.strip()

        # Refresh embed with new title/body preview
        if interaction.message and interaction.message.embeds:
            emb = interaction.message.embeds[0].copy()
            emb.title = f"📰 {self._view.article['title_sk'][:250]}"
            preview = self._view.article["body_sk"][:300]
            if len(self._view.article["body_sk"]) > 300:
                preview += "…"
            emb.description = preview or "_(no text)_"
            emb.colour = discord.Color.yellow()
            emb.set_footer(text=f"✏️ Edited — {interaction.user.display_name}")
            await interaction.message.edit(embed=emb, view=self._view)

        await interaction.response.send_message("✅ Article updated. You can now approve it.", ephemeral=True)


# ── Per-article confirmation view ──────────────────────────────────────────────

class ArticleConfirmView(discord.ui.View):
    """Shown for each article individually — user picks Web+IG, Web only, or Skip.
    Uses stable custom_ids so views survive bot restarts."""

    def __init__(self, article: dict):
        super().__init__(timeout=None)
        self.article = article
        sid = article["supabase_id"]

        b_ig = discord.ui.Button(label="Web + Instagram", emoji="🚀", style=discord.ButtonStyle.success, custom_id=f"pz_ig:{sid}")
        b_web = discord.ui.Button(label="Web only", emoji="🌐", style=discord.ButtonStyle.primary, custom_id=f"pz_web:{sid}")
        b_edit = discord.ui.Button(label="Edit", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id=f"pz_edit:{sid}")
        b_skip = discord.ui.Button(label="Reject", emoji="❌", style=discord.ButtonStyle.danger, custom_id=f"pz_skip:{sid}")

        b_ig.callback = self._cb_ig
        b_web.callback = self._cb_web
        b_edit.callback = self._cb_edit
        b_skip.callback = self._cb_skip

        for b in [b_ig, b_web, b_edit, b_skip]:
            self.add_item(b)

    async def _finish(self, interaction: discord.Interaction, post_ig: bool):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            result = await _publish_article(self.article, post_ig=post_ig)
            if interaction.message and interaction.message.embeds:
                emb = interaction.message.embeds[0].copy()
                emb.colour = discord.Color.green()
                emb.set_footer(text=f"{result} — {interaction.user.display_name}")
                await interaction.message.edit(embed=emb, view=None)
            await interaction.followup.send(result, ephemeral=True)
        except Exception as e:
            logger.error(f"Publish error: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    async def _cb_ig(self, interaction: discord.Interaction):
        await self._finish(interaction, post_ig=True)

    async def _cb_web(self, interaction: discord.Interaction):
        await self._finish(interaction, post_ig=False)

    async def _cb_edit(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ArticleEditModal(self))

    async def _cb_skip(self, interaction: discord.Interaction):
        await update_article_status_by_supabase_id(self.article["supabase_id"], "rejected")
        # Mark as rejected in Supabase so it never comes back after bot restart
        try:
            from supabase import create_client
            from config import SUPABASE_URL, SUPABASE_KEY
            db = create_client(SUPABASE_URL, SUPABASE_KEY)
            db.table("articles").update({"rejected": True, "published": False}).eq("id", self.article["supabase_id"]).execute()
        except Exception as e:
            logger.error(f"Failed to mark article as rejected in Supabase: {e}")
        if interaction.message and interaction.message.embeds:
            emb = interaction.message.embeds[0].copy()
            emb.colour = discord.Color.red()
            emb.set_footer(text=f"❌ Rejected — {interaction.user.display_name}")
            await interaction.message.edit(embed=emb, view=None)
        await interaction.response.send_message("❌ Article rejected.", ephemeral=True)


# ── Batch overview view ─────────────────────────────────────────────────────────

class BatchReviewView(discord.ui.View):
    """Overview of all new articles — user selects which to process, then confirms individually."""

    def __init__(self, articles: list[dict], channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.articles_map: dict[str, dict] = {a["supabase_id"]: a for a in articles}
        self.channel = channel
        self.selected_ids: set[str] = set()

        batch_key = articles[0]["supabase_id"][:12] if articles else "default"

        options = [
            discord.SelectOption(
                label=(a["title_sk"] or "(no title)")[:100],
                value=a["supabase_id"],
                emoji="📰",
            )
            for a in articles[:25]
        ]

        sel = discord.ui.Select(
            placeholder=f"Select from {len(articles)} articles...",
            min_values=0,
            max_values=len(options),
            options=options,
            custom_id=f"pz_bsel:{batch_key}",
        )
        sel.callback = self.on_select
        self.add_item(sel)

        btn_confirm = discord.ui.Button(
            label="Confirm selected →", emoji="📋",
            style=discord.ButtonStyle.success,
            custom_id=f"pz_bconf:{batch_key}",
        )
        btn_confirm.callback = self._confirm_selected

        btn_reject = discord.ui.Button(
            label="Reject all", emoji="❌",
            style=discord.ButtonStyle.danger,
            custom_id=f"pz_brej:{batch_key}",
        )
        btn_reject.callback = self._reject_all

        self.add_item(btn_confirm)
        self.add_item(btn_reject)

    async def on_select(self, interaction: discord.Interaction):
        self.selected_ids = set(interaction.data.get("values", []))
        n = len(self.selected_ids)
        msg = (
            f"✅ Selected **{n}** article{'s' if n != 1 else ''}. "
            f"Click **Confirm selected →** to review individually."
            if n else "ℹ️ No articles selected."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    async def _confirm_selected(self, interaction: discord.Interaction):
        if not self.selected_ids:
            await interaction.response.send_message(
                "⚠️ Please select at least one article from the dropdown.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        for sid in self.articles_map:
            if sid not in self.selected_ids:
                await update_article_status_by_supabase_id(sid, "rejected")

        await interaction.message.edit(
            content=(
                f"📋 **{len(self.selected_ids)}** article(s) going for review — "
                f"see messages below."
            ),
            embeds=[],
            view=None,
        )

        for sid in self.selected_ids:
            article = self.articles_map[sid]
            title = article.get("title_sk") or "(no title)"
            body_preview = (article.get("body_sk") or "")[:300]
            if len(article.get("body_sk") or "") > 300:
                body_preview += "…"

            emb = discord.Embed(
                title=f"📰 {title[:250]}",
                description=body_preview or "_(no text)_",
                color=discord.Color.orange(),
                url=article.get("source_url") or None,
            )
            if article.get("image_url"):
                emb.set_image(url=article["image_url"])
            emb.set_footer(text=f"ID: {sid}")

            await self.channel.send(
                content="**📰 Approve this article?**",
                embed=emb,
                view=ArticleConfirmView(article),
            )
            await asyncio.sleep(0.5)

        await interaction.followup.send(
            f"✅ Sent {len(self.selected_ids)} article(s) for approval.", ephemeral=True
        )

    async def _reject_all(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        for sid in self.articles_map:
            await update_article_status_by_supabase_id(sid, "rejected")
        await interaction.message.edit(
            content=f"❌ All {len(self.articles_map)} articles rejected ({interaction.user.display_name})",
            embeds=[],
            view=None,
        )
        await interaction.followup.send("❌ All rejected.", ephemeral=True)


# ── Cog ────────────────────────────────────────────────────────────────────────

class ArticleReviewCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._check_lock = asyncio.Lock()  # prevents concurrent _check_new_articles runs
        self.poll_articles.start()
        self.watch_trigger.start()
        # Make bot accessible to module-level reminder helper
        import cogs.article_review as _self_module
        _self_module._ig_reminder_bot = bot
        _self_module._ig_reminder_channel = DISCORD_CHANNEL_ID

    def cog_unload(self):
        self.poll_articles.cancel()
        self.watch_trigger.cancel()

    async def cog_load(self):
        """Re-register persistent views for all pending articles on startup.
        Uses Supabase as source of truth so views survive bot restarts / SQLite wipes."""
        try:
            from supabase import create_client
            db = create_client(SUPABASE_URL, SUPABASE_KEY)
            result = (
                db.table("articles")
                .select("id, title_sk, text_sk, image_url, url")
                .eq("discord_sent", True)
                .or_("published.eq.false,published.is.null")
                .neq("rejected", True)
                .order("scraped_at", desc=True)
                .limit(100)
                .execute()
            )
            count = 0
            for row in result.data:
                article = {
                    "supabase_id": str(row["id"]),
                    "title_sk": row.get("title_sk") or "",
                    "body_sk": row.get("text_sk") or "",
                    "image_url": row.get("image_url") or "",
                    "source_url": row.get("url") or "",
                }
                self.bot.add_view(ArticleConfirmView(article))
                count += 1
            if count:
                logger.info(f"Restored {count} persistent ArticleConfirmView(s) from Supabase")
        except Exception as e:
            logger.warning(f"Could not restore views: {e}")

    @tasks.loop(seconds=POLL_INTERVAL)
    async def poll_articles(self):
        async with self._check_lock:
            await self._check_new_articles()
            await self._check_new_videos()

    @poll_articles.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(15)

    @tasks.loop(seconds=5)
    async def watch_trigger(self):
        """Watch for trigger file created by push_article.py to run immediate poll."""
        if TRIGGER_FILE.exists():
            try:
                TRIGGER_FILE.unlink()
            except OSError:
                pass
            logger.info("Trigger file detected — running immediate poll")
            async with self._check_lock:
                await self._check_new_articles()
                await self._check_new_videos()

    @watch_trigger.before_loop
    async def before_watch(self):
        await self.bot.wait_until_ready()

    async def _check_new_articles(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            logger.warning("Supabase not configured — skipping poll")
            return
        try:
            from supabase import create_client
            db = create_client(SUPABASE_URL, SUPABASE_KEY)
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

            # Atomically claim unclaimed articles: UPDATE first, get back only the rows
            # we just claimed. Two concurrent bot instances can never claim the same row.
            claim = (
                db.table("articles")
                .update({"discord_sent": True})
                .is_("discord_sent", "null")
                .neq("rejected", True)
                .gte("scraped_at", cutoff)
                .execute()
            )

            channel = self.bot.get_channel(DISCORD_CHANNEL_ID)
            if not channel:
                logger.error(f"Channel {DISCORD_CHANNEL_ID} not found")
                return

            new_articles = list(reversed(claim.data or []))

            if not new_articles:
                return

            logger.info(f"Claimed {len(new_articles)} new articles — translating...")

            prepared: list[dict] = []
            for article in new_articles:
                orig_title = article.get("title", "")
                orig_text  = article.get("text", "")
                stored_title_sk = article.get("title_sk") or ""
                stored_text_sk  = article.get("text_sk")  or ""

                # If not yet translated (title_sk same as Dutch title or empty), translate now
                if not stored_title_sk or stored_title_sk.strip() == orig_title.strip():
                    title_sk = await translate_to_english(orig_title)
                else:
                    title_sk = stored_title_sk

                if not stored_text_sk or stored_text_sk.strip() == orig_text.strip():
                    body_sk = await translate_to_english(orig_text)
                else:
                    body_sk = stored_text_sk
                image_url = article.get("image_url", "")
                source    = article.get("url", "")

                await add_pending_article(
                    supabase_id=str(article["id"]),
                    discord_message_id="pending",
                    channel_id=str(channel.id),
                    title_sk=title_sk,
                    body_sk=body_sk,
                    image_url=image_url,
                    source_url=source,
                )
                prepared.append({
                    "supabase_id": str(article["id"]),
                    "title_sk": title_sk,
                    "body_sk": body_sk,
                    "image_url": image_url,
                    "source_url": source,
                })

            for batch_start in range(0, len(prepared), 25):
                batch = prepared[batch_start:batch_start + 25]
                await self._send_batch(channel, batch)

        except Exception as e:
            logger.error(f"Poll error: {e}", exc_info=True)

    async def _check_new_videos(self):
        """Send the next video with a ready download_url to Discord."""
        if not SUPABASE_URL or not SUPABASE_KEY:
            return

        try:
            from supabase import create_client
            db = create_client(SUPABASE_URL, SUPABASE_KEY)
            result = (
                db.table("videos")
                .select("id, title, title_sk, youtube_url, category, download_url")
                .or_("discord_sent.is.null,discord_sent.eq.false")
                .not_.is_("download_url", "null")  # only send if download is ready
                .order("scraped_at", desc=False)  # oldest first — FIFO queue
                .limit(1)
                .execute()
            )

            if not result.data:
                return

            channel = self.bot.get_channel(DISCORD_CHANNEL_ID)
            if not channel:
                return

            v = result.data[0]
            title = v.get("title_sk") or v.get("title") or "Video"
            yt_url = v.get("youtube_url") or ""
            dl_url = v.get("download_url") or ""
            cat = v.get("category") or ""
            category_icon = "🏑" if cat in ("dames", "heren") else "🎬"
            credits = "Credits: FIH Hockey" if cat.startswith("fih") else "Credits: Eyecons Hockey / HockeyNL"

            lines = [f"{category_icon} **{title}**"]
            if yt_url:
                lines.append(f"▶️ {yt_url}")
            if dl_url:
                lines.append(f"📥 Download: {dl_url}")
            lines.append(f"\n{credits}")

            await channel.send("\n".join(lines))
            logger.info(f"Video sent to Discord: {v['id']} — {title[:60]}")

            # Mark as sent and clear download_url to free the slot for the next video
            try:
                db.table("videos").update({"discord_sent": True, "download_url": None}).eq("id", v["id"]).execute()
            except Exception as _e:
                logger.warning(f"Could not mark discord_sent for video {v['id']}: {_e}")

        except Exception as e:
            logger.error(f"Video poll error: {e}", exc_info=True)

    async def _send_batch(self, channel: discord.TextChannel, batch: list[dict]):
        """Send each article as an individual persistent ArticleConfirmView message."""
        logger.info(f"Sending {len(batch)} article(s) to Discord")
        from supabase import create_client
        _db = create_client(SUPABASE_URL, SUPABASE_KEY)

        _COUNTRY_NAMES = {
            "🇳🇱": "Netherlands", "🇬🇧": "Great Britain", "🇮🇪": "Ireland",
            "🏴󠁧󠁢󠁳󠁣󠁴󠁿": "Scotland", "🇦🇺": "Australia", "🇪🇸": "Spain",
            "🇦🇷": "Argentina", "🇩🇪": "Germany", "🇧🇪": "Belgium",
            "🇮🇳": "India", "🇪🇺": "EuroHockey", "🏑": "FIH Hockey",
        }
        _EMBED_COLORS = {
            "🇳🇱": discord.Color.orange(),
            "🇬🇧": discord.Color.blue(),
            "🇮🇪": discord.Color.green(),
            "🏴󠁧󠁢󠁳󠁣󠁴󠁿": discord.Color.dark_blue(),
            "🇦🇺": discord.Color.gold(),
            "🇪🇸": discord.Color.red(),
            "🇦🇷": discord.Color.from_rgb(116, 172, 223),
            "🇩🇪": discord.Color.from_rgb(80, 80, 80),
            "🇧🇪": discord.Color.from_rgb(0, 100, 200),
            "🇮🇳": discord.Color.from_rgb(255, 153, 51),   # India saffron
            "🇪🇺": discord.Color.from_rgb(0, 70, 153),     # EuroHockey blue
            "🏑": discord.Color.from_rgb(0, 150, 100),      # FIH green
        }

        for a in batch:
            flag, credit = _source_info(a.get("source_url", ""))
            country = _COUNTRY_NAMES.get(flag, "Unknown")
            emb = discord.Embed(
                title=f"{flag} {(a['title_sk'] or '')[:253]}",
                url=a["source_url"] or None,
                color=_EMBED_COLORS.get(flag, discord.Color.orange()),
            )
            full_body = (a.get("body_sk") or "").strip()
            if full_body:
                # Discord embed description limit is 4096 chars
                emb.description = full_body[:4096]
            emb.add_field(name="Country", value=f"{flag} {country}", inline=True)
            emb.add_field(name="Source", value=credit, inline=True)
            if a["image_url"]:
                emb.set_image(url=a["image_url"])
            emb.set_footer(text=f"ID: {a['supabase_id']}")

            view = ArticleConfirmView(a)
            msg = await channel.send(
                content="**📰 New article — approve?**",
                embed=emb,
                view=view,
            )
            a["discord_message_id"] = str(msg.id)
            await set_batch_message_id([a["supabase_id"]], str(msg.id), str(channel.id))
            # Mark as sent in Supabase — survives bot restarts, no more SQLite dependency
            try:
                _db.table("articles").update({"discord_sent": True}).eq("id", a["supabase_id"]).execute()
            except Exception as _e:
                logger.warning(f"Could not mark discord_sent for {a['supabase_id']}: {_e}")
            logger.info(f"Sent article {a['supabase_id'][:8]} → Discord msg {msg.id}")
            await asyncio.sleep(0.5)


async def setup(bot: commands.Bot):
    await bot.add_cog(ArticleReviewCog(bot))
