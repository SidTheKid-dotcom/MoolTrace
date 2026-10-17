# MoolTrace demo video script (≤90 s)

Record signed-out. Track 01: **Agents That Act on Connected Data**.
Live demo: https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/
Say only numbers cited at the bottom. Do not give medical advice. An Expression of Concern is not a retraction. Never say the review relies on the trial. Do not say olive oil, vitamin D, or the Mediterranean diet works or does not.

Voice is the `>` lines. Everything else is on-screen or a director note.

## Problem (5 s)

On-screen title: Track 01 — Agents That Act on Connected Data.

> Your health bot cites Healthline. No DOI in the draft. Looks safe.

## Paste AI answer (8 s)

Open `/?preset=harvard-vitamin-d`. The URL is the whole answer:

`https://nutritionsource.hsph.harvard.edu/vitamin-d/`

> A nutrition coach pastes only this Harvard Nutrition Source vitamin D URL. That is the whole answer.

## No-graph check (5 s)

On-screen: `mooltrace baseline` / Direct-DOI checker. Decision **pass**, exit 0, `dois []`.

> A Direct-DOI check (no graph) finds no DOI. Pages are not fetched. It says pass.

## MoolTrace BLOCK and path (18 s)

Stay on **Harvard vitamin D (block)**. **BLOCK (exit 1)**. Point at the two hops, then `Decided by: algo.SPpaths, path strength 0.47`. Then the **Why the graph decided** panel: `Direct DOI check: 0 notices → would ship  |  Graph depth 2: retraction 10.1016/j.amjmed.2004.05.019 → BLOCK`.

> BLOCK. Harvard vitamin D goes to Avenell 2014, then Ishida 2004. The review used that trial. uses_data_or_method 0.85. Path strength 0.47. Direct-DOI would have shipped. The graph blocked.

Then click **Healthline olive oil (warn)** (`https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil`). Toggle **depth 1**: **PASS** (exit 0), 0 notice paths. Toggle **depth 3**: **WARN (exit 2)**, path strength 0.30.

> Olive oil depth 1 is pass. Zero notice paths. Depth 3 is WARN. Both hops are mention. Estruch 2013 was retracted and republished. The review did not appear to rely on it.

On-screen must show: Harvard **BLOCK (exit 1)**; hops `mention` 0.55 → `uses_data_or_method` 0.85; Ishida 2004 retraction `10.1016/j.amjmed.2004.05.019` (2004-10-15); **Why the graph decided** with Direct-DOI would ship vs graph BLOCK. Then olive-oil depth 1 **PASS**, 0 notice paths; depth 3 **WARN**; hops `mention` 0.55 → `mention` 0.55; retraction `10.1056/nejmc1806491` (2018-06-13). Do not read those mention hops as the review depending on the trial.

## Not in the graph (8 s)

Click **Not in the graph**. NHS page `https://www.nhs.uk/live-well/best-way-to-wash-your-hands/`.

> This NHS how-to has no scholarly citations. WARN. Expanded 0 of 0 cited works. That is not a pass, and it is not proof it is safe.

On-screen: **WARN** (exit 2); “Nothing in the graph connects this answer to a study. This is not proof it is safe; the source may not be modelled.” Coverage **expanded 0 of 0 cited works**.

## Rewrite (8 s)

Stay on the Harvard vitamin D preset. Click **Rewrite and recheck** (deterministic template, not a language-model edit). The demo fills this recorded two-sentence draft and shows Before / After. Do not paste free text.

Before: `Hand hygiene is discussed separately. A nutrition coach cites https://nutritionsource.hsph.harvard.edu/vitamin-d/.`

After: `Hand hygiene is discussed separately. An earlier version of this answer cited Ishida et al. 2004; that paper was retracted on 15 Oct 2004, so this claim was removed.`

> Rewrite names Ishida 2004 and drops only that claim. Hand hygiene is discussed separately. stays byte-identical.

## CI fails the PR (8 s)

Terminal:

```bash
.venv/bin/python -m mooltrace batch examples/lancet.jsonl --fail-on block
echo $?
```

> Same gate in CI. Lancet 2020 retraction. Fail-on block. Exit 1. The PR fails.

## Agent calls what_rests_on over MCP (12 s)

Remote MCP: `https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/mcp`
Tool `what_rests_on` on `10.1016/j.amjmed.2004.05.019` (after the Harvard vitamin D check is in the graph).

> An agent calls what_rests_on over MCP. This retraction affects 2 stored answers.

On-screen is the live hosted graph, which accumulates checks. This session (17 Oct 2026 10:37 UTC) printed **2**. A throwaway seed of only the Harvard preset is 1. Do not freeze N if the live number moved.

Do not run reverse-recheck on camera (hosted recheck is not this beat).

## Baseline result (8 s)

On-screen table from `results/baseline_2026-10-16.json` and `results/vitality_2026-10-17.json`:

