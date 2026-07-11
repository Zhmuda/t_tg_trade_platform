import logging

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


class _SentimentResult(BaseModel):
    score: float = Field(description="Overall sentiment from -1 (very negative) to 1 (very positive)")
    reasoning: str = Field(description="One short sentence explaining the score")


def _get_client() -> genai.Client | None:
    global _client
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def analyze_ticker_headlines(ticker: str, headlines: list[str]) -> float | None:
    """One aggregate sentiment score (-1..1) across all headlines for a ticker, via a
    single Gemini request - far cheaper on rate limits than scoring each headline
    separately, handles Russian and English text alike, and needs no local ML runtime
    (unlike a locally-hosted BERT model, which would need ~1.5-2GB RAM this bot's
    hosting doesn't have)."""
    client = _get_client()
    if client is None or not headlines:
        return None

    numbered = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(headlines[:30]))
    prompt = (
        f"Ты финансовый аналитик. Вот последние заголовки новостей об акции {ticker} "
        f"на Московской бирже:\n\n{numbered}\n\n"
        "Оцени общую тональность этих новостей для держателя акции: насколько они "
        "позитивны или негативны для будущей цены."
    )

    try:
        response = await client.aio.models.generate_content(
            model=get_settings().gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_SentimentResult,
                temperature=0.0,
            ),
        )
        result: _SentimentResult = response.parsed
        return max(-1.0, min(1.0, result.score))
    except Exception:
        logger.exception("Не удалось получить сентимент от Gemini для %s", ticker)
        return None
