# MoolTrace

Trace a health-AI answer to its root, and see if that root is flagged.

Mool means root. The user is an engineer or reviewer on a health-AI team, before merging an answer fixture or shipping a content draft. Health models cite web pages. Direct DOI or retraction checkers miss the page → review → study → publisher Expression of Concern chain. MoolTrace returns a deterministic **pass / warn / block** with the exact path, each hop's sentence and weight, the notice, and the Cypher that decided it.

It reports a path to a publisher notice. It does not say the draft is medically correct or incorrect. An Expression of Concern is not a retraction.

WeMakeDevs × FalkorDB Graph Hacks, **Track 1**. The verdict is computed from FalkorDB paths and `RESTS_ON` hop properties. Notices come from Crossref. Citation lists come from OpenAlex. Citation sentences come from Semantic Scholar contexts, PMC, the citing page, or the pasted draft.

## Primary workflow: CI over answer fixtures

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
export MOOLTRACE_MAILTO=you@example.com
.venv/bin/python -m mooltrace batch examples/answers.jsonl --fail-on block
echo $?
```

`examples/answers.jsonl` is the CI sample (Everyday Health URL-only + Allen 2013). Those warn; they do not block. `--fail-on block` therefore exits 0. `examples/lancet.jsonl` is the retraction demo and exits 1.

Exit codes: **0** pass, **1** block, **2** warn/review, **3** infrastructure failure.

`--fail-on block` (default) fails CI on block and infra. Warn is annotated (`::warning`) and does not fail. Use `--fail-on warn` to fail on warn too.

The sample workflow `.github/workflows/mooltrace-fixtures.yml` installs a venv and runs `examples/answers.jsonl` on pull requests, pushes to `main`, and manual dispatch. A daily schedule re-runs that same fixture file against live catalogs. That is a fresh fixture recheck, not persistent monitoring. The web UI is an evidence viewer for the demo, not the core claim. MCP is an editor integration for the same check.

Hero fixture: Everyday Health URL only, no Khan DOI in the pasted text. See `examples/nutrition-draft.txt` and the first line of `examples/answers.jsonl`.

```bash
.venv/bin/python -m mooltrace check-answer \
  --urls-file <(printf '%s\n' 'https://www.everydayhealth.com/diabetes/cinnamon-for-diabetes/') \
  --engine nutrition-coach \
  --depth 2
```

## Decision

| Decision | Meaning | Exit |
| --- | --- | --- |
| pass | No counted or unverified path to a publisher notice within the requested depth | 0 |
| block | A counted path reaches a retraction, withdrawal, or removal | 1 |
| warn | A counted path reaches an Expression of Concern, a reachable path is unverified, the check did not finish, or no verifiable citation or source was provided (`no_sources`) | 2 |
| incomplete (infra) | Graph timeout or exhausted upstream. Not a silent pass and not a block | 3 |

A **counted path** needs every `RESTS_ON` hop judged with a stored sentence and weight ≥ 0.5, and a `path_score` (the product of those weights) ≥ 0.25. A chain of bare mentions (`0.55 × 0.55 × 0.55`) does not count. A two-hop use (`0.85 × 0.85`) does. The draft cannot hedge-bypass: naming an Expression of Concern or writing "we excluded" in the pasted answer does not turn a cited flagged study into a pass. A scholarly review can still set a study aside. A weak background hop does not hide a counted longer path: the check classifies **every** path within the depth cap, not `shortestPath`. Depth is 1–3. Depth 4 is not implemented. `pass` means no counted or unverified notice was found within that depth. Coverage is **not shown** beyond it.

## Graph model

Nodes: `Answer`, `Source`, `Work`, `Notice`.

Edges: `(Answer)-[:CITES]->(Source)`, `(Source)-[:RESTS_ON]->(Work)`, `(Work)-[:RESTS_ON]->(Work)`, `(Notice)-[:FLAGS]->(Work)`.

`RESTS_ON` stores `reliance`, `weight`, `sentence`, `evidence_from`, `judged`, `judged_at`.

The deciding query (bounds are literals; depth 2 shown). `FLAGS` is matched separately so FalkorDB does not bind the notice hop into `p`:

```cypher
MATCH (a:Answer {id: $answer_id})-[:CITES]->(s:Source)
MATCH (n:Notice)-[:FLAGS]->(w:Work)
MATCH p = (s)-[:RESTS_ON*1..2]->(w)
WITH s, w, n, p, relationships(p) AS rels
WITH s, w, n, p, rels,
     reduce(score = 1.0, r IN rels | score * coalesce(r.weight, 0.0)) AS path_score
