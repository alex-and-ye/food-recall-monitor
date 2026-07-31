import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

KEEPALIVE_INTERVAL_SECONDS = 30.0

@dataclass(frozen=True)
class AlertsChangedEvent:
    saved_count: int

class AlertChangeBroadcaster:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[AlertsChangedEvent | None]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> AsyncIterator[AlertsChangedEvent]:
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
        if saved_count <= 0:
            return

        event = AlertsChangedEvent(saved_count=saved_count)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
