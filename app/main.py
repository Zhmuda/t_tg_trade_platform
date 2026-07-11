import asyncio
import logging

from app.bootstrap import provision_owner_tokens_from_env
from app.bot.dispatcher import build_bot_and_dispatcher
from app.db.repository import reset_stale_running_instances
from app.db.session import get_session, init_db
from app.news.worker import run_sentiment_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    await init_db()
    await provision_owner_tokens_from_env()

    async with get_session() as session:
        reset_count = await reset_stale_running_instances(session)
    if reset_count:
        logger.info("Сброшен статус %s стратегий, оставшихся 'running' с прошлого запуска процесса", reset_count)

    bot, dp = build_bot_and_dispatcher()

    await asyncio.gather(
        run_sentiment_worker(),
        dp.start_polling(bot),
    )


if __name__ == "__main__":
    asyncio.run(main())
