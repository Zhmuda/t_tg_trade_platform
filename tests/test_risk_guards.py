from app.risk.guards import RiskLimits, apply_risk_guards, check_stop_loss_take_profit, daily_loss_exceeded, size_position
from app.strategies.base import Action, Position, Signal


def test_size_position_caps_by_max_lots_and_cash():
    limits = RiskLimits(max_position_lots=5)
    assert size_position(limits, available_cash=1000, price_per_lot=100) == 5
    assert size_position(limits, available_cash=250, price_per_lot=100) == 2
    assert size_position(limits, available_cash=1000, price_per_lot=0) == 0


def test_stop_loss_triggers_sell():
    limits = RiskLimits(stop_loss_pct=1.0, take_profit_pct=2.0)
    position = Position(is_open=True, entry_price=100.0, lots=1)
    signal = check_stop_loss_take_profit(limits, position, current_price=98.5)
    assert signal is not None
    assert signal.action == Action.SELL


def test_take_profit_triggers_sell():
    limits = RiskLimits(stop_loss_pct=1.0, take_profit_pct=2.0)
    position = Position(is_open=True, entry_price=100.0, lots=1)
    signal = check_stop_loss_take_profit(limits, position, current_price=102.5)
    assert signal is not None
    assert signal.action == Action.SELL


def test_no_forced_exit_within_band():
    limits = RiskLimits(stop_loss_pct=1.0, take_profit_pct=2.0)
    position = Position(is_open=True, entry_price=100.0, lots=1)
    assert check_stop_loss_take_profit(limits, position, current_price=100.5) is None


def test_no_forced_exit_when_position_closed():
    limits = RiskLimits(stop_loss_pct=1.0, take_profit_pct=2.0)
    assert check_stop_loss_take_profit(limits, Position(), current_price=50.0) is None


def test_daily_loss_exceeded_boundary():
    limits = RiskLimits(max_daily_loss_pct=3.0)
    assert daily_loss_exceeded(limits, realized_pnl_today=-3000, day_start_equity=100_000) is True
    assert daily_loss_exceeded(limits, realized_pnl_today=-2000, day_start_equity=100_000) is False


def test_apply_risk_guards_blocks_buy_after_daily_loss_limit():
    limits = RiskLimits(max_daily_loss_pct=3.0, stop_loss_pct=50, take_profit_pct=50)
    signal = apply_risk_guards(
        limits,
        Signal(Action.BUY),
        Position(),
        current_price=100.0,
        realized_pnl_today=-5000,
        day_start_equity=100_000,
    )
    assert signal.action == Action.HOLD


def test_apply_risk_guards_forces_exit_over_strategy_hold():
    limits = RiskLimits(stop_loss_pct=1.0, take_profit_pct=50)
    position = Position(is_open=True, entry_price=100.0, lots=1)
    signal = apply_risk_guards(
        limits, Signal(Action.HOLD), position, current_price=98.0, realized_pnl_today=0, day_start_equity=100_000
    )
    assert signal.action == Action.SELL


def test_apply_risk_guards_blocks_duplicate_buy_when_already_open():
    limits = RiskLimits(stop_loss_pct=50, take_profit_pct=50)
    position = Position(is_open=True, entry_price=100.0, lots=1)
    signal = apply_risk_guards(
        limits, Signal(Action.BUY), position, current_price=100.2, realized_pnl_today=0, day_start_equity=100_000
    )
    assert signal.action == Action.HOLD
