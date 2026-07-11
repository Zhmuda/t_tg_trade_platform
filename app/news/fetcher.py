import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

NEWSAPI_URL = "https://newsapi.org/v2/everything"


async def fetch_articles(query: str, days: int = 3, page_size: int = 50) -> list[dict]:
    """Fetch recent articles mentioning `query` from NewsAPI.org. Returns [] if no key
    is configured or the request fails, so callers can treat "no sentiment" as neutral."""
    settings = get_settings()
    if not settings.newsapi_key:
        return []

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    params = {
        "q": query,
        "from": start_date.strftime("%Y-%m-%d"),
        "to": end_date.strftime("%Y-%m-%d"),
        "sortBy": "relevancy",
        "pageSize": page_size,
        "apiKey": settings.newsapi_key,
    }

    async with httpx.AsyncClient(timeout=15, proxy=settings.outbound_proxy_url or None) as client:
        try:
            response = await client.get(NEWSAPI_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Запрос к NewsAPI не удался (query=%s) - сеть/блокировка/лимит?", query)
            return []
        data = response.json()

    if data.get("status") != "ok":
        logger.warning("NewsAPI вернул status=%s для query=%s: %s", data.get("status"), query, data.get("message"))
        return []

    articles = data.get("articles", [])
    logger.info("NewsAPI: %s статей по запросу %s (totalResults=%s)", len(articles), query, data.get("totalResults"))
    return articles
