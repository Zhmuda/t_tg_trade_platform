from dataclasses import dataclass

import pandas as pd

from app.risk.guards import RiskLimits, apply_risk_guards, size_position
from app.strategies.base import Action, Position, Strategy


@dataclass
class SimulatedTrade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    lots: int
    pnl: float
    pnl_pct: float
    reason_entry: str
    reason_exit: str


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame  # columns: time, equity
    trades: list[SimulatedTrade]
    initial_capital: float
    open_position: Position

    @property
    def final_equity(self) -> float:
        if self.equity_curve.empty:
            return self.initial_capital
        return float(self.equity_curve["equity"].iloc[-1])


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    limits: RiskLimits,
    *,
    lot_size: int = 1,
    initial_capital: float = 100_000.0,
    commission_pct: float = 0.05,
    slippage_pct: float = 0.0,
    sentiment_context: dict | None = None,
) -> BacktestResult:
    """Replay df (ascending, complete bars only) bar-by-bar through strategy.

    A decision at bar i uses only data visible up to and including bar i; the resulting
    order fills at bar i+1's open, mirroring a real order placed right after the
    deciding candle closes - this avoids look-ahead bias from filling at the same
    close the decision was based on.
    """
    min_bars = strategy.min_history_bars()
    if len(df) < min_bars + 1:
        raise ValueError(f"Недостаточно свечей для бэктеста: нужно минимум {min_bars + 1}, получено {len(df)}")

    cash = initial_capital
    position = Position()
    entry_cost = 0.0  # total cash paid to open the current position, incl. commission/slippage
    trades: list[SimulatedTrade] = []
    equity_rows = []
    realized_pnl_today = 0.0
    day_start_equity = initial_capital
    current_day = None

    def fee(notional: float) -> float:
        return notional * (commission_pct + slippage_pct) / 100

    for i in range(min_bars - 1, len(df) - 1):
        visible = df.iloc[: i + 1]
        bar_time = visible["time"].iloc[-1]
        bar_day = pd.Timestamp(bar_time).date()
        if current_day is None or bar_day != current_day:
            current_day = bar_day
            mark_value = position.lots * lot_size * visible["close"].iloc[-1] if position.is_open else 0
            day_start_equity = cash + mark_value
            realized_pnl_today = 0.0

        current_price = float(visible["close"].iloc[-1])
        raw_signal = strategy.generate_signal(visible, position, sentiment_context)
        final_signal = apply_risk_guards(
            limits, raw_signal, position, current_price, realized_pnl_today, day_start_equity
        )

        next_bar = df.iloc[i + 1]
        fill_price = float(next_bar["open"])
        fill_time = pd.Timestamp(next_bar["time"])

        if final_signal.action == Action.BUY and not position.is_open:
            lots = size_position(limits, cash, fill_price * lot_size)
            if lots > 0:
                notional = fill_price * lot_size * lots
                cost = notional + fee(notional)
                if cost <= cash:
                    cash -= cost
                    entry_cost = cost
                    position = Position(is_open=True, entry_price=fill_price, lots=lots, entry_time=fill_time)

        elif final_signal.action == Action.SELL and position.is_open:
            notional = fill_price * lot_size * position.lots
            proceeds = notional - fee(notional)
            pnl = proceeds - entry_cost
            pnl_pct = pnl / entry_cost * 100 if entry_cost else 0.0
            cash += proceeds
            realized_pnl_today += pnl
            trades.append(
                SimulatedTrade(
                    entry_time=position.entry_time,
                    exit_time=fill_time,
                    entry_price=position.entry_price,
                    exit_price=fill_price,
                    lots=position.lots,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    reason_entry="",
                    reason_exit=final_signal.reason,
                )
            )
            position = Position()

        mark_value = position.lots * lot_size * current_price if position.is_open else 0
        equity_rows.append({"time": bar_time, "equity": cash + mark_value})

    last_price = float(df["close"].iloc[-1])
    mark_value = position.lots * lot_size * last_price if position.is_open else 0
    equity_rows.append({"time": df["time"].iloc[-1], "equity": cash + mark_value})

    equity_curve = pd.DataFrame(equity_rows).drop_duplicates(subset="time", keep="last").reset_index(drop=True)
    return BacktestResult(
        equity_curve=equity_curve, trades=trades, initial_capital=initial_capital, open_position=position
    )
