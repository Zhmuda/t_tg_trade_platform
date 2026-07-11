import enum
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Enum, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TradingMode(str, enum.Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class StrategyStatus(str, enum.Enum):
    STOPPED = "stopped"
    RUNNING = "running"


class OrderDirection(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    credentials: Mapped[list["BrokerCredential"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    strategy_instances: Mapped[list["StrategyInstance"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    backtest_runs: Mapped[list["BacktestRun"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class BrokerCredential(Base):
    """A user's T-Invest API token for one mode (sandbox or production), encrypted at rest."""

    __tablename__ = "broker_credentials"
    __table_args__ = (UniqueConstraint("user_id", "mode", name="uq_broker_credential_user_mode"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    mode: Mapped[TradingMode] = mapped_column(Enum(TradingMode))
    encrypted_token: Mapped[str] = mapped_column(String)
    account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="credentials")


class StrategyInstance(Base):
    """A configured (strategy, instrument, mode) combination a user can run live or demo."""

    __tablename__ = "strategy_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    strategy_name: Mapped[str] = mapped_column(String)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    ticker: Mapped[str] = mapped_column(String)
    figi: Mapped[str] = mapped_column(String)
    mode: Mapped[TradingMode] = mapped_column(Enum(TradingMode))
    status: Mapped[StrategyStatus] = mapped_column(Enum(StrategyStatus), default=StrategyStatus.STOPPED)

    max_position_lots: Mapped[int] = mapped_column(default=1)
    stop_loss_pct: Mapped[float] = mapped_column(Float, default=1.0)
    take_profit_pct: Mapped[float] = mapped_column(Float, default=2.0)
    max_daily_loss_pct: Mapped[float] = mapped_column(Float, default=3.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="strategy_instances")
    orders: Mapped[list["Order"]] = relationship(back_populates="strategy_instance", cascade="all, delete-orphan")
    trades: Mapped[list["Trade"]] = relationship(back_populates="strategy_instance", cascade="all, delete-orphan")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_instance_id: Mapped[int] = mapped_column(ForeignKey("strategy_instances.id"))
    broker_order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    direction: Mapped[OrderDirection] = mapped_column(Enum(OrderDirection))
    lots: Mapped[int] = mapped_column()
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="submitted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    strategy_instance: Mapped["StrategyInstance"] = relationship(back_populates="orders")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_instance_id: Mapped[int] = mapped_column(ForeignKey("strategy_instances.id"))
    ticker: Mapped[str] = mapped_column(String)
    direction: Mapped[OrderDirection] = mapped_column(Enum(OrderDirection))
    lots: Mapped[int] = mapped_column()
    price: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    strategy_instance: Mapped["StrategyInstance"] = relationship(back_populates="trades")


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    strategy_name: Mapped[str] = mapped_column(String)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    ticker: Mapped[str] = mapped_column(String)
    date_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    date_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="backtest_runs")


class SentimentScore(Base):
    """Cached news-sentiment score per ticker, refreshed periodically by the news worker."""

    __tablename__ = "sentiment_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    score: Mapped[float] = mapped_column(Float)  # in [-1, 1], negative..positive
    sample_size: Mapped[int] = mapped_column(default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
