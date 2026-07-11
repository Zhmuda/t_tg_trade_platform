import pandas as pd

from app.strategies.base import Action, Position, Signal, Strategy
from app.strategies.indicators import macd


class MacdMomentumStrategy(Strategy):
    """Momentum: go long when MACD crosses above its signal line, exit on the reverse cross."""

    name = "macd_momentum"

    def __init__(self, window_fast: int = 12, window_slow: int = 26, window_sign: int = 9, **params):
        super().__init__(window_fast=window_fast, window_slow=window_slow, window_sign=window_sign, **params)
        self.window_fast = window_fast
        self.window_slow = window_slow
        self.window_sign = window_sign

    def min_history_bars(self) -> int:
        return self.window_slow + self.window_sign + 1

    def generate_signal(self, df: pd.DataFrame, position: Position, context: dict | None = None) -> Signal:
        if len(df) < self.min_history_bars():
            return Signal(Action.HOLD, reason="недостаточно истории")

        macd_line, signal_line, _ = macd(df["close"], self.window_slow, self.window_fast, self.window_sign)
        prev_diff = macd_line.iloc[-2] - signal_line.iloc[-2]
        curr_diff = macd_line.iloc[-1] - signal_line.iloc[-1]

        if prev_diff <= 0 < curr_diff and not position.is_open:
            return Signal(Action.BUY, reason="MACD пересёк сигнальную линию снизу вверх")
        if prev_diff >= 0 > curr_diff and position.is_open:
            return Signal(Action.SELL, reason="MACD пересёк сигнальную линию сверху вниз")
        return Signal(Action.HOLD)
