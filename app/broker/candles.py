from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from t_tech.invest import CandleInterval, HistoricCandle
from t_tech.invest.utils import quotation_to_decimal

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OHLCV_COLUMNS = ["time", "open", "high", "low", "close", "volume"]


def _cache_path(figi: str, interval: CandleInterval) -> Path:
    return CACHE_DIR / f"{figi}_{interval.name}.pkl"


def _candle_to_row(candle: HistoricCandle) -> dict:
    return {
        "time": candle.time,
        "open": float(quotation_to_decimal(candle.open)),
        "high": float(quotation_to_decimal(candle.high)),
        "low": float(quotation_to_decimal(candle.low)),
        "close": float(quotation_to_decimal(candle.close)),
        "volume": candle.volume,
    }


async def get_candles_df(
    client, figi: str, from_: datetime, to: datetime, interval: CandleInterval
) -> pd.DataFrame:
    """Historical OHLCV candles as a DataFrame, backed by an incrementally-updated local cache.

    Only complete (closed) candles are kept, since the currently-forming candle would
    otherwise leak an unstable bar into both the backtest and the live strategy input.
    """
    path = _cache_path(figi, interval)
    cached = pd.read_pickle(path) if path.exists() else pd.DataFrame(columns=OHLCV_COLUMNS)

    fetch_from = from_
    if not cached.empty:
        cached_max = pd.Timestamp(cached["time"].max())
        if cached_max.tzinfo is None:
            cached_max = cached_max.tz_localize(timezone.utc)
        fetch_from = max(from_, cached_max.to_pydatetime())

    rows = []
    if fetch_from < to:
        async for candle in client.get_all_candles(
            instrument_id=figi, from_=fetch_from, to=to, interval=interval
        ):
            if candle.is_complete:
                rows.append(_candle_to_row(candle))

    if rows:
        fresh = pd.DataFrame(rows)
        combined = pd.concat([cached, fresh], ignore_index=True)
        combined = combined.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)
        combined.to_pickle(path)
    else:
        combined = cached

    if combined.empty:
        return combined

    from_ts = pd.Timestamp(from_)
    to_ts = pd.Timestamp(to)
    mask = (combined["time"] >= from_ts) & (combined["time"] <= to_ts)
    return combined.loc[mask].reset_index(drop=True)
