import assert from "node:assert/strict"
import { test } from "node:test"
import { stepLabel } from "./step-label.ts"

const PASTE = "urn:mooltrace:paste:8ac9aace5474c753"
const EVERYDAY = "https://www.everydayhealth.com/diabetes/cinnamon-for-diabetes/"

test("paste URN without a title shows draft", () => {
  assert.equal(stepLabel({ url: PASTE }), "draft")
})

test("paste URN with a title shows the title", () => {
  assert.equal(stepLabel({ url: PASTE, title: "Pasted draft" }), "Pasted draft")
})

test("DOI chips stay DOIs", () => {
  assert.equal(stepLabel({ doi: "10.1370/afm.1517", title: "Allen 2013" }), "10.1370/afm.1517")
  assert.equal(stepLabel({ doi: "10.2337/diacare.26.12.3215", url: null }), "10.2337/diacare.26.12.3215")
})

test("Everyday Health URL wins over title", () => {
  assert.equal(
    stepLabel({ url: EVERYDAY, title: "Cinnamon for Diabetes" }),
    EVERYDAY,
  )
})

test("http(s) URLs stay URLs", () => {
  assert.equal(
    stepLabel({ url: "http://example.com/page", title: "Example" }),
    "http://example.com/page",
  )
})
