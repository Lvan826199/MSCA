import test from "node:test"
import assert from "node:assert/strict"

import { getConnectionState, setMode, setRemoteUrl, getBackendUrl, toWsUrl } from "./useConnection.js"

test("useConnection uses normalized persisted remote URL for REST and WebSocket URLs", () => {
  setMode("remote")
  setRemoteUrl("wss://example.com/api/")

  assert.deepEqual(getConnectionState(), {
    mode: "remote",
    remoteUrl: "https://example.com/api",
  })
  assert.equal(getBackendUrl(), "https://example.com/api")
  assert.equal(toWsUrl("/ws/devices"), "wss://example.com/api/ws/devices")
})
