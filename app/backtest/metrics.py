from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.backtest.engine import BacktestResult


@dataclass
class BacktestMetrics:
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float | None
    num_trades: int
    win_rate_pct: float
    avg_trade_pnl_pct: float
    profit_factor: float | None


def compute_metrics(result: BacktestResult) -> BacktestMetrics:
    equity = result.equity_curve["equity"]
    initial = result.initial_capital
    final = result.final_equity
    total_return_pct = (final - initial) / initial * 100 if initial else 0.0

    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max * 100
    max_drawdown_pct = float(drawdown.min()) if not drawdown.empty else 0.0

    daily = result.equity_curve.copy()
    daily["date"] = pd.to_datetime(daily["time"]).dt.date
    daily_equity = daily.groupby("date")["equity"].last()
    daily_returns = daily_equity.pct_change().dropna()
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        sharpe_ratio = float(daily_returns.mean() / daily_returns.std() * np.sqrt(252))
    else:
        sharpe_ratio = None

    trades = result.trades
    num_trades = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate_pct = len(wins) / num_trades * 100 if num_trades else 0.0
    avg_trade_pnl_pct = sum(t.pnl_pct for t in trades) / num_trades if num_trades else 0.0

    gross_profit = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None

    return BacktestMetrics(
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe_ratio,
        num_trades=num_trades,
        win_rate_pct=win_rate_pct,
        avg_trade_pnl_pct=avg_trade_pnl_pct,
        profit_factor=profit_factor,
    )
