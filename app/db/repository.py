from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crypto import encrypt_token
from app.db.models import (
    BacktestRun,
    BrokerCredential,
    Order,
    OrderDirection,
    SentimentScore,
    StrategyInstance,
    StrategyStatus,
    Trade,
    TradingMode,
    User,
)


async def get_or_create_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        user = User(id=user_id)
        session.add(user)
        await session.commit()
    return user


async def save_broker_credential(
    session: AsyncSession, user_id: int, mode: TradingMode, token: str, account_id: str | None = None
) -> BrokerCredential:
    await get_or_create_user(session, user_id)
    stmt = select(BrokerCredential).where(BrokerCredential.user_id == user_id, BrokerCredential.mode == mode)
    credential = (await session.execute(stmt)).scalar_one_or_none()
    encrypted = encrypt_token(token)
    if credential is None:
        credential = BrokerCredential(user_id=user_id, mode=mode, encrypted_token=encrypted, account_id=account_id)
        session.add(credential)
    else:
        credential.encrypted_token = encrypted
        if account_id is not None:
            credential.account_id = account_id
    await session.commit()
    return credential


async def get_broker_credential(session: AsyncSession, user_id: int, mode: TradingMode) -> BrokerCredential | None:
    stmt = select(BrokerCredential).where(BrokerCredential.user_id == user_id, BrokerCredential.mode == mode)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_strategy_instance(
    session: AsyncSession,
    *,
    user_id: int,
    strategy_name: str,
    params: dict,
    ticker: str,
    figi: str,
    mode: TradingMode,
    max_position_lots: int = 1,
    stop_loss_pct: float = 1.0,
    take_profit_pct: float = 2.0,
    max_daily_loss_pct: float = 3.0,
) -> StrategyInstance:
    instance = StrategyInstance(
        user_id=user_id,
        strategy_name=strategy_name,
        params=params,
        ticker=ticker,
        figi=figi,
        mode=mode,
        max_position_lots=max_position_lots,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        max_daily_loss_pct=max_daily_loss_pct,
    )
    session.add(instance)
    await session.commit()
    return instance


async def list_strategy_instances(
    session: AsyncSession, user_id: int, status: StrategyStatus | None = None
) -> list[StrategyInstance]:
    stmt = select(StrategyInstance).where(StrategyInstance.user_id == user_id)
    if status is not None:
        stmt = stmt.where(StrategyInstance.status == status)
    return list((await session.execute(stmt)).scalars().all())


async def set_strategy_status(session: AsyncSession, instance_id: int, status: StrategyStatus) -> None:
    instance = await session.get(StrategyInstance, instance_id)
    if instance is not None:
        instance.status = status
        await session.commit()


async def reset_stale_running_instances(session: AsyncSession) -> int:
    """Mark every RUNNING instance as STOPPED. Call once at process startup: a RUNNING
    row left over from a previous process means there's no asyncio task actually driving
    it anymore, so it must not be reported as live."""
    stmt = select(StrategyInstance).where(StrategyInstance.status == StrategyStatus.RUNNING)
    instances = list((await session.execute(stmt)).scalars().all())
    for instance in instances:
        instance.status = StrategyStatus.STOPPED
    if instances:
        await session.commit()
    return len(instances)


async def record_order(
    session: AsyncSession,
    *,
    strategy_instance_id: int,
    direction: OrderDirection,
    lots: int,
    price: float | None,
    broker_order_id: str | None,
    status: str = "submitted",
) -> Order:
    order = Order(
        strategy_instance_id=strategy_instance_id,
        direction=direction,
        lots=lots,
        price=price,
        broker_order_id=broker_order_id,
        status=status,
    )
    session.add(order)
    await session.commit()
    return order


async def record_trade(
    session: AsyncSession,
    *,
    strategy_instance_id: int,
    ticker: str,
    direction: OrderDirection,
    lots: int,
    price: float,
    pnl: float | None = None,
    opened_at: datetime | None = None,
) -> Trade:
    now = datetime.now(timezone.utc)
    trade = Trade(
        strategy_instance_id=strategy_instance_id,
        ticker=ticker,
        direction=direction,
        lots=lots,
        price=price,
        pnl=pnl,
        opened_at=opened_at or now,
        closed_at=now,
    )
    session.add(trade)
    await session.commit()
    return trade


async def latest_order(session: AsyncSession, strategy_instance_id: int) -> Order | None:
    """Most recent order for a strategy instance - a trailing BUY with no later SELL
    means the strategy is currently holding an open position."""
    stmt = (
        select(Order)
        .where(Order.strategy_instance_id == strategy_instance_id)
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def todays_realized_pnl(session: AsyncSession, strategy_instance_id: int) -> float:
    """Sum of pnl for trades closed today (UTC) for this strategy instance.

    Backed by the trade log rather than an in-memory counter so the daily-loss guard
    survives a process restart mid-session.
    """
    today = datetime.now(timezone.utc).date()
    stmt = select(Trade).where(Trade.strategy_instance_id == strategy_instance_id)
    trades = (await session.execute(stmt)).scalars().all()
    return sum(t.pnl or 0.0 for t in trades if t.closed_at and t.closed_at.date() == today)


async def save_backtest_run(
    session: AsyncSession,
    *,
    user_id: int,
    strategy_name: str,
    params: dict,
    ticker: str,
    date_from: datetime,
    date_to: datetime,
    metrics: dict,
) -> BacktestRun:
    await get_or_create_user(session, user_id)
    run = BacktestRun(
        user_id=user_id,
        strategy_name=strategy_name,
        params=params,
        ticker=ticker,
        date_from=date_from,
        date_to=date_to,
        metrics=metrics,
    )
    session.add(run)
    await session.commit()
    return run


async def active_tickers(session: AsyncSession) -> list[str]:
    """Distinct tickers with at least one currently-running strategy instance."""
    stmt = select(StrategyInstance.ticker).where(StrategyInstance.status == StrategyStatus.RUNNING).distinct()
    return list((await session.execute(stmt)).scalars().all())


async def latest_sentiment(session: AsyncSession, ticker: str) -> SentimentScore | None:
    stmt = (
        select(SentimentScore)
        .where(SentimentScore.ticker == ticker)
        .order_by(SentimentScore.computed_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert_sentiment(session: AsyncSession, ticker: str, score: float, sample_size: int) -> SentimentScore:
    entry = SentimentScore(ticker=ticker, score=score, sample_size=sample_size, computed_at=datetime.now(timezone.utc))
    session.add(entry)
    await session.commit()
    return entry
