import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.backtest.engine import BacktestResult  # noqa: E402
from app.backtest.metrics import BacktestMetrics  # noqa: E402


def render_equity_curve_png(result: BacktestResult) -> bytes:
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(result.equity_curve["time"], result.equity_curve["equity"])
    ax.set_title("Кривая капитала")
    ax.set_xlabel("Время")
    ax.set_ylabel("Капитал, руб.")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_text_summary(strategy_name: str, ticker: str, result: BacktestResult, metrics: BacktestMetrics) -> str:
    sharpe = f"{metrics.sharpe_ratio:.2f}" if metrics.sharpe_ratio is not None else "н/д (мало данных)"
    lines = [
        f"Бэктест: {strategy_name} на {ticker}",
        f"Начальный капитал: {result.initial_capital:,.0f} руб.",
        f"Итоговый капитал: {result.final_equity:,.0f} руб.",
        f"Доходность: {metrics.total_return_pct:+.2f}%",
        f"Макс. просадка: {metrics.max_drawdown_pct:.2f}%",
        f"Коэфф. Шарпа: {sharpe}",
        f"Сделок: {metrics.num_trades}",
        f"Win rate: {metrics.win_rate_pct:.1f}%",
        f"Средний результат сделки: {metrics.avg_trade_pnl_pct:+.2f}%",
    ]
    if metrics.profit_factor is not None:
        lines.append(f"Profit factor: {metrics.profit_factor:.2f}")
    if result.open_position.is_open:
        lines.append(
            f"На конец периода осталась открытая позиция: {result.open_position.lots} лот(ов) "
            f"по {result.open_position.entry_price:.2f} — не учтена как закрытая сделка"
        )
    return "\n".join(lines)
