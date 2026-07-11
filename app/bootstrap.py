import logging

from app.config import get_settings
from app.db.models import TradingMode
from app.db.repository import save_broker_credential
from app.db.session import get_session

logger = logging.getLogger(__name__)


async def provision_owner_tokens_from_env() -> None:
    """Optional convenience for single-user setups: load T-Invest tokens straight from
    .env (OWNER_TELEGRAM_ID + TINKOFF_SANDBOX_TOKEN/TINKOFF_PRODUCTION_TOKEN) instead of
    requiring /start in Telegram. Re-applied on every startup - editing .env and
    restarting the bot updates the stored token too. Multi-user /start onboarding still
    works unchanged for anyone else who talks to the bot.
    """
    settings = get_settings()
    if settings.owner_telegram_id is None:
        return

    async with get_session() as session:
        if settings.tinkoff_sandbox_token:
            await save_broker_credential(
                session, settings.owner_telegram_id, TradingMode.SANDBOX, settings.tinkoff_sandbox_token
            )
            logger.info("Sandbox-токен владельца (OWNER_TELEGRAM_ID) загружен из .env")
        if settings.tinkoff_production_token:
            await save_broker_credential(
                session, settings.owner_telegram_id, TradingMode.PRODUCTION, settings.tinkoff_production_token
            )
            logger.info("Production-токен владельца (OWNER_TELEGRAM_ID) загружен из .env")
