import pandas as pd
import pytest

from app.strategies.base import Action, Position, Signal, Strategy
from app.strategies.registry import create_strategy
from app.strategies.sentiment_filter import SentimentFilteredStrategy


class AlwaysBuyStrategy(Strategy):
    name = "always_buy"

    def min_history_bars(self) -> int:
        return 1

    def generate_signal(self, df, position, context=None) -> Signal:
        return Signal(Action.BUY, reason="always buy")


class AlwaysSellStrategy(Strategy):
    name = "always_sell"

    def min_history_bars(self) -> int:
        return 1

    def generate_signal(self, df, position, context=None) -> Signal:
        return Signal(Action.SELL, reason="always sell")


def _df() -> pd.DataFrame:
    return pd.DataFrame({"time": pd.date_range("2024-01-02", periods=1), "close": [100.0]})


def test_sentiment_filter_suppresses_buy_on_negative_sentiment():
    wrapped = SentimentFilteredStrategy(AlwaysBuyStrategy(), min_sentiment=-0.05)
    signal = wrapped.generate_signal(_df(), Position(), {"sentiment_score": -0.5})
    assert signal.action == Action.HOLD


def test_sentiment_filter_allows_buy_on_positive_sentiment():
    wrapped = SentimentFilteredStrategy(AlwaysBuyStrategy(), min_sentiment=-0.05)
    signal = wrapped.generate_signal(_df(), Position(), {"sentiment_score": 0.5})
    assert signal.action == Action.BUY


def test_sentiment_filter_allows_buy_when_sentiment_unknown():
    wrapped = SentimentFilteredStrategy(AlwaysBuyStrategy(), min_sentiment=-0.05)
    assert wrapped.generate_signal(_df(), Position(), None).action == Action.BUY
    assert wrapped.generate_signal(_df(), Position(), {}).action == Action.BUY


def test_sentiment_filter_never_touches_sell_signals():
    wrapped = SentimentFilteredStrategy(AlwaysSellStrategy(), min_sentiment=-0.05)
    signal = wrapped.generate_signal(_df(), Position(is_open=True, entry_price=100.0, lots=1), {"sentiment_score": -0.9})
    assert signal.action == Action.SELL


def test_registry_unknown_strategy_raises():
    with pytest.raises(ValueError):
        create_strategy("does_not_exist")


def test_registry_wraps_with_sentiment_filter():
    strategy = create_strategy("sma_cross", params={"min_sentiment": -0.1}, use_sentiment_filter=True)
    assert isinstance(strategy, SentimentFilteredStrategy)
    assert strategy.name == "sma_cross+sentiment"
    assert strategy.min_sentiment == -0.1


def test_registry_without_sentiment_filter_returns_base_strategy():
    strategy = create_strategy("rsi_reversion")
    assert strategy.name == "rsi_reversion"
