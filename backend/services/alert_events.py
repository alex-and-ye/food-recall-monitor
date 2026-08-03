"""In-process pub/sub broadcaster for alert-change notifications.

Used by SSE endpoints so clients can react when new alerts or early-warning
incidents are persisted, with optional keepalive yields for idle connections.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

KEEPALIVE_INTERVAL_SECONDS = 30.0  # Default idle timeout before yielding a keepalive.


@dataclass(frozen=True)
class AlertsChangedEvent:
    """Payload describing how many new alerts were saved.

    Attributes:
        saved_count: Number of newly persisted alerts in this notification.
    """

    saved_count: int


class AlertChangeBroadcaster:
    """Fan-out alert-change events to async subscriber queues."""

    def __init__(self) -> None:
        """Initialize subscriber tracking and the coordination lock."""
        self._subscribers: set[asyncio.Queue[AlertsChangedEvent | None]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> AsyncIterator[AlertsChangedEvent]:
        """Yield events until the subscriber is cancelled or closed.

        Yields:
            AlertsChangedEvent instances as they are published.

        Note:
            A None sentinel ends the stream; it is not yielded to callers.
        """
        queue: asyncio.Queue[AlertsChangedEvent | None] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def iter_with_keepalive(
        self,
        interval_seconds: float = KEEPALIVE_INTERVAL_SECONDS,
    ) -> AsyncIterator[AlertsChangedEvent | None]:
        """Yield events, or None when no event arrives within the interval.

        Args:
            interval_seconds: Seconds to wait before emitting a keepalive None.

        Yields:
            AlertsChangedEvent for real updates, or None as a keepalive pulse.
        """
        queue: asyncio.Queue[AlertsChangedEvent | None] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=interval_seconds)
                except asyncio.TimeoutError:
                    yield None
                    continue

                if event is None:
                    break
                yield event
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    def notify(self, saved_count: int) -> None:
        """Publish a change event to all current subscribers.

        Args:
            saved_count: Number of alerts saved; ignored when non-positive.
        """
        if saved_count <= 0:
            return

        event = AlertsChangedEvent(saved_count=saved_count)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
