import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

logger = logging.getLogger(__name__)

_CHANNEL_URL = "https://t.me/s/{channel}"

# Colloquial names people actually use in chat, which rarely match the official instrument
# name returned by the broker API (e.g. "Сбербанк ПАО"). Falls back to the raw ticker for
# anything not listed here.
_TICKER_ALIASES: dict[str, list[str]] = {
    "SBER": ["сбер", "сбербанк"],
    "GAZP": ["газпром"],
    "LKOH": ["лукойл"],
    "GMKN": ["норникель", "норильский никель"],
    "ROSN": ["роснефть"],
    "VTBR": ["втб"],
    "YNDX": ["яндекс"],
    "MTSS": ["мтс"],
    "MGNT": ["магнит"],
    "NVTK": ["новатэк"],
    "TATN": ["татнефть"],
    "ALRS": ["алроса"],
    "CHMF": ["северсталь"],
    "PLZL": ["полюс"],
    "MOEX": ["мосбиржа", "московская биржа"],
    "AFLT": ["аэрофлот"],
}

# Broad macro/geopolitical news moves the whole market, not just one ticker, so it's
# matched against every active ticker regardless of company-name mentions.
_MACRO_KEYWORDS = [
    "санкц", "цб рф", "центробанк", "ключевая ставка", "геополит",
    "россия", "росси", "рубл", "минфин", "путин", "кремл",
]


@dataclass
class ChannelPost:
    text: str
    posted_at: datetime


async def fetch_channel_posts(channels: list[str], lookback_minutes: int) -> list[ChannelPost]:
    """Scrape the public t.me/s/<channel> preview page for each channel - this needs no
    bot admin rights and no personal Telegram account/login, since it's the same static
    HTML page anyone gets from a browser for a public channel. Returns only posts newer
    than lookback_minutes."""
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    posts: list[ChannelPost] = []

    async with httpx.AsyncClient(timeout=15, proxy=settings.outbound_proxy_url or None) as client:
        for channel in channels:
            try:
                response = await client.get(_CHANNEL_URL.format(channel=channel))
                response.raise_for_status()
            except httpx.HTTPError:
                logger.exception("Канал %s: не удалось получить %s", channel, _CHANNEL_URL.format(channel=channel))
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            blocks = soup.select("div.tgme_widget_message")
            if not blocks:
                logger.warning(
                    "Канал %s: страница получена (HTTP %s, %s байт), но постов на ней не нашлось - "
                    "проверь, что имя канала верное и он публичный",
                    channel, response.status_code, len(response.content),
                )
                continue

            fresh_count = 0
            for block in blocks:
                text_el = block.select_one(".tgme_widget_message_text")
                time_el = block.select_one("time.time")
                if text_el is None or time_el is None or not time_el.get("datetime"):
                    continue
                try:
                    posted_at = datetime.fromisoformat(time_el["datetime"])
                except ValueError:
                    continue
                if posted_at < cutoff:
                    continue
                text = text_el.get_text(" ", strip=True)
                if text:
                    posts.append(ChannelPost(text=text, posted_at=posted_at))
                    fresh_count += 1

            logger.info(
                "Канал %s: успешно распарсен, %s постов на странице, %s свежих за последние %s мин",
                channel, len(blocks), fresh_count, lookback_minutes,
            )

    logger.info(
        "Telegram-каналы (%s): всего %s свежих постов за %s мин",
        ", ".join(channels), len(posts), lookback_minutes,
    )
    return posts


def match_posts_for_ticker(posts: list[ChannelPost], ticker: str) -> list[str]:
    """Posts mentioning the company by name/alias, plus any broad macro/geopolitical
    post - both are treated as relevant to this ticker's near-term price."""
    aliases = [alias.lower() for alias in _TICKER_ALIASES.get(ticker.upper(), [])]
    aliases.append(ticker.lower())

    matched = []
    for post in posts:
        low = post.text.lower()
        if any(alias in low for alias in aliases) or any(keyword in low for keyword in _MACRO_KEYWORDS):
            matched.append(post.text)
    return matched
