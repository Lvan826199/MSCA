import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.drivers.base import ControlEvent
from app.drivers.ios import IOSDriver


class IOSDriverControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_tap_uses_wda_tap_endpoint(self):
        driver = IOSDriver("device-1", SimpleNamespace(wda_info=SimpleNamespace(host="127.0.0.1", port=8100)))
        driver._http = object()
        driver._session_id = "session-1"
        driver._post_wda = AsyncMock(return_value=True)

        success = await driver.send_event(ControlEvent("tap", {"x": 10, "y": 20}))

        self.assertTrue(success)
        driver._post_wda.assert_awaited_once_with(
            "http://127.0.0.1:8100/session/session-1/wda/tap/0",
            {"x": 10, "y": 20},
        )

    async def test_touch_down_falls_back_to_tap_when_wda_touch_endpoint_fails(self):
        driver = IOSDriver("device-1", SimpleNamespace(wda_info=SimpleNamespace(host="127.0.0.1", port=8100)))
        driver._http = object()
        driver._session_id = "session-1"
        driver._post_wda = AsyncMock(side_effect=[False, True])

        success = await driver.send_event(ControlEvent("touch", {"action": "down", "x": 10, "y": 20}))

        self.assertTrue(success)
        self.assertEqual(driver._post_wda.await_count, 2)
        driver._post_wda.assert_any_await(
            "http://127.0.0.1:8100/session/session-1/wda/touch/down",
            {"x": 10, "y": 20},
        )
        driver._post_wda.assert_any_await(
            "http://127.0.0.1:8100/session/session-1/wda/tap/0",
            {"x": 10, "y": 20},
        )


if __name__ == "__main__":
    unittest.main()
