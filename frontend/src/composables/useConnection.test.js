import test from "node:test"
import assert from "node:assert/strict"

import {
  getConnectionState,
  setMode,
  setRemoteUrl,
  getBackendUrl,
  toWsUrl,
  resolveElectronBackendUrl,
} from "./useConnection.js"

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

test("resolveElectronBackendUrl falls back to healthy default backend when Electron port is stale", async () => {
  const calls = []
  const fetchImpl = async (url) => {
    calls.push(url)
    return {
      ok: url === "http://127.0.0.1:18000/health",
      json: async () => ({ status: "ok" }),
    }
  }

  const url = await resolveElectronBackendUrl(
    {
      getBackendStatus: async () => ({ port: 18001, running: false }),
    },
    { isDevMode: true, fetchImpl }
  )

  assert.equal(url, "http://127.0.0.1:18000")
  assert.deepEqual(calls, ["http://127.0.0.1:18000/health"])
})

test("resolveElectronBackendUrl keeps a healthy Electron backend port", async () => {
  const calls = []
  const fetchImpl = async (url) => {
    calls.push(url)
    return {
      ok: true,
      json: async () => ({ status: "ok" }),
    }
  }

  const url = await resolveElectronBackendUrl(
    {
      getBackendStatus: async () => ({ port: 18002, running: true }),
    },
    { isDevMode: true, fetchImpl }
  )

  assert.equal(url, "http://127.0.0.1:18002")
  assert.deepEqual(calls, ["http://127.0.0.1:18002/health"])
})
