import logging
from datetime import timedelta
from uuid import uuid4

import pandas as pd
from t_tech.invest import (
    CandleInstrument,
    CandleInterval,
    OrderDirection as ApiOrderDirection,
    OrderType,
    SubscriptionInterval,
)
from t_tech.invest.utils import now, quotation_to_decimal

from app.broker.candles import get_candles_df
from app.broker.client import client_context, ensure_account_id
from app.broker.instruments import resolve_ticker
from app.db.crypto import decrypt_token
from app.db.models import OrderDirection as DbOrderDirection, StrategyInstance, TradingMode
from app.db.repository import (
    get_broker_credential,
    latest_sentiment,
    record_order,
    record_trade,
    save_broker_credential,
    todays_realized_pnl,
)
from app.db.session import get_session
from app.risk.guards import RiskLimits, apply_risk_guards, size_position
from app.strategies.base import Action, Position
from app.strategies.registry import create_strategy

logger = logging.getLogger(__name__)

_STREAM_INTERVAL = SubscriptionInterval.SUBSCRIPTION_INTERVAL_ONE_MINUTE
_HISTORY_INTERVAL = CandleInterval.CANDLE_INTERVAL_1_MIN
_WARMUP_DAYS = 5
_MAX_BUFFER_BARS = 500


def _candle_row(candle) -> dict:
    return {
        "time": candle.time,
        "open": float(quotation_to_decimal(candle.open)),
        "high": float(quotation_to_decimal(candle.high)),
        "low": float(quotation_to_decimal(candle.low)),
        "close": float(quotation_to_decimal(candle.close)),
        "volume": candle.volume,
    }


def _rub_balance(positions_response) -> float:
    for money in positions_response.money:
        if money.currency == "rub":
            return float(quotation_to_decimal(money))
    return 0.0


async def _place_market_order(client, account_id: str, figi: str, lots: int, direction):
    try:
        return await client.orders.post_order(
            quantity=lots,
            direction=direction,
            account_id=account_id,
            order_type=OrderType.ORDER_TYPE_MARKET,
            order_id=str(uuid4()),
            instrument_id=figi,
        )
    except Exception:
        logger.exception("Не удалось выставить заявку figi=%s lots=%s", figi, lots)
        return None


