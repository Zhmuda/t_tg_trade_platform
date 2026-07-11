import asyncio
import logging

from app.config import get_settings
from app.db.repository import active_tickers, upsert_sentiment
from app.db.session import get_session
from app.news.fetcher import fetch_articles
from app.news.sentiment import analyze_ticker_headlines

logger = logging.getLogger(__name__)


async def compute_ticker_sentiment(ticker: str, days: int = 3) -> tuple[float, int] | None:
    """Fetch recent news for `ticker` and return (score, headline_count), or None if no
    articles were found (e.g. no NEWSAPI_KEY/GEMINI_API_KEY configured, or nothing recent).

    All headlines go into a single Gemini request (see analyze_ticker_headlines) rather
    than one request per article, to stay well within free-tier rate limits.
    """
    articles = await fetch_articles(ticker, days=days)
    if not articles:
        return None

    headlines = []
    for article in articles:
        title = article.get("title") or ""
        description = article.get("description") or ""
        text = f"{title}. {description}".strip()
        if any(c.isalpha() for c in text):
            headlines.append(text)

    if not headlines:
        return None

    score = await analyze_ticker_headlines(ticker, headlines)
    if score is None:
        return None
    return score, len(headlines)


async def refresh_ticker_sentiment(ticker: str, days: int = 3) -> float | None:
    result = await compute_ticker_sentiment(ticker, days=days)
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

    while True:
        async with get_session() as session:
            tickers = await active_tickers(session)

        for ticker in tickers:
            try:
                await refresh_ticker_sentiment(ticker)
            except Exception:
                logger.exception("Не удалось обновить сентимент для %s", ticker)

        await asyncio.sleep(settings.sentiment_refresh_interval_seconds)
