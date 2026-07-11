from app.strategies.base import Strategy
from app.strategies.bollinger_breakout import BollingerBreakoutStrategy
from app.strategies.macd_momentum import MacdMomentumStrategy
from app.strategies.rsi_reversion import RsiReversionStrategy
from app.strategies.sentiment_filter import SentimentFilteredStrategy
from app.strategies.sma_cross import SmaCrossStrategy

BASE_STRATEGIES: dict[str, type[Strategy]] = {
    SmaCrossStrategy.name: SmaCrossStrategy,
    RsiReversionStrategy.name: RsiReversionStrategy,
    MacdMomentumStrategy.name: MacdMomentumStrategy,
    BollingerBreakoutStrategy.name: BollingerBreakoutStrategy,
}


def available_strategy_names() -> list[str]:
    return list(BASE_STRATEGIES)


def create_strategy(name: str, params: dict | None = None, use_sentiment_filter: bool = False) -> Strategy:
    """Build a strategy instance by its registered name.

    params are forwarded to the strategy's constructor. Set use_sentiment_filter=True to
    wrap it with SentimentFilteredStrategy (min_sentiment can be passed inside params).
    """
    params = dict(params or {})
    if name not in BASE_STRATEGIES:
        raise ValueError(f"Неизвестная стратегия: {name}. Доступные: {', '.join(available_strategy_names())}")

    min_sentiment = params.pop("min_sentiment", -0.05)
    strategy = BASE_STRATEGIES[name](**params)

    if use_sentiment_filter:
        return SentimentFilteredStrategy(base_strategy=strategy, min_sentiment=min_sentiment)
    return strategy