RETURN s.url AS source_url,
       s.title AS source_title,
       w.doi AS root_doi,
       w.title AS root_title,
       w.year AS root_year,
       n.doi AS notice_doi,
       n.type AS notice_type,
       n.label AS notice_label,
       n.date AS notice_date,
       n.source AS notice_source,
       length(p) AS hops,
       path_score,
       [x IN nodes(p) | {doi: x.doi, title: x.title, url: x.url, year: x.year}] AS steps,
       [r IN rels | {weight: r.weight, reliance: r.reliance, sentence: r.sentence, evidence_from: r.evidence_from, judged: r.judged}] AS hops_evidence
ORDER BY path_score DESC, hops ASC
LIMIT 80
```

Remediation clusters (not the verdict) use FalkorDBLite 0.10.0:

```cypher
CALL algo.WCC({nodeLabels: ['Work'], relationshipTypes: ['RESTS_ON']})
YIELD node, componentId
```

```cypher
CALL algo.pageRank('Work', 'RESTS_ON')
YIELD node, score
```

That groups answers that share a Work component containing a publisher notice. The fixture batch report includes these clusters. `algo.pageRank` ranks which counted notice is shown first. `algo.MaxFlow` is not registered in this build. Independent sources are distinct citers on counted paths.

Reverse lookup lists every matching notice and only the answers whose sources reach that work. Counted answers use the same hop rule, including the path-score floor. It is not a monitoring or alert scheduler.

Every query the tools run is in `mooltrace/cypher.py`.

## Reliance weights

| Class | Weight | Counts |
| --- | --- | --- |
| relies | 1.0 | yes |
| uses_data_or_method | 0.85 | yes |
| mention | 0.55 | yes |
| background | 0.2 | no |
| critical | 0.0 | no |

Semantic Scholar [citation context data](https://www.semanticscholar.org/) may appear in hop evidence (`evidence_from: semantic_scholar`). Intent labels from that API are not requested.

## Seeded regression (not accuracy)

`python -m mooltrace.gate` runs each fixture on its **own throwaway graph** at default depth 2. It never deletes `MOOLTRACE_DB`.

Positives: Everyday Health URL-only, Allen 2013, Deyno 2019 (`10.1016/j.diabres.2019.107815`, not Namazi), CTIM 2020, Moridpour 2023 (`10.1002/ptr.8026`, first author Moridpour), Cochrane 2012, Lancet 2020 retraction.

Clean DOIs are works that had no Crossref retraction / withdrawal / removal / EoC on the work itself **and** no flagged ancestor within depth 2 on an isolated graph as of 15 Oct 2026. They are not a random sample. Papers that merely sit near Khan (for example `10.1093/jn/136.4.977`) are true signals, not clean negatives. Any warn/block on a clean fixture is an **alarm**.

Live numbers are not hardcoded. Run the gate. Files under `results/` are marked stale and are not a score.

## Setup

Python 3.12+. Node 20+ only for the demo UI.

```bash
python3 -m venv .venv
.venv/bin/pip install -e . pytest
export MOOLTRACE_MAILTO=you@example.com
.venv/bin/python -m pytest
.venv/bin/python -m mooltrace.api
```

The API binds `127.0.0.1:4317` and allows CORS from the local UI. The demo UI:

```bash
cd web && npm ci && npm run dev -- --port 4318 --hostname 127.0.0.1
```

Open [http://127.0.0.1:4318](http://127.0.0.1:4318). `/nw/*` rewrites to the API.

MCP: `.venv/bin/python -m mooltrace.mcp_server` (stdio). See `mcp.example.json`.

## Prior art

Closest public systems: [Shaky Ground](https://github.com/aryangorde6/shaky-ground) (web UI and MCP landed in `6ba49c2` on 15 Oct 2026; live HEAD at check 15 Oct 2026 16:49 IST is `68ae587`, parent `d0a4cb9`, so UI/MCP are table stakes), refcheck, Origyn, GhostCite, Citeright, citeguard. MoolTrace's wedge is the **page hop plus publisher Expression of Concern** on a health-AI answer fixture, with hop-level reliance in FalkorDB, not a claim of unique multi-hop, unique EoC, unique MCP, or continuous monitoring.

## Limits

- This does not give medical advice and does not say cinnamon, hydroxychloroquine, or any intervention works.
- Khan 2003 (`10.2337/diacare.26.12.3215`) carries Expression of Concern `10.2337/dc25-ec09` (2025-08-20), not a retraction. OpenAlex `is_retracted` can stay false.
- Mehra et al., Lancet 2020 (`10.1016/s0140-6736(20)31180-6`) was retracted (`10.1016/s0140-6736(20)31324-6`).
- Cleveland Clinic pages are not fetched in shipped presets or tests.
- Everyday Health `/diabetes/cinnamon-for-diabetes/` is a public article URL (no login). The demo fetches it once to walk page → review → study → publisher notice. It is not a training crawl. Named AI crawlers are blocked in that site's robots.txt; this User-Agent identifies MoolTrace with a mailto. If that fetch is refused, use Allen 2013 as the DOI fixture.
- Unverified or unfinished reachable paths warn. They never silently pass.
- A draft with no DOI, PMID, PMCID, resolvable scholarly identifier, or public URL warns (`no_sources`). MoolTrace cannot inspect that evidence chain. This is not a pass and not a medical claim. Inline DOI, PMID, PMCID, or URL, and explicit URLs, still count as sources.
- Private, loopback, credentialed, and non-http URLs are refused (SSRF). The API binds `127.0.0.1` and does not honor CORS `*`.
- Semantic Scholar 429s after retries skip that route; other sentence routes still run.
- The sample GitHub workflow fetches live OpenAlex, Crossref, and the Everyday Health page. If a host refuses GitHub IPs, the job exits 3. The daily cron re-runs that fixture file; it does not watch answers over time.

## AI-use disclosure

MoolTrace code in this repository was written with Cursor agents (including Grok) after the Graph Hacks kickoff on 15 Oct 2026. Paths and notices come from live OpenAlex, Crossref, NCBI, Semantic Scholar, and PMC, not from the model. Each teammate must be able to explain the code they ship.

## Demo checklist

1. Fresh clone, venv, `pip install -e . pytest`, `pytest`.
2. `python -m mooltrace batch examples/answers.jsonl --fail-on block` (exit 0; warns are annotated).
3. URL-only Everyday Health check twice; second call should make 0 API calls while notices are fresh.
4. `python -m mooltrace batch examples/lancet.jsonl --fail-on block` (exit 1) → block on the retraction notice, not the earlier EoC.
5. UI preset Everyday Health shows path, hop sentence, and the PATHS_TO_NOTICE Cypher (not an unused query).
6. `ro_cypher` with `CONTAINS 'set'` is allowed; `CREATE` is rejected; GRAPH.RO_QUERY is the write barrier.
7. Public repo, 2:50 video, Track 1, AWS/FalkorDB shown, AI tools listed.

License: MIT. Copyright holder matches the GitHub profile name for `SidTheKid-dotcom` (Siddhant Vishnu).