async def run_strategy_instance(instance_id: int) -> None:
    """Drive one (user, strategy, instrument, mode) combination off a live candle stream
    until cancelled. Same Strategy + risk-guard code as the backtester (see
    app/backtest/engine.py) so demo and real trading behave exactly as validated."""

    async with get_session() as session:
        instance = await session.get(StrategyInstance, instance_id)
        if instance is None:
            raise RuntimeError(f"Strategy instance {instance_id} not found")
        credential = await get_broker_credential(session, instance.user_id, instance.mode)
        if credential is None:
            raise RuntimeError("Нет сохранённого токена Т-Инвестиций для этого режима")
        token = decrypt_token(credential.encrypted_token)
        account_id = credential.account_id
        limits = RiskLimits(
            max_position_lots=instance.max_position_lots,
            stop_loss_pct=instance.stop_loss_pct,
            take_profit_pct=instance.take_profit_pct,
            max_daily_loss_pct=instance.max_daily_loss_pct,
        )
        strategy = create_strategy(instance.strategy_name, instance.params)

    async with client_context(token, instance.mode) as client:
        account_id = await ensure_account_id(client, instance.mode, account_id)
        if instance.mode == TradingMode.SANDBOX and account_id != credential.account_id:
            async with get_session() as session:
                await save_broker_credential(session, instance.user_id, instance.mode, token, account_id=account_id)

        instrument = await resolve_ticker(client, instance.ticker)
        lot_size = instrument.lot

        warmup_from = now() - timedelta(days=_WARMUP_DAYS)
        buffer = await get_candles_df(client, instance.figi, warmup_from, now(), _HISTORY_INTERVAL)
        buffer = buffer.tail(_MAX_BUFFER_BARS).reset_index(drop=True)

        position = Position()
        realized_pnl_today = 0.0
        day_start_equity: float | None = None
        current_day = None

        stream = client.create_market_data_stream()
        stream.candles.waiting_close().subscribe(
            [CandleInstrument(figi=instance.figi, interval=_STREAM_INTERVAL)]
        )

        logger.info(
            "Started strategy instance %s: %s on %s (%s)", instance_id, instance.strategy_name, instance.ticker, instance.mode
        )

        async for marketdata in stream:
            candle = marketdata.candle
            if candle is None:
                continue

            row = _candle_row(candle)
            buffer = pd.concat([buffer, pd.DataFrame([row])], ignore_index=True)
            buffer = buffer.drop_duplicates(subset="time", keep="last").tail(_MAX_BUFFER_BARS).reset_index(drop=True)

            if len(buffer) < strategy.min_history_bars():
                continue

            trading_status = await client.market_data.get_trading_status(figi=instance.figi)
            if not (trading_status.market_order_available_flag and trading_status.api_trade_available_flag):
                continue

            positions_response = await client.operations.get_positions(account_id=account_id)
            available_cash = _rub_balance(positions_response)

            bar_day = pd.Timestamp(row["time"]).date()
            if current_day is None or bar_day != current_day:
                current_day = bar_day
                async with get_session() as session:
                    realized_pnl_today = await todays_realized_pnl(session, instance_id)
                mark_value = position.lots * lot_size * row["close"] if position.is_open else 0
                day_start_equity = available_cash + mark_value

            async with get_session() as session:
                sentiment = await latest_sentiment(session, instance.ticker)
            context = {"sentiment_score": sentiment.score if sentiment else None}

            raw_signal = strategy.generate_signal(buffer, position, context)
            final_signal = apply_risk_guards(
                limits, raw_signal, position, row["close"], realized_pnl_today, day_start_equity or available_cash
            )

            if final_signal.action == Action.BUY and not position.is_open:
                lots = size_position(limits, available_cash, row["close"] * lot_size)
                if lots <= 0:
                    continue
                response = await _place_market_order(
                    client, account_id, instance.figi, lots, ApiOrderDirection.ORDER_DIRECTION_BUY
                )
                if response is None:
                    continue
                fill_price = (
                    float(quotation_to_decimal(response.executed_order_price))
                    if response.executed_order_price
                    else row["close"]
                )
                position = Position(is_open=True, entry_price=fill_price, lots=lots, entry_time=pd.Timestamp(row["time"]))
                async with get_session() as session:
                    await record_order(
                        session,
                        strategy_instance_id=instance_id,
                        direction=DbOrderDirection.BUY,
                        lots=lots,
                        price=fill_price,
                        broker_order_id=response.order_id,
                    )
                logger.info("BUY %s lots=%s price=%.2f reason=%s", instance.ticker, lots, fill_price, raw_signal.reason)

            elif final_signal.action == Action.SELL and position.is_open:
                response = await _place_market_order(
                    client, account_id, instance.figi, position.lots, ApiOrderDirection.ORDER_DIRECTION_SELL
                )
                if response is None:
                    continue
                fill_price = (
                    float(quotation_to_decimal(response.executed_order_price))
                    if response.executed_order_price
                    else row["close"]
                )
                pnl = (fill_price - position.entry_price) * position.lots * lot_size
                realized_pnl_today += pnl
                async with get_session() as session:
                    await record_order(
                        session,
                        strategy_instance_id=instance_id,
                        direction=DbOrderDirection.SELL,
                        lots=position.lots,
                        price=fill_price,
                        broker_order_id=response.order_id,
                    )
                    await record_trade(
                        session,
                        strategy_instance_id=instance_id,
                        ticker=instance.ticker,
                        direction=DbOrderDirection.SELL,
                        lots=position.lots,
                        price=fill_price,
                        pnl=pnl,
                        opened_at=position.entry_time,
                    )
                logger.info(
                    "SELL %s lots=%s price=%.2f pnl=%.2f reason=%s",
                    instance.ticker,
                    position.lots,
                    fill_price,
                    pnl,
                    final_signal.reason,
                )
                position = Position()
