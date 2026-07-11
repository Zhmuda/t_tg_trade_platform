import pandas as pd

from app.strategies.base import Action, Position, Signal, Strategy
from app.strategies.indicators import sma


class SmaCrossStrategy(Strategy):
    """Trend-following: go long when the fast SMA crosses above the slow SMA, exit on the
    reverse cross."""

    name = "sma_cross"

    def __init__(self, fast_window: int = 10, slow_window: int = 30, **params):
        super().__init__(fast_window=fast_window, slow_window=slow_window, **params)
        self.fast_window = fast_window
        self.slow_window = slow_window

    def min_history_bars(self) -> int:
        return self.slow_window + 1

    def generate_signal(self, df: pd.DataFrame, position: Position, context: dict | None = None) -> Signal:
        if len(df) < self.min_history_bars():
            return Signal(Action.HOLD, reason="недостаточно истории")

        close = df["close"]
        fast = sma(close, self.fast_window)
        slow = sma(close, self.slow_window)
        prev_fast, prev_slow = fast.iloc[-2], slow.iloc[-2]
        curr_fast, curr_slow = fast.iloc[-1], slow.iloc[-1]

        crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
        crossed_down = prev_fast >= prev_slow and curr_fast < curr_slow

        if crossed_up and not position.is_open:
            return Signal(Action.BUY, reason=f"SMA{self.fast_window} пересекла SMA{self.slow_window} снизу вверх")
        if crossed_down and position.is_open:
            return Signal(Action.SELL, reason=f"SMA{self.fast_window} пересекла SMA{self.slow_window} сверху вниз")
        return Signal(Action.HOLD)


class SmaCrossTestStrategy(SmaCrossStrategy):
    """Same crossover logic as SmaCrossStrategy but with much shorter windows (2/5 bars
    instead of 10/30), so on 1-minute candles crossovers - and orders - happen within
    minutes instead of potentially never during a short test session. For validating the
    demo/live order-placement pipeline end-to-end, not for real trading."""

    name = "sma_cross_test"

    def __init__(self, fast_window: int = 2, slow_window: int = 5, **params):
        super().__init__(fast_window=fast_window, slow_window=slow_window, **params)
