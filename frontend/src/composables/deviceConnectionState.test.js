import test from "node:test"
import assert from "node:assert/strict"

import { shouldOpenDeviceSocket, buildDevicesApiUrl } from "./deviceConnectionState.js"

test("shouldOpenDeviceSocket blocks duplicate open or connecting device sockets", () => {
  assert.equal(shouldOpenDeviceSocket(null), true)
  assert.equal(shouldOpenDeviceSocket({ readyState: 0 }), false)
  assert.equal(shouldOpenDeviceSocket({ readyState: 1 }), false)
  assert.equal(shouldOpenDeviceSocket({ readyState: 2 }), true)
  assert.equal(shouldOpenDeviceSocket({ readyState: 3 }), true)
})

test("buildDevicesApiUrl supports relative and remote backend URLs", () => {
  assert.equal(buildDevicesApiUrl(""), "/api/devices")
  assert.equal(buildDevicesApiUrl("https://example.com/api"), "https://example.com/api/api/devices")
})
