import pandas as pd

from app.strategies.base import Action, Position, Signal, Strategy
from app.strategies.indicators import bollinger_bands


class BollingerBreakoutStrategy(Strategy):
    """Breakout: buy when price closes above the upper Bollinger band, exit when it falls
    back below the middle band (the moving average)."""

    name = "bollinger_breakout"

    def __init__(self, window: int = 20, window_dev: float = 2.0, **params):
        super().__init__(window=window, window_dev=window_dev, **params)
        self.window = window
        self.window_dev = window_dev

    def min_history_bars(self) -> int:
        return self.window + 1

    def generate_signal(self, df: pd.DataFrame, position: Position, context: dict | None = None) -> Signal:
        if len(df) < self.min_history_bars():
            return Signal(Action.HOLD, reason="недостаточно истории")

        upper, mid, _lower = bollinger_bands(df["close"], self.window, self.window_dev)
        close = df["close"]

        broke_out = close.iloc[-2] <= upper.iloc[-2] and close.iloc[-1] > upper.iloc[-1]

        if broke_out and not position.is_open:
            return Signal(Action.BUY, reason="Пробой верхней полосы Боллинджера")
        if position.is_open and close.iloc[-1] < mid.iloc[-1]:
            return Signal(Action.SELL, reason="Возврат к средней линии — выход из позиции")
        return Signal(Action.HOLD)
