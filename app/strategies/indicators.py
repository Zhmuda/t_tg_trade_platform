import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, SMAIndicator
from ta.volatility import BollingerBands


def sma(series: pd.Series, window: int) -> pd.Series:
    return SMAIndicator(close=series, window=window).sma_indicator()


def ema(series: pd.Series, window: int) -> pd.Series:
    return EMAIndicator(close=series, window=window).ema_indicator()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    return RSIIndicator(close=series, window=window).rsi()


def macd(
    series: pd.Series, window_slow: int = 26, window_fast: int = 12, window_sign: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    indicator = MACD(close=series, window_slow=window_slow, window_fast=window_fast, window_sign=window_sign)
    return indicator.macd(), indicator.macd_signal(), indicator.macd_diff()


def bollinger_bands(series: pd.Series, window: int = 20, window_dev: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    indicator = BollingerBands(close=series, window=window, window_dev=window_dev)
    return indicator.bollinger_hband(), indicator.bollinger_mavg(), indicator.bollinger_lband()
