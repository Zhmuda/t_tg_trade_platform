from app.strategies.base import Strategy
from app.strategies.bollinger_breakout import BollingerBreakoutStrategy
from app.strategies.macd_momentum import MacdMomentumStrategy
from app.strategies.rsi_reversion import RsiReversionStrategy
from app.strategies.sentiment_filter import SentimentFilteredStrategy
from app.strategies.sma_cross import SmaCrossStrategy, SmaCrossTestStrategy

BASE_STRATEGIES: dict[str, type[Strategy]] = {
    SmaCrossStrategy.name: SmaCrossStrategy,
    SmaCrossTestStrategy.name: SmaCrossTestStrategy,
    RsiReversionStrategy.name: RsiReversionStrategy,
    MacdMomentumStrategy.name: MacdMomentumStrategy,
    BollingerBreakoutStrategy.name: BollingerBreakoutStrategy,
}


def available_strategy_names() -> list[str]:
    return list(BASE_STRATEGIES)


def create_strategy(name: str, params: dict | None = None, use_sentiment_filter: bool | None = None) -> Strategy:
    """Build a strategy instance by its registered name.

    Remaining params are forwarded to the strategy's constructor. use_sentiment_filter and
    min_sentiment can be passed either as explicit kwargs here or embedded in params (the
    latter is how StrategyInstance.params round-trips the choice made in the bot's
    /demo, /trade and /backtest flows - see app/bot/handlers/trading.py and backtest.py)
    - wraps the strategy with SentimentFilteredStrategy when enabled.
    """
    params = dict(params or {})
    if name not in BASE_STRATEGIES:
        raise ValueError(f"Неизвестная стратегия: {name}. Доступные: {', '.join(available_strategy_names())}")

    min_sentiment = params.pop("min_sentiment", -0.05)
    params_use_sentiment = params.pop("use_sentiment_filter", False)
    if use_sentiment_filter is None:
        use_sentiment_filter = params_use_sentiment
    strategy = BASE_STRATEGIES[name](**params)

    if use_sentiment_filter:
        return SentimentFilteredStrategy(base_strategy=strategy, min_sentiment=min_sentiment)
    return strategy
