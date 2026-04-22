import asyncio
import logging

import certifi
import httpx
from openai import AsyncOpenAI

from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

SYSTEM_PROMPT = """\
You are a field hockey sports journalist writing for an international audience of fans and players.

IMPORTANT RULES:
- This content is always about FIELD HOCKEY (played on grass or turf with sticks and a ball). \
Never use the words "ice hockey" or any ice hockey terminology.
- Always say "field hockey", "hockey match", "hockey player", "the pitch", etc.
- Gender: always pay close attention to whether people mentioned are male or female \
(use context clues like team names, Dutch pronouns hij/zij/haar, player history, or common knowledge). \
Use the correct pronouns (he/his or she/her) consistently throughout the article.
- Preserve all facts, names, scores, and dates exactly as in the original.
- Do not add any information that is not in the original text.
- Return only the translated/rewritten text — no preamble, no notes, no explanation.

WRITING STYLE:
- Write in a warm, engaging, easy-to-read style — like a knowledgeable friend explaining the match.
- Use clear, simple language. Prefer short sentences. Avoid jargon and overly complex vocabulary.
- Mix short punchy sentences with slightly longer ones for natural rhythm.
- Use active voice. Be direct and confident, not stiff or formal.
- Make the reader feel the energy of the game — but stay factual and accurate.

FORMATTING RULES for full articles:
- Divide the article into 2–4 logical sections. Each section MUST start with a short subheading \
(3–7 words) on its own line, prefixed with one of these emojis (rotate through them): 🚀 🔥 💥 💪 🏑
- The subheading line must be alone — followed by a blank line, then the section paragraphs.
- Keep paragraphs short (2–4 sentences max). Separate paragraphs with blank lines.

TITLE/HEADLINE RULES (when translating a single short headline):
- Write it as a natural, flowing English sentence.
- Use sentence case: capitalise only the first word and proper nouns/abbreviations (e.g. EHL, FIH, team names). \
Do NOT capitalise every word.
- Do NOT use colons (:) or dashes (-) in the title.
- Example: instead of "Den Bosch: victory at Pinoké" → "Den Bosch claim impressive victory away at Pinoké"
"""


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            http_client=httpx.AsyncClient(verify=certifi.where()),
        )
    return _client


async def translate_to_english(text: str) -> str:
    """Translate Dutch field hockey text to professional English using GPT-4o.

    Function name kept for backwards compatibility with all callers.
    Falls back to the original text if the API key is missing or the request fails.
    """
    if not OPENAI_API_KEY or not text.strip():
        return text

    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.6,
            max_tokens=4096,
        )
        translated = response.choices[0].message.content.strip()
        logger.debug(f"Translated {len(text)} chars NL→EN via GPT-4o")
        return translated
    except Exception as exc:
        logger.error(f"GPT-4o translation failed: {exc}")
        return text


async def generate_video_adjectives(title: str) -> list[str]:
    """Generate 3 field hockey sport adjectives with emojis based on video title.

    Returns a list of 3 strings like ["⚡ Explosive", "💪 Dominant", "🎯 Precise"].
    Falls back to defaults on error.
    """
    if not OPENAI_API_KEY:
        return ["⚡ Explosive", "💪 Dominant", "🎯 Thrilling"]
    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You generate exactly 3 short English adjectives (1-2 words each) "
                        "that describe a field hockey video highlight. "
                        "Each adjective must be preceded by a relevant sport/action emoji. "
                        "Output ONLY the 3 items, one per line, nothing else. "
                        "Example format:\n⚡ Explosive\n💪 Dominant\n🎯 Precise"
                    ),
                },
                {"role": "user", "content": f"Video title: {title}"},
            ],
            temperature=0.8,
            max_tokens=60,
        )
        raw = response.choices[0].message.content.strip()
        items = [line.strip() for line in raw.splitlines() if line.strip()][:3]
        if len(items) == 3:
            return items
    except Exception as exc:
        logger.error(f"generate_video_adjectives failed: {exc}")
    return ["⚡ Explosive", "💪 Dominant", "🎯 Thrilling"]


def apply_word_replacements(text: str, replacements: dict) -> str:
    """Replace each key with its corresponding value in text (case-sensitive)."""
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def parse_replacements(raw: str) -> dict:
    """Parse a comma-separated string of 'old=new' pairs into a dict."""
    result: dict[str, str] = {}
    if not raw or not raw.strip():
        return result
    for part in raw.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        value = value.strip()
        if key:
            result[key] = value
    return result
