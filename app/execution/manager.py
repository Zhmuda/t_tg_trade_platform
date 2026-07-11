import asyncio
import logging

from app.db.models import StrategyStatus
from app.db.repository import set_strategy_status
from app.db.session import get_session
from app.execution.engine import run_strategy_instance

logger = logging.getLogger(__name__)

_tasks: dict[int, asyncio.Task] = {}


def is_running(instance_id: int) -> bool:
    task = _tasks.get(instance_id)
    return task is not None and not task.done()


def running_instance_ids() -> list[int]:
    return [instance_id for instance_id, task in _tasks.items() if not task.done()]


async def start(instance_id: int) -> bool:
    """Start a strategy instance in the background. Returns False if already running."""
    if is_running(instance_id):
        return False

    async def _runner() -> None:
        try:
            await run_strategy_instance(instance_id)
        except asyncio.CancelledError:
            logger.info("Strategy instance %s stopped", instance_id)
            raise
        except Exception:
            logger.exception("Strategy instance %s crashed", instance_id)
        finally:
            async with get_session() as session:
                await set_strategy_status(session, instance_id, StrategyStatus.STOPPED)

    task = asyncio.create_task(_runner(), name=f"strategy-{instance_id}")
    _tasks[instance_id] = task
    async with get_session() as session:
        await set_strategy_status(session, instance_id, StrategyStatus.RUNNING)
    return True


async def stop(instance_id: int) -> bool:
    """Cancel a running strategy instance. Returns False if it wasn't running."""
    task = _tasks.pop(instance_id, None)
    if task is None:
        return False
    task.cancel()
    async with get_session() as session:
        await set_strategy_status(session, instance_id, StrategyStatus.STOPPED)
    return True


async def stop_all() -> int:
    """Emergency stop: cancel every running strategy instance. Returns how many were stopped."""
    stopped = 0
    for instance_id in list(_tasks):
        if await stop(instance_id):
            stopped += 1
    return stopped
