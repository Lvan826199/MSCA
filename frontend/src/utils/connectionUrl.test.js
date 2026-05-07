import test from "node:test"
import assert from "node:assert/strict"

import { normalizeHttpBaseUrl, toWsBaseUrl } from "./connectionUrl.js"

test("normalizeHttpBaseUrl converts websocket remote addresses to HTTP REST base URLs", () => {
  assert.equal(normalizeHttpBaseUrl("wss://example.com/api/"), "https://example.com/api")
  assert.equal(normalizeHttpBaseUrl("ws://127.0.0.1:19000/"), "http://127.0.0.1:19000")
})

test("normalizeHttpBaseUrl adds HTTPS when remote address omits protocol", () => {
  assert.equal(normalizeHttpBaseUrl("example.com"), "https://example.com")
})

test("toWsBaseUrl converts HTTP REST base URLs to WebSocket base URLs", () => {
  assert.equal(toWsBaseUrl("https://example.com/api"), "wss://example.com/api")
  assert.equal(toWsBaseUrl("http://127.0.0.1:19000"), "ws://127.0.0.1:19000")
})
