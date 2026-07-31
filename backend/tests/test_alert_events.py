import asyncio
import unittest

from services.alert_events import AlertChangeBroadcaster

class AlertChangeBroadcasterTests(unittest.IsolatedAsyncioTestCase):
    async def test_notify_delivers_event_to_subscriber(self) -> None:
        broadcaster = AlertChangeBroadcaster()

        async def read_one() -> int:
            async for event in broadcaster.subscribe():
                return event.saved_count
            return 0

        reader = asyncio.create_task(read_one())
        await asyncio.sleep(0)
        broadcaster.notify(2)

        saved_count = await asyncio.wait_for(reader, timeout=1.0)
        self.assertEqual(saved_count, 2)

    async def test_notify_ignores_zero_or_negative_counts(self) -> None:
        broadcaster = AlertChangeBroadcaster()
        subscriber = broadcaster.subscribe()

        broadcaster.notify(0)
        broadcaster.notify(-1)

        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(anext(subscriber), timeout=0.05)

        await subscriber.aclose()

    async def test_iter_with_keepalive_emits_none_on_timeout(self) -> None:
        broadcaster = AlertChangeBroadcaster()
        stream = broadcaster.iter_with_keepalive(interval_seconds=0.05)

        keepalive = await asyncio.wait_for(anext(stream), timeout=1.0)
        self.assertIsNone(keepalive)

        broadcaster.notify(1)
        event = await asyncio.wait_for(anext(stream), timeout=1.0)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.saved_count, 1)

        await stream.aclose()

if __name__ == "__main__":
    unittest.main()
