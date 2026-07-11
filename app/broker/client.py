from contextlib import AbstractAsyncContextManager
from decimal import Decimal

from t_tech.invest import AsyncClient, MoneyValue
from t_tech.invest.sandbox.async_client import AsyncSandboxClient
from t_tech.invest.utils import decimal_to_quotation

from app.db.models import TradingMode

DEFAULT_SANDBOX_INITIAL_BALANCE_RUB = Decimal(100_000)


def client_context(token: str, mode: TradingMode) -> AbstractAsyncContextManager:
    """Return an async-context-manager T-Invest client for the given mode.

    Same call surface for both modes (orders, market_data, users, ...) - only the
    gRPC target differs, which is what lets strategies run unmodified in either.
    """
    if mode == TradingMode.SANDBOX:
        return AsyncSandboxClient(token)
    return AsyncClient(token)


async def ensure_account_id(client, mode: TradingMode, existing_account_id: str | None) -> str:
    """Return a usable account id for trading.

    Production: the user's own brokerage account (must already exist in their app).
    Sandbox: created and funded with virtual rubles on first use if not passed in.
    """
    if mode == TradingMode.PRODUCTION:
        accounts = (await client.users.get_accounts()).accounts
        if not accounts:
            raise RuntimeError("На этом токене не найдено ни одного брокерского счёта")
        return accounts[0].id

    if existing_account_id:
        return existing_account_id

    opened = await client.sandbox.open_sandbox_account()
    account_id = opened.account_id
    quotation = decimal_to_quotation(DEFAULT_SANDBOX_INITIAL_BALANCE_RUB)
    await client.sandbox.sandbox_pay_in(
        account_id=account_id,
        amount=MoneyValue(units=quotation.units, nano=quotation.nano, currency="rub"),
    )
    return account_id
