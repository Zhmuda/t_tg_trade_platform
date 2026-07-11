from dataclasses import dataclass

from app.strategies.base import Action, Position, Signal


@dataclass
class RiskLimits:
    max_position_lots: int = 1
    stop_loss_pct: float = 1.0  # exit if price falls this % below entry
    take_profit_pct: float = 2.0  # exit if price rises this % above entry
    max_daily_loss_pct: float = 3.0  # block new entries once today's realized loss hits this % of day-start equity


def size_position(limits: RiskLimits, available_cash: float, price_per_lot: float) -> int:
    """Lots to buy, capped by both the configured max and available cash."""
    if price_per_lot <= 0:
        return 0
    affordable = int(available_cash // price_per_lot)
    return max(0, min(limits.max_position_lots, affordable))


def check_stop_loss_take_profit(limits: RiskLimits, position: Position, current_price: float) -> Signal | None:
    """Forced-exit check that always overrides the strategy's own HOLD/BUY signal."""
    if not position.is_open or position.entry_price is None:
        return None

    change_pct = (current_price - position.entry_price) / position.entry_price * 100

    if change_pct <= -limits.stop_loss_pct:
        return Signal(Action.SELL, reason=f"Стоп-лосс: {change_pct:.2f}% <= -{limits.stop_loss_pct}%")
    if change_pct >= limits.take_profit_pct:
        return Signal(Action.SELL, reason=f"Тейк-профит: {change_pct:.2f}% >= {limits.take_profit_pct}%")
    return None


def daily_loss_exceeded(limits: RiskLimits, realized_pnl_today: float, day_start_equity: float) -> bool:
    if day_start_equity <= 0:
        return False
    loss_pct = -realized_pnl_today / day_start_equity * 100
    return loss_pct >= limits.max_daily_loss_pct


def apply_risk_guards(
    limits: RiskLimits,
    strategy_signal: Signal,
    position: Position,
    current_price: float,
    realized_pnl_today: float,
    day_start_equity: float,
) -> Signal:
    """Combine the strategy's raw signal with mandatory risk checks.

    Used by both the backtest engine and the live/demo execution engine so backtested
    results reflect the same guardrails that would apply to real money.
    """
    forced_exit = check_stop_loss_take_profit(limits, position, current_price)
    if forced_exit is not None:
        return forced_exit

    if strategy_signal.action == Action.BUY:
        if position.is_open:
            return Signal(Action.HOLD, reason="уже есть открытая позиция")
        if daily_loss_exceeded(limits, realized_pnl_today, day_start_equity):
            return Signal(Action.HOLD, reason="достигнут дневной лимит убытка — новые входы заблокированы")

    return strategy_signal