> On 52 labelled cases, no-graph recall is 0.4286. MoolTrace recall is 1.0. 15 cases only the graph catches. On VITALITY, Direct-DOI is 0 of 40. The graph reaches the same trial on 31 of 40.

## Close (5 s)

> MoolTrace. Check the roots before you ship.

Stop at or before 90 s. Beats sum to 85 s.

## Click order

1. Signed-out demo `/?preset=harvard-vitamin-d`
2. Direct-DOI / baseline pass (terminal or slide)
3. Harvard BLOCK path + `algo.SPpaths` 0.47 + **Why the graph decided**; then olive-oil toggle depth 1 (PASS, 0 notice paths) then depth 3 (WARN, path strength 0.30)
4. Click **Not in the graph** (WARN, expanded 0 of 0)
5. Rewrite
6. `batch examples/lancet.jsonl --fail-on block`
7. MCP `what_rests_on`
8. Baseline + VITALITY slide
9. Close line

## Numbers (cited)

| Number / line | Source |
| --- | --- |
| Harvard vitamin D **BLOCK (exit 1)**, path strength 0.47, hops `mention` 0.55 × `uses_data_or_method` 0.85, Ishida 2004 retraction `10.1016/j.amjmed.2004.05.019` (2004-10-15), Avenell 2014 | `examples/presets_recorded.json` (`nutrition-harvard-vitamin-d`); live throwaway DB 17 Oct 2026 (T25); seeded replay under T26 PATH_RULE |
| **Why the graph decided**: `Direct DOI check: 0 notices → would ship  |  Graph depth 2: retraction 10.1016/j.amjmed.2004.05.019 → BLOCK` | hosted signed-out POST `/?preset=harvard-vitamin-d` depth 2, 17 Oct 2026 10:37 UTC, `:mooltrace.api.15` |
| Raw Harvard strength `0.4675` (UI prints 0.47) | same preset run |
| Olive-oil depth 1 **PASS**, exit 0, 0 notice paths | `examples/presets_recorded.json` (`nutrition-olive-oil` `by_depth["1"]`); live throwaway DB 16 Oct 2026 19:51 UTC (T17, wall 13.6 s) |
| Olive-oil depth 3 **WARN (exit 2)**, path strength 0.30, hops `mention` 0.55 × `mention` 0.55, retraction `10.1056/nejmc1806491` (2018-06-13), Schwingshackl 2014, Estruch 2013 | `examples/presets_recorded.json` (`nutrition-olive-oil`); T26 PATH_RULE on the recorded hops |
| Raw olive-oil strength `0.30250000000000005` (UI prints 0.30) | same preset run |
| Direct-DOI on the Harvard URL: **pass**, exit 0, `dois []`, summary starts `Direct-DOI check (no graph)` | `mooltrace.baseline.check_direct_doi("", [Harvard URL])` recorded Crossref catalog, no HTTP |
| Not in the graph: NHS `https://www.nhs.uk/live-well/best-way-to-wash-your-hands/`, WARN exit 2, **expanded 0 of 0 cited works**, fetched 2026-10-16T20:22:08+00:00, hash `5c015843460b0e872bd9a0b01bf0c5bf91a810a04a9f21b72b0574b525495329` | `examples/presets_recorded.json` (`not-in-graph`); live throwaway DB 16 Oct 2026 (T18); hosted signed-out POST 16 Oct 2026 (T18 / T20) |
| Rewrite keeps `Hand hygiene is discussed separately.` and names Ishida et al. 2004, retracted on 15 Oct 2004; never `RETRACTED:`; never notice DOI; click **Rewrite and recheck** on the Harvard preset (no free-text paste) | recorded rewrite draft in `examples/presets_recorded.json` |
| `This retraction affects 2 stored answers.` | hosted MCP `what_rests_on("10.1016/j.amjmed.2004.05.019")` 17 Oct 2026 10:37 UTC after Harvard `check_answer`; shared demo graph. Throwaway seed of that preset is 1. |
| Lancet CI exit 1 | `mooltrace batch examples/lancet.jsonl --fail-on block`, 16 Oct 2026 18:09 UTC, CLAIMS.md, throwaway DB, 14.06 s |
| Direct-DOI recall 0.4286; MoolTrace recall 1.0; 15 only-multi-hop; n=52 | `results/baseline_2026-10-16.json` (`baseline.metrics.recall`, `mooltrace.metrics.recall`, `only_multihop_ids`) |
| VITALITY Direct-DOI 0/40; MoolTrace same-trial **31/40**; false alarms 1/40 (n=40); depth 3 14/18 pending 22 | `results/vitality_2026-10-17.json` |
| Olive-oil URL is not one of those 15 labelled rows. The no-graph miss on this URL is the separate Direct-DOI pass above. | labelled ids in that JSON; Direct-DOI run T13 |
