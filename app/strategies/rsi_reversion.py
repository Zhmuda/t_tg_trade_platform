import pandas as pd

from app.strategies.base import Action, Position, Signal, Strategy
from app.strategies.indicators import rsi


class RsiReversionStrategy(Strategy):
    """Mean-reversion: buy when RSI signals oversold, sell when it signals overbought."""

    name = "rsi_reversion"

    def __init__(self, window: int = 14, oversold: float = 30.0, overbought: float = 70.0, **params):
        super().__init__(window=window, oversold=oversold, overbought=overbought, **params)
        self.window = window
        self.oversold = oversold
        self.overbought = overbought

    def min_history_bars(self) -> int:
        return self.window + 1

    def generate_signal(self, df: pd.DataFrame, position: Position, context: dict | None = None) -> Signal:
        if len(df) < self.min_history_bars():
            return Signal(Action.HOLD, reason="недостаточно истории")

        current = rsi(df["close"], self.window).iloc[-1]

        if current < self.oversold and not position.is_open:
            return Signal(Action.BUY, reason=f"RSI {current:.1f} < {self.oversold} (перепродан)")
        if current > self.overbought and position.is_open:
            return Signal(Action.SELL, reason=f"RSI {current:.1f} > {self.overbought} (перекуплен)")
        return Signal(Action.HOLD)
