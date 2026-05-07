import asyncio
import unittest

from app.websocket.control import _cancel_and_await_tasks


class ControlTaskCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_and_await_tasks_waits_for_cancellation_cleanup(self):
        cleaned = False

        async def worker():
            nonlocal cleaned
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cleaned = True
                raise

        task = asyncio.create_task(worker())
        await asyncio.sleep(0)

        await _cancel_and_await_tasks([task])

        self.assertTrue(cleaned)
        self.assertTrue(task.cancelled())


if __name__ == "__main__":
    unittest.main()
