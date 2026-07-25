import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.db.repository import all_user_ids, list_strategy_instances, todays_realized_pnl
from app.db.session import get_session
from app.notifications import notify_user

logger = logging.getLogger(__name__)


def _seconds_until_next_run(hour_utc: int) -> float:
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _send_digest_for_user(user_id: int) -> None:
    async with get_session() as session:
        instances = await list_strategy_instances(session, user_id)

    lines = []
    total_today = 0.0
    for inst in instances:
        async with get_session() as session:
            pnl = await todays_realized_pnl(session, inst.id)
        if pnl == 0.0:
            continue
        total_today += pnl
        lines.append(f"#{inst.id} {inst.strategy_name} · {inst.ticker} ({inst.mode.value}): {pnl:+.2f} руб.")

    if not lines:
        # Nothing closed today for this user - skip the notification rather than spam an
        # empty "0.00 руб." digest every evening.
        return

    text = "📅 Итоги дня по вашим стратегиям:\n\n" + "\n".join(lines) + f"\n\nВсего за сегодня: {total_today:+.2f} руб."
    await notify_user(user_id, text)


async def run_daily_digest_worker() -> None:
    """Background loop: once a day, at settings.daily_digest_hour_utc, message every user
    with a same-day P&L summary across their strategies (demo and real together, each
    line tagged with its mode) - see app/db/repository.todays_realized_pnl for the
    per-instance query this is built from."""
    settings = get_settings()
    if settings.daily_digest_hour_utc < 0:
        logger.info("Ежедневный дайджест P&L отключён (DAILY_DIGEST_HOUR_UTC < 0)")
        return

    while True:
        delay = _seconds_until_next_run(settings.daily_digest_hour_utc)
        logger.info("Следующий дайджест P&L через %.0f сек. (%.1f ч.)", delay, delay / 3600)
        await asyncio.sleep(delay)

        try:
            async with get_session() as session:
                user_ids = await all_user_ids(session)
            for user_id in user_ids:
                try:
                    await _send_digest_for_user(user_id)
                except Exception:
                    logger.exception("Не удалось отправить дайджест пользователю %s", user_id)
        except Exception:
            logger.exception("Ошибка в цикле ежедневного дайджеста")
