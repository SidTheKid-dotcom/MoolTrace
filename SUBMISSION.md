# MoolTrace — Graph Hacks submission

Fill the video URL on 18 Oct 2026 after upload. Do not invent it.

**Name:** MoolTrace

**Tagline:** Check the roots before you ship.

**Track:** 01 — Agents That Act on Connected Data

**Deadline:** Sun 18 Oct 2026, 11:59 PM IST

## 150-word description

Health-AI products (symptom checkers, nutrition coaches, patient chatbots) cite consumer pages. Those pages cite reviews, which cite trials. Some of those trials now carry a publisher Expression of Concern or a retraction. MoolTrace turns one pasted answer plus its URLs into a FalkorDB graph (Answer → Source → Work → Notice). **algo.SPpaths** with cost `-ln(weight)` decides pass / warn / block from path strength. Judges see the hops, the sentence on each hop, the evidence trail, and the Cypher. An Expression of Concern is not a retraction and is never scored as one. A no-graph Direct-DOI check misses URL-only chains; the graph catches them. CI (`mooltrace batch`) fails a PR on block. Remote MCP exposes `check_answer`, `what_rests_on`, and `recheck_affected`. Rewrite is a deterministic template: only sentences that cite flagged work change. This is a pre-ship gate, not a medical-accuracy claim.

## How judges run it in two minutes

Live demo (no sign-up): https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/ — click **Harvard vitamin D (block)**. **BLOCK (exit 1)** and `Decided by: algo.SPpaths, path strength 0.47` (page `mention` 0.55 × Avenell 2014 `uses_data_or_method` 0.85 → Ishida 2004 retraction `10.1016/j.amjmed.2004.05.019` 2004-10-15; recorded 17 Oct 2026 in `examples/presets_recorded.json`). Then **Healthline olive oil (warn)**: toggle **depth 1** **PASS** (0 notice paths); toggle **depth 3** **WARN (exit 2)** path strength 0.30 (mention × mention to Estruch 2013; the review did not appear to rely on it). Click **Not in the graph** for the honest negative (NHS how-to, WARN, expanded 0 of 0 cited works). The 2013 trial was retracted and republished in 2018 after re-analysis. This does not say olive oil or vitamin D works or does not.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
export MOOLTRACE_MAILTO=you@example.com
.venv/bin/python -m mooltrace check --url https://www.healthline.com/nutrition/cinnamon-and-diabetes --summary
```

Expect **WARN (exit 2)** and `Decided by: algo.SPpaths, path strength 0.55` (Healthline page `mention` × Silva→Khan `relies`, recorded 16 Oct 2026). An Expression of Concern is not a retraction. Then:

```bash
.venv/bin/python -m mooltrace batch examples/lancet.jsonl --fail-on block; echo $?
```

Expect exit **1** (Mehra 2020 retraction). Direct-DOI on the olive-oil URL with no graph is **pass** (no DOI in the draft; this session, `check_direct_doi`). Olive-oil depth-1 MoolTrace is **pass** (0 notice paths). Olive-oil depth-3 MoolTrace is **warn** (mention × mention). Harvard vitamin D depth-2 is **block**.

## Cypher (deciding query)

Bounds are literals; depth 2 shown. `cost` on `RESTS_ON` is `-ln(weight)`. The verdict uses these `algo.SPpaths` rows only:

```cypher
MATCH (a:Answer {id: $answer_id})-[:CITES]->(s:Source)
MATCH p0 = (s)-[:RESTS_ON*1..2]->(w)
MATCH (n:Notice)-[:FLAGS]->(w:Work)
WITH DISTINCT s, w, n
CALL algo.SPpaths({sourceNode: s, targetNode: w, relTypes: ['RESTS_ON'], relDirection: 'outgoing', maxLen: 2, weightProp: 'cost'})
YIELD path, pathCost
WITH s, w, n, path, pathCost, relationships(path) AS rels
RETURN s.url AS source_url,
       s.title AS source_title,
       w.doi AS root_doi,
       w.title AS root_title,
       w.year AS root_year,
       w.first_author AS root_author,
       n.doi AS notice_doi,
       n.type AS notice_type,
       n.label AS notice_label,
       n.date AS notice_date,
       n.source AS notice_source,
       length(path) AS hops,
       reduce(score = 0.0, r IN rels | score + coalesce(r.cost, 20.0)) AS sp_cost,
       reduce(score = 1.0, r IN rels | score * coalesce(r.weight, 0.0)) AS path_score,
       [x IN nodes(path) | {doi: x.doi, title: x.title, url: x.url, year: x.year, first_author: x.first_author}] AS steps,
       [r IN rels | {weight: r.weight, reliance: r.reliance, sentence: r.sentence, evidence_from: r.evidence_from, judged: r.judged, cost: r.cost, source_url: r.evidence_url, fetched_at: r.evidence_fetched_at, content_hash: r.evidence_sha256}] AS hops_evidence
