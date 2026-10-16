# MoolTrace demo video script (≤90 s)

Record signed-out. Track 01: **Agents That Act on Connected Data**.
Live demo: https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/
Say only numbers cited at the bottom. Do not give medical advice. An Expression of Concern is not a retraction. Never say the review relies on the trial. Do not say olive oil or the Mediterranean diet works or does not.

Voice is the `>` lines. Everything else is on-screen or a director note.

## Problem (5 s)

On-screen title: Track 01 — Agents That Act on Connected Data.

> Your health bot cites Healthline. No DOI in the draft. Looks safe.

## Paste AI answer (10 s)

Open `/?preset=olive-oil`. The URL is the whole answer:

`https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil`

> A nutrition coach pastes only this Healthline olive oil URL. That is the whole answer.

## No-graph check (5 s)

On-screen: `mooltrace baseline` / Direct-DOI checker. Decision **pass**, exit 0, `dois []`.

> A Direct-DOI check (no graph) finds no DOI. Pages are not fetched. It says pass.

## MoolTrace BLOCK and path (20 s)

Keep the live BLOCK result in frame. Point at the two hops, then `Decided by: algo.SPpaths, path strength 0.30`.

> Healthline olive oil goes to Schwingshackl 2014, then Estruch 2013. Both hops are mention, 0.55 times 0.55. Path strength 0.30. The 2013 trial was retracted and republished in 2018. BLOCK (exit 1).

On-screen must show: **BLOCK (exit 1)**; hops `mention` 0.55 → `mention` 0.55; retraction `10.1056/nejmc1806491` (2018-06-13); notice title as stored. Do not read those mention hops as the review depending on the trial.

## Rewrite (10 s)

Click **Rewrite and recheck** (deterministic template, not a language-model edit). Paste this two-sentence draft if the preset is URL-only:

Before: `Vitamin D status is discussed separately. A nutrition coach cites https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil.`

After: `Vitamin D status is discussed separately. A nutrition coach cites: the study this relied on (Estruch 2013) was retracted on 2018-06-13. This claim has been removed.`

> Rewrite names Estruch 2013 and drops only that claim. Vitamin D status is discussed separately. stays byte-identical.

## CI fails the PR (10 s)

Terminal:

```bash
.venv/bin/python -m mooltrace batch examples/lancet.jsonl --fail-on block
echo $?
```

> Same gate in CI. Lancet 2020 retraction. Fail-on block. Exit 1. The PR fails.

## Agent calls what_rests_on over MCP (15 s)

Remote MCP: `https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/mcp`
Tool `what_rests_on` on `10.1056/nejmc1806491` (after the olive-oil check is in the graph).

> An agent calls what_rests_on over MCP. This retraction affects 1 stored answer.

Do not run reverse-recheck on camera (hosted recheck is not this beat).

## Baseline result (10 s)

On-screen table from `results/baseline_2026-10-16.json`:

> On 52 labelled cases, no-graph recall is 0.4286. MoolTrace recall is 1.0. 15 cases only the graph catches.

## Close (5 s)

> MoolTrace. Check the roots before you ship.

Stop at or before 90 s.

## Click order

1. Signed-out demo `/?preset=olive-oil`
2. Direct-DOI / baseline pass (terminal or slide)
3. BLOCK path + `algo.SPpaths` 0.30
4. Rewrite
5. `batch examples/lancet.jsonl --fail-on block`
6. MCP `what_rests_on`
7. Baseline slide
8. Close line

## Numbers (cited)

| Number / line | Source |
| --- | --- |
| BLOCK, path strength 0.30, hops `mention` 0.55 × `mention` 0.55, retraction `10.1056/nejmc1806491` (2018-06-13), Schwingshackl 2014, Estruch 2013 | `examples/presets_recorded.json` (`nutrition-olive-oil`); live signed-out POST 16 Oct 2026 (CLAIMS.md / T08); throwaway replay this file (`MOOLTRACE_DB=/tmp/mt-t13-ship`, `data/mooltrace.db` unused) |
| Raw strength `0.30250000000000005` (UI prints 0.30) | same preset run |
| Direct-DOI on the olive-oil URL: **pass**, exit 0, `dois []`, summary starts `Direct-DOI check (no graph)` | `mooltrace.baseline.check_direct_doi("", [olive-oil URL])` this session, recorded Crossref catalog, no HTTP |
| Rewrite keeps `Vitamin D status is discussed separately.` and names Estruch 2013, date 2018-06-13; never `RETRACTED:`; never notice DOI | `template_rewrite` on the recorded olive-oil payload this session (`/tmp/mt-t13-ship2`) |
| `This retraction affects 1 stored answer.` | `what_rests_on("10.1056/nejmc1806491")` after seeding that preset, this session; live remote MCP 16 Oct 2026 (T09 / CLAIMS.md) counted 1 |
| Lancet CI exit 1 | `mooltrace batch examples/lancet.jsonl --fail-on block`, 16 Oct 2026 18:09 UTC, CLAIMS.md, throwaway DB, 14.06 s |
| Direct-DOI recall 0.4286; MoolTrace recall 1.0; 15 only-multi-hop; n=52 | `results/baseline_2026-10-16.json` (`baseline.metrics.recall`, `mooltrace.metrics.recall`, `only_multihop_ids`) |
| Olive-oil URL is not one of those 15 labelled rows. The no-graph miss on this URL is the separate Direct-DOI pass above. | labelled ids in that JSON; Direct-DOI run this session |
