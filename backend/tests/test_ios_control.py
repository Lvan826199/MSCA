import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.drivers.base import ControlEvent
from app.drivers.ios import IOSDriver
from app.websocket.control import _build_ios_touch_event, _send_ios_event


class IOSDriverControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_tap_uses_w3c_actions_api(self):
        driver = IOSDriver("device-1", SimpleNamespace(wda_info=SimpleNamespace(host="127.0.0.1", port=8100)))
        driver._http = object()
        driver._session_id = "session-1"
        driver._post_wda = AsyncMock(return_value=True)

        success = await driver.send_event(ControlEvent("tap", {"x": 10, "y": 20}))

        self.assertTrue(success)
        driver._post_wda.assert_awaited_once()
        call_args = driver._post_wda.await_args
        self.assertEqual(call_args[0][0], "http://127.0.0.1:8100/session/session-1/actions")
        payload = call_args[0][1]
        self.assertIn("actions", payload)
        self.assertEqual(payload["actions"][0]["type"], "pointer")

    async def test_swipe_uses_w3c_actions_api(self):
        driver = IOSDriver("device-1", SimpleNamespace(wda_info=SimpleNamespace(host="127.0.0.1", port=8100)))
        driver._http = object()
        driver._session_id = "session-1"
        driver._post_wda = AsyncMock(return_value=True)

        success = await driver.send_event(ControlEvent("swipe", {"fromX": 10, "fromY": 20, "toX": 100, "toY": 200, "duration": 0.5}))

        self.assertTrue(success)
        driver._post_wda.assert_awaited_once()
        call_args = driver._post_wda.await_args
        self.assertEqual(call_args[0][0], "http://127.0.0.1:8100/session/session-1/actions")
        payload = call_args[0][1]
        self.assertIn("actions", payload)
        actions = payload["actions"][0]["actions"]
        self.assertEqual(actions[0]["type"], "pointerMove")
        self.assertEqual(actions[0]["x"], 10)
        self.assertEqual(actions[0]["y"], 20)

    def test_ios_touch_sequence_builds_tap_on_up_without_wda_touch_endpoint(self):
        state = {}

        down_event = _build_ios_touch_event("down", 10, 20, state)
        up_event = _build_ios_touch_event("up", 10, 20, state)

        self.assertIsNone(down_event)
        self.assertEqual(up_event.action, "tap")
        self.assertEqual(up_event.params, {"x": 10, "y": 20})
        self.assertEqual(state, {})

    def test_ios_touch_sequence_builds_swipe_after_move(self):
        state = {}

        self.assertIsNone(_build_ios_touch_event("down", 10, 20, state))
        self.assertIsNone(_build_ios_touch_event("move", 40, 80, state))
        up_event = _build_ios_touch_event("up", 45, 90, state)

        self.assertEqual(up_event.action, "swipe")
        self.assertEqual(up_event.params, {
            "fromX": 10,
            "fromY": 20,
            "toX": 45,
            "toY": 90,
            "duration": 0.3,
        })
        self.assertEqual(state, {})

    async def test_ios_touch_up_dispatches_tap_instead_of_wda_touch_up(self):
        driver = SimpleNamespace(send_event=AsyncMock(return_value=True), diagnose_control_failure=lambda: "hint")
        websocket = SimpleNamespace(send_json=AsyncMock())
        state = {}

        _build_ios_touch_event("down", 10, 20, state)
        event = _build_ios_touch_event("up", 10, 20, state)
        await _send_ios_event(driver, event, websocket, "iOS 触控动作失败")

        driver.send_event.assert_awaited_once_with(ControlEvent("tap", {"x": 10, "y": 20}))
        websocket.send_json.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
