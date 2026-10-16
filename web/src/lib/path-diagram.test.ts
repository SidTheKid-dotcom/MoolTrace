import assert from "node:assert/strict"
import { test } from "node:test"
import { buildPathGraph, decidingReason, hostLabel, noticeLabel } from "./path-diagram.ts"

const HEALTHLINE = {
  notice_doi: "10.2337/dc25-ec09",
  notice_type: "expression_of_concern",
  sentence: "cassia decreased triglycerides (TG) levels and total cholesterol (TC) levels [15].",
  steps: [
    {
      kind: "Source",
      title: "How Cinnamon Lowers Blood Sugar and Fights Diabetes",
      url: "https://www.healthline.com/nutrition/cinnamon-and-diabetes",
    },
    {
      kind: "Work",
      doi: "10.3390/nu14132773",
      title: "Cinnamon as a Complementary Therapeutic Approach",
      year: 2022,
    },
    {
      kind: "Work",
      doi: "10.2337/diacare.26.12.3215",
      title: "Cinnamon Improves Glucose and Lipids of People With Type 2 Diabetes",
      year: 2003,
    },
  ],
  hops_evidence: [
    { weight: 0.55, reliance: "mention", sentence: "A review.", evidence_from: "page" },
    { weight: 1.0, reliance: "relies", sentence: "cassia decreased triglycerides.", evidence_from: "semantic_scholar" },
  ],
}

test("notice types stay human", () => {
  assert.equal(noticeLabel("expression_of_concern"), "Expression of Concern")
  assert.equal(noticeLabel("retraction"), "Retraction")
  assert.equal(hostLabel("https://www.healthline.com/nutrition/cinnamon-and-diabetes"), "healthline.com")
  assert.equal(hostLabel("urn:mooltrace:paste:abc"), "draft")
})

test("Healthline path is Source → Work → Work → Notice", () => {
  const graph = buildPathGraph(HEALTHLINE)
  assert.deepEqual(
    graph.nodes.map((node) => node.kind),
    ["Source", "Work", "Work", "Notice"],
  )
  assert.equal(graph.nodes[0].label, "healthline.com")
  assert.equal(graph.nodes[3].label, "Expression of Concern")
  assert.deepEqual(
    graph.edges.map((edge) => edge.label),
    ["mention", "relies", "FLAGS"],
  )
  assert.equal(graph.edges[1].weight, 1)
})

test("Everyday Health one-hop still adds FLAGS", () => {
  const graph = buildPathGraph({
    notice_doi: "10.2337/dc25-ec09",
    notice_type: "expression_of_concern",
    steps: [
      {
        kind: "Source",
        url: "https://www.everydayhealth.com/diabetes/cinnamon-for-diabetes/",
        title: "Cinnamon for Diabetes",
      },
      { kind: "Work", doi: "10.2337/diacare.26.12.3215", title: "Khan 2003", year: 2003 },
    ],
    hops_evidence: [{ weight: 0.55, reliance: "mention", sentence: "Khan et al." }],
  })
  assert.equal(graph.nodes.length, 3)
  assert.equal(graph.edges.at(-1)?.label, "FLAGS")
})

test("decidingReason prefers a notice path over a path with no steps", () => {
  const picked = decidingReason([
    { steps: [] },
    HEALTHLINE,
    { steps: [{ kind: "Work", doi: "10.1/example" }] },
  ])
  assert.equal(picked, HEALTHLINE)
})

test("decidingReason prefers the lower SPpaths cost", () => {
  const expensive = { ...HEALTHLINE, notice_doi: "10.1/expensive", sp_cost: 2.0 }
  const cheap = { ...HEALTHLINE, notice_doi: "10.1/cheap", sp_cost: 0.01 }
  const picked = decidingReason([expensive, cheap])
  assert.equal(picked, cheap)
})
