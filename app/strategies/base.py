from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Action(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Position:
    """Current position state as seen by a strategy. Long-only for v1 (no short-selling)."""

    is_open: bool = False
    entry_price: float | None = None
    lots: int = 0
    entry_time: pd.Timestamp | None = None


@dataclass
class Signal:
    action: Action
    reason: str = ""


class Strategy(ABC):
    """Given price history up to "now" and the current position, decide buy/sell/hold.

    Implementations must be pure functions of (df, position, context): the same
    generate_signal call is used by the backtest engine replaying history and by the
    live/demo execution engine reacting to a real-time candle stream, so behaviour is
    identical in both — the point of a "demo mode" is that it faithfully rehearses what
    real trading would do.
    """

    name: str

    def __init__(self, **params):
        self.params = params

    @abstractmethod
    def min_history_bars(self) -> int:
        """Minimum number of bars needed in df before generate_signal can decide anything."""

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, position: Position, context: dict | None = None) -> Signal:
        """df has columns time/open/high/low/close/volume, sorted ascending by time.

        context carries optional side signals (e.g. {"sentiment_score": -0.3}).
        """
