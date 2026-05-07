import test from "node:test"
import assert from "node:assert/strict"

import { useSettings } from "./useSettings.js"

test("useSettings persists connection mode and normalized remote URL", () => {
  globalThis.localStorage = {
    value: "",
    getItem() { return this.value },
    setItem(key, value) { this.value = value },
  }

  const { settings, setConnectionSettings, getConnectionSettings } = useSettings()
  settings.value.connection.mode = "auto"
  settings.value.connection.remoteUrl = ""

  setConnectionSettings({ mode: "remote", remoteUrl: "wss://example.com/" })

  assert.deepEqual(getConnectionSettings(), {
    mode: "remote",
    remoteUrl: "https://example.com",
  })
})
