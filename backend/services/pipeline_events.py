import asyncio
from collections.abc import AsyncIterator

from models.pipeline_run_status import PipelineProgressSnapshot

KEEPALIVE_INTERVAL_SECONDS = 15.0


class PipelineProgressBroadcaster:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[PipelineProgressSnapshot | None]] = set()
        self._lock = asyncio.Lock()

    async def iter_with_keepalive(
        self,
        interval_seconds: float = KEEPALIVE_INTERVAL_SECONDS,
    ) -> AsyncIterator[PipelineProgressSnapshot | None]:
        queue: asyncio.Queue[PipelineProgressSnapshot | None] = asyncio.Queue(maxsize=32)
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

    def notify(self, snapshot: PipelineProgressSnapshot) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(snapshot)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(snapshot)
                except asyncio.QueueFull:
                    pass
