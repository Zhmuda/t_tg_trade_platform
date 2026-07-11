import pandas as pd

from app.strategies.base import Action, Position, Signal, Strategy


class SentimentFilteredStrategy(Strategy):
    """Wraps any base strategy and suppresses its BUY signals when cached news sentiment
    for the ticker is below a threshold. Reads context["sentiment_score"] (range -1..1),
    populated by the news worker's cache - see app/news/worker.py."""

    def __init__(self, base_strategy: Strategy, min_sentiment: float = -0.05, **params):
        super().__init__(min_sentiment=min_sentiment, **params)
        self.base_strategy = base_strategy
        self.min_sentiment = min_sentiment
        self.name = f"{base_strategy.name}+sentiment"

    def min_history_bars(self) -> int:
        return self.base_strategy.min_history_bars()

    def generate_signal(self, df: pd.DataFrame, position: Position, context: dict | None = None) -> Signal:
        signal = self.base_strategy.generate_signal(df, position, context)
        if signal.action != Action.BUY:
            return signal

        sentiment_score = (context or {}).get("sentiment_score")
        if sentiment_score is not None and sentiment_score < self.min_sentiment:
            return Signal(
                Action.HOLD,
                reason=f"Сигнал BUY подавлен новостным сентиментом ({sentiment_score:.2f} < {self.min_sentiment})",
            )
        return signal
