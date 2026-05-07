import asyncio
import unittest

from app.core.device_manager import DeviceManager


class DeviceManagerStopTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_async_awaits_cancelled_poll_task(self):
        manager = DeviceManager()
        cancelled = False

        async def poll_forever():
            nonlocal cancelled
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled = True
                raise

        manager._poll_task = asyncio.create_task(poll_forever())
        await asyncio.sleep(0)

        await manager.stop_async()

        self.assertTrue(cancelled)
        self.assertIsNone(manager._poll_task)
        self.assertTrue(manager._subscribers == [])


if __name__ == "__main__":
    unittest.main()
