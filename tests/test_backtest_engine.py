import pandas as pd
import pytest

from app.backtest.engine import run_backtest
from app.risk.guards import RiskLimits
from app.strategies.base import Action, Position, Signal, Strategy


class DummyAlwaysFlipStrategy(Strategy):
    """Buys whenever flat, sells whenever holding - isolates the engine's fill/PnL
    mechanics from any real indicator behaviour."""

    name = "dummy_flip"

    def min_history_bars(self) -> int:
        return 1

    def generate_signal(self, df, position: Position, context=None) -> Signal:
        if position.is_open:
            return Signal(Action.SELL, reason="flip sell")
        return Signal(Action.BUY, reason="flip buy")


def make_df(opens, closes) -> pd.DataFrame:
    times = pd.date_range("2024-01-02 10:00", periods=len(opens), freq="1min")
    return pd.DataFrame(
        {
            "time": times,
            "open": opens,
            "high": [max(o, c) for o, c in zip(opens, closes)],
            "low": [min(o, c) for o, c in zip(opens, closes)],
            "close": closes,
            "volume": 1000,
        }
    )


def test_backtest_engine_fills_at_next_bar_open_and_computes_pnl():
    opens = [100, 102, 104, 106, 108]
    closes = [101, 103, 105, 107, 109]
    df = make_df(opens, closes)

    limits = RiskLimits(max_position_lots=1, stop_loss_pct=50, take_profit_pct=50, max_daily_loss_pct=50)
    result = run_backtest(df, DummyAlwaysFlipStrategy(), limits, lot_size=1, initial_capital=100_000, commission_pct=0)

    assert len(result.trades) == 2

    first, second = result.trades
    assert first.entry_price == 102 and first.exit_price == 104 and first.pnl == 2
    assert second.entry_price == 106 and second.exit_price == 108 and second.pnl == 2

    assert result.open_position.is_open is False
    assert result.final_equity == pytest.approx(100_004)


def test_backtest_engine_applies_commission():
    opens = [100, 102, 104]
    closes = [101, 103, 105]
    df = make_df(opens, closes)

    limits = RiskLimits(max_position_lots=1, stop_loss_pct=50, take_profit_pct=50, max_daily_loss_pct=50)
    result = run_backtest(df, DummyAlwaysFlipStrategy(), limits, lot_size=1, initial_capital=100_000, commission_pct=1.0)

    # buys at 102 (cost 102 * 1.01), sells at 104 (proceeds 104 * 0.99)
    trade = result.trades[0]
    expected_pnl = (104 * 0.99) - (102 * 1.01)
    assert trade.pnl == pytest.approx(expected_pnl)


def test_backtest_engine_raises_on_insufficient_history():
    df = make_df([100], [101])
    limits = RiskLimits()
    with pytest.raises(ValueError):
        run_backtest(df, DummyAlwaysFlipStrategy(), limits)
