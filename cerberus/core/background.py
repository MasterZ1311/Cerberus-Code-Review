"""
Thread-safe and loop-aware background task management.
Prevents premature garbage collection of in-flight tasks in Python 3.11+,
retrieves and logs unhandled task exceptions to eliminate 'Task exception was never retrieved',
and provides safe draining and cancellation during application shutdown or test teardown.
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional, Set

logger = logging.getLogger("cerberus.background")


class BackgroundTaskManager:
    """
    Manages background tasks across event loops safely.
    - Prevents premature GC of background tasks in Python 3.11+.
    - Retrieves task.exception() on completion to avoid 'Task exception was never retrieved'.
    - Scopes task draining per event loop so tasks do not cross test boundaries.
    - Gracefully drains or cancels active tasks during shutdown.
    """

    def __init__(self) -> None:
        self._tasks: Set[asyncio.Task[Any]] = set()

    def create_task(
        self,
        coro: Coroutine[Any, Any, Any],
        name: Optional[str] = None,
        on_error: Optional[Callable[[BaseException], None]] = None,
    ) -> asyncio.Task[Any]:
        """Create and track a background task on the current running event loop."""
        self._prune_stale_tasks()

        loop = asyncio.get_running_loop()
        task_name = name or getattr(coro, "__name__", "background_task")
        task = loop.create_task(coro, name=task_name)
        self._tasks.add(task)

        def _on_done(t: asyncio.Task[Any]) -> None:
            self._tasks.discard(t)
            if t.cancelled():
                return
            try:
                exc = t.exception()
            except asyncio.CancelledError:
                return
            except Exception as read_err:
                logger.warning("Error inspecting background task %s: %s", t.get_name(), read_err)
                return

            if exc:
                if on_error:
                    try:
                        on_error(exc)
                    except Exception:
                        pass
                logger.error(
                    "Background task '%s' failed with unhandled exception: %s: %s",
                    t.get_name(),
                    type(exc).__name__,
                    exc,
                    exc_info=exc,
                )

        task.add_done_callback(_on_done)
        return task

    def _prune_stale_tasks(self) -> None:
        """Remove tasks that are done or whose event loop is closed."""
        stale = set()
        for t in list(self._tasks):
            try:
                if t.done() or t.get_loop().is_closed():
                    stale.add(t)
            except Exception:
                stale.add(t)
        self._tasks.difference_update(stale)

    async def drain_tasks(
        self,
        timeout: float = 5.0,
        cancel: bool = False,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """
        Drain active tasks associated with the target event loop (defaults to current running loop).
        If cancel is True, cancels them before waiting.
        """
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return

        target_tasks = [
            t for t in list(self._tasks) if not t.done() and not t.get_loop().is_closed() and t.get_loop() is loop
        ]

        if not target_tasks:
            return

        if cancel:
            for t in target_tasks:
                t.cancel()

        try:
            await asyncio.wait_for(
                asyncio.gather(*target_tasks, return_exceptions=True),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning("Timed out draining %s background tasks after %ss.", len(target_tasks), timeout)
            for t in target_tasks:
                if not t.done():
                    t.cancel()
        except Exception as e:
            logger.warning("Exception while draining background tasks: %s", e)
        finally:
            self._prune_stale_tasks()


# Global singleton instance
background_tasks = BackgroundTaskManager()
