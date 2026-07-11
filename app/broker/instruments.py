import time
from dataclasses import dataclass
from decimal import Decimal

from t_tech.invest.utils import quotation_to_decimal

_CACHE_TTL_SECONDS = 6 * 60 * 60
_shares_cache: tuple[float, list] | None = None


@dataclass(frozen=True)
class InstrumentInfo:
    figi: str
    ticker: str
    name: str
    lot: int
    currency: str
    min_price_increment: Decimal


async def _all_shares(client) -> list:
    global _shares_cache
    now = time.monotonic()
    if _shares_cache is not None and now - _shares_cache[0] < _CACHE_TTL_SECONDS:
        return _shares_cache[1]
    instruments = (await client.instruments.shares()).instruments
    _shares_cache = (now, instruments)
    return instruments


async def resolve_ticker(client, ticker: str) -> InstrumentInfo:
    """Resolve a MOEX share ticker (e.g. SBER) to its FIGI and trading metadata."""
    ticker = ticker.strip().upper()
    for item in await _all_shares(client):
        if item.ticker == ticker:
            return InstrumentInfo(
                figi=item.figi,
                ticker=item.ticker,
                name=item.name,
                lot=item.lot,
                currency=item.currency,
                min_price_increment=quotation_to_decimal(item.min_price_increment),
            )
    raise ValueError(f"Тикер не найден среди акций Т-Инвестиций: {ticker}")
