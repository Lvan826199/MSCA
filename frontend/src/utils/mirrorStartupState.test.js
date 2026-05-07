import test from "node:test"
import assert from "node:assert/strict"

import { MIRROR_CANVAS_MISSING_MESSAGE, shouldFailWhenCanvasMissing } from "./mirrorStartupState.js"

test("shouldFailWhenCanvasMissing treats missing canvas after backend start as startup failure", () => {
  assert.equal(shouldFailWhenCanvasMissing(null), true)
  assert.equal(shouldFailWhenCanvasMissing({ getContext() {} }), false)
})

test("MIRROR_CANVAS_MISSING_MESSAGE tells user mirror canvas is unavailable", () => {
  assert.match(MIRROR_CANVAS_MISSING_MESSAGE, /画布|投屏/)
})