ORDER BY sp_cost ASC, hops ASC
LIMIT 40
```

Remediation clusters (not the verdict):

```cypher
CALL algo.WCC({nodeLabels: ['Work'], relationshipTypes: ['RESTS_ON']})
YIELD node, componentId
```

## Algorithms

| Algorithm | Job |
| --- | --- |
| `algo.SPpaths` | Verdict. Strongest `RESTS_ON` path to a flagged Work, cost `-ln(weight)`. If it errors, exit 3. |
| `algo.WCC` | Remediation clusters only (not the verdict). Groups answers that share a Work component containing a publisher notice. |

`algo.pageRank` is registered in FalkorDBLite 0.10.0 and is **not** called. It does not change what a check shows.

## Baseline (cited)

From `results/baseline_2026-10-16.json` (16 Oct 2026; 52 labelled cases; Direct-DOI recall **0.4286**, MoolTrace recall **1.0**, 15 only-multi-hop catches). Reproduce: `.venv/bin/python -m mooltrace baseline --out results/baseline_2026-10-16.json`. Sealed external set from `results/vitality_2026-10-17.json`: Direct-DOI **0/40**, MoolTrace same-trial **31/40**, false alarms **1/40** (n=40). Depth 3 is a separate row: **14/18** same-trial, **1/40** false alarms, 22 extra positives pending. Reproduce: `.venv/bin/python -m mooltrace vitality --out results/vitality_2026-10-17.json`. This is not a medical accuracy score.

## Tech used

- FalkorDBLite 0.10.0 (embedded FalkorDB)
- Notices: Crossref. Citation lists: OpenAlex. Sentences: Semantic Scholar contexts, PMC, page, or draft
- Remote MCP (read-only): `check_answer`, `what_rests_on`, `recheck_affected` at `/mcp` on the demo host
- Local MCP (one command): `.venv/bin/python -m mooltrace mcp` — full tool list, including local `rewrite_answer`
- Rewrite is a deterministic template: only sentences that cite flagged work change; every other sentence stays byte-identical. Not an LLM edit.

## Links (paste on 18 Oct)

| Field | Value |
| --- | --- |
| Public GitHub repo | https://github.com/SidTheKid-dotcom/MoolTrace _(paste after flipping the repo public; currently private)_ |
| Demo video (YouTube, ≤90 s) | _paste after upload_ |
| Hosted demo | https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/ |
| Remote MCP | https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/mcp |

Five-minute path: [JUDGES.md](JUDGES.md). Video beats: [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md). Human-only ship steps: [SHIP_CHECKLIST.md](SHIP_CHECKLIST.md).

## AI-assistance disclosure

MoolTrace code in this repository was written with Cursor agents (including Grok) after the Graph Hacks kickoff on 15 Oct 2026. Paths and notices come from live OpenAlex, Crossref, NCBI, Semantic Scholar, and PMC, not from the model. Rewrite is a deterministic template, not an LLM edit. Each teammate can explain the code they ship.

## Data sources and attribution

- OpenAlex (citation lists, work metadata)
- Crossref (publisher notices, work metadata)
- DataCite (arXiv / Zenodo DOIs)
- NCBI / Europe PMC (PMID, PMC full text for `included`)
- Semantic Scholar [citation context data](https://www.semanticscholar.org/) may appear as hop evidence (`evidence_from: semantic_scholar`). Intent labels from that API are not requested.
- Public consumer pages used as fixtures: Healthline, Everyday Health, WebMD, Medical News Today (fetched with a mailto User-Agent). Cleveland Clinic pages are not fetched.
- Khan 2003 Expression of Concern `10.2337/dc25-ec09` (2025-08-20) is not a retraction.
- Mehra et al. Lancet 2020 `10.1016/s0140-6736(20)31180-6` was retracted (`10.1016/s0140-6736(20)31324-6`).
- Estruch 2013 PREDIMED `10.1056/nejmoa1200303` was retracted and republished (`10.1056/nejmc1806491`, 2018-06-13).
