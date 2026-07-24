import asyncio
import logging

from app.config import get_settings
from app.db.repository import active_tickers, upsert_sentiment
from app.db.session import get_session
from app.news.fetcher import fetch_articles
from app.news.sentiment import analyze_ticker_headlines
from app.news.telegram_channel import ChannelPost, fetch_channel_posts, match_posts_for_ticker

logger = logging.getLogger(__name__)


async def compute_ticker_sentiment(
    ticker: str, days: int = 3, channel_posts: list[ChannelPost] | None = None
) -> tuple[float, int] | None:
    """Fetch recent news for `ticker` and return (score, headline_count), or None if
    nothing was found (e.g. no NEWSAPI_KEY/GEMINI_API_KEY configured, or nothing recent).

    Combines NewsAPI headlines with any matching Telegram channel posts (see
    app/news/telegram_channel.py) into a single Gemini request rather than one request
    per item, to stay well within free-tier rate limits.
    """
    articles = await fetch_articles(ticker, days=days)

    headlines = []
    for article in articles:
        title = article.get("title") or ""
        description = article.get("description") or ""
        text = f"{title}. {description}".strip()
        if any(c.isalpha() for c in text):
            headlines.append(text)

    matched_posts = match_posts_for_ticker(channel_posts, ticker) if channel_posts else []
    if matched_posts:
        headlines.extend(matched_posts)

    logger.info(
        "%s: %s заголовков NewsAPI + %s постов из Telegram-каналов -> %s всего",
        ticker, len(articles), len(matched_posts), len(headlines),
    )

    if not headlines:
        return None

    score = await analyze_ticker_headlines(ticker, headlines)
    if score is None:
        return None
    return score, len(headlines)


async def refresh_ticker_sentiment(
    ticker: str, days: int = 3, channel_posts: list[ChannelPost] | None = None
) -> float | None:
    result = await compute_ticker_sentiment(ticker, days=days, channel_posts=channel_posts)
    if result is None:
        return None
    avg_score, sample_size = result
    async with get_session() as session:
        await upsert_sentiment(session, ticker, avg_score, sample_size)
    return avg_score


async def run_sentiment_worker() -> None:
    """Background loop: keep SentimentScore cache fresh for every ticker with a
    currently-running strategy instance (see app/strategies/sentiment_filter.py for how
    the cached score is consumed)."""
    settings = get_settings()
    if not settings.newsapi_key or not settings.gemini_api_key:
        logger.warning(
            "NEWSAPI_KEY и/или GEMINI_API_KEY не заданы — фоновое обновление новостного сентимента отключено"
        )
        return

    channels = settings.news_telegram_channel_list
    if channels:
        logger.info("Telegram-каналы для новостного сентимента: %s", ", ".join(channels))
    else:
        logger.info("NEWS_TELEGRAM_CHANNELS не задан — источник постов из Telegram-каналов отключён")
    # Overlap window wider than the refresh interval so a slow cycle (or one that starts
    # a little late) doesn't miss a post that landed right before the previous fetch.
    lookback_minutes = max(15, 2 * settings.sentiment_refresh_interval_seconds // 60)

    while True:
        async with get_session() as session:
            tickers = await active_tickers(session)

        channel_posts: list[ChannelPost] = []
        if tickers and channels:
            try:
                channel_posts = await fetch_channel_posts(channels, lookback_minutes)
            except Exception:
                logger.exception("Не удалось обновить посты Telegram-каналов")

        for ticker in tickers:
            try:
                await refresh_ticker_sentiment(ticker, channel_posts=channel_posts)
            except Exception:
                logger.exception("Не удалось обновить сентимент для %s", ticker)

        await asyncio.sleep(settings.sentiment_refresh_interval_seconds)
