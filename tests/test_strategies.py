import numpy as np
import pandas as pd

from app.strategies.base import Action, Position
from app.strategies.bollinger_breakout import BollingerBreakoutStrategy
from app.strategies.macd_momentum import MacdMomentumStrategy
from app.strategies.rsi_reversion import RsiReversionStrategy
from app.strategies.sma_cross import SmaCrossStrategy


def make_df(closes) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    times = pd.date_range("2024-01-02 10:00", periods=len(closes), freq="1min")
    return pd.DataFrame(
        {
            "time": times,
            "open": closes,
            "high": closes * 1.001,
            "low": closes * 0.999,
            "close": closes,
            "volume": 1000,
        }
    )


def run_over_series(strategy, df: pd.DataFrame) -> list:
    """Feed the strategy bar-by-bar, same as the backtest engine does, and collect signals."""
    position = Position()
    signals = []
    for i in range(strategy.min_history_bars() - 1, len(df)):
        visible = df.iloc[: i + 1]
        signal = strategy.generate_signal(visible, position, None)
        signals.append(signal)
        if signal.action == Action.BUY and not position.is_open:
            position = Position(is_open=True, entry_price=float(visible["close"].iloc[-1]), lots=1)
        elif signal.action == Action.SELL and position.is_open:
            position = Position()
    return signals


def test_sma_cross_buys_somewhere_in_the_uptrend_not_early_in_downtrend():
    down = np.linspace(100, 80, 40)
    up = np.linspace(80, 130, 60)
    df = make_df(np.concatenate([down, up]))
    strategy = SmaCrossStrategy(fast_window=5, slow_window=20)
    signals = run_over_series(strategy, df)
    assert any(s.action == Action.BUY for s in signals)
    assert not any(s.action == Action.BUY for s in signals[:15])


def test_rsi_reversion_buys_when_oversold():
    prices = np.concatenate([np.full(15, 100.0), np.linspace(100, 70, 20), np.full(10, 70.0)])
    df = make_df(prices)
    strategy = RsiReversionStrategy(window=14, oversold=30, overbought=70)
    signals = run_over_series(strategy, df)
    assert any(s.action == Action.BUY for s in signals)


def test_macd_momentum_buys_on_trend_reversal():
    down = np.linspace(120, 90, 40)
    up = np.linspace(90, 150, 50)
    df = make_df(np.concatenate([down, up]))
    strategy = MacdMomentumStrategy(window_fast=12, window_slow=26, window_sign=9)
    signals = run_over_series(strategy, df)
    assert any(s.action == Action.BUY for s in signals)


def test_bollinger_breakout_buys_on_breakout():
    flat = 100 + np.random.default_rng(0).normal(0, 0.3, 30)
    breakout = np.linspace(100, 140, 20)
    df = make_df(np.concatenate([flat, breakout]))
    strategy = BollingerBreakoutStrategy(window=20, window_dev=2.0)
    signals = run_over_series(strategy, df)
    assert any(s.action == Action.BUY for s in signals)


def test_strategies_hold_without_enough_history():
    df = make_df(np.full(3, 100.0))
    for strategy in [SmaCrossStrategy(), RsiReversionStrategy(), MacdMomentumStrategy(), BollingerBreakoutStrategy()]:
        signal = strategy.generate_signal(df, Position(), None)
        assert signal.action == Action.HOLD
