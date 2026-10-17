# CLAIMS

Every README claim → the command that proves it. Confirmed 16 Oct 2026 in this checkout unless a row says otherwise. Do not treat these as a medical accuracy score. An Expression of Concern is not a retraction. Track 01: **Agents That Act on Connected Data**.

Live demo (no sign-up): https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/

Remote MCP: https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/mcp

Five-minute path: [JUDGES.md](JUDGES.md).

## Fresh-clone quickstart

Fresh-clone quickstart wall time on 16 Oct 2026: **65.06 s**.

Literal README 3-line run from a fresh clone in `/tmp` (16 Oct 2026 18:06–18:08 UTC). Clone from `origin.cursor.com`. `pip` used the local wheel cache. Cinnamon check used `MOOLTRACE_MAILTO` from the environment and `MOOLTRACE_OPENALEX_RPS=3`. The clone wrote `/tmp/mt-t12-qs/MoolTrace/data/mooltrace.db`. Repo `data/mooltrace.db` mtime stayed `1792153156`.

| Step | Command | Wall |
| --- | --- | --- |
| clone | `git clone https://origin.cursor.com/siddhant-vishnu/MoolTrace.git /tmp/mt-t12-qs/MoolTrace` | 3.02 s |
| install | `python3 -m venv .venv && .venv/bin/pip install -e .` | 9.67 s |
| check | `.venv/bin/python -m mooltrace check --url https://www.healthline.com/nutrition/cinnamon-and-diabetes --summary` | 52.37 s |
| **total** | clone + install + cinnamon `--summary` | **65.06 s** |

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
export MOOLTRACE_MAILTO=you@example.com
.venv/bin/python -m mooltrace check --url https://www.healthline.com/nutrition/cinnamon-and-diabetes --summary
```

Confirmed stdout (exit 2):

```
WARN (exit 2) — your answer rests on a study flagged with an Expression of Concern
healthline.com/nutrition/cinnamon-and-diabetes → Cinnamon as a Complementary Therapeutic Appro… (2022) (10.3390/nu14132773) → Cinnamon Improves Glucose and Lipids of Peopl… (2003) (10.2337/diacare.26.12.3215)
Flag: Expression of Concern 10.2337/dc25-ec09 (2025-08-20) · notices checked 35 s ago
What to do: disclose or replace this source. Run `mooltrace rewrite` to fix only the affected sentence.
Decided by: algo.SPpaths, path strength 0.55
```

Same URL via the README `check-answer` form (not re-fetched; same cinnamon page):

```bash
.venv/bin/python -m mooltrace check-answer \
  --urls-file <(printf '%s\n' 'https://www.healthline.com/nutrition/cinnamon-and-diabetes') \
  --engine nutrition-coach \
  --depth 2
```

## Live demo (signed-out)

| Claim | Command | Confirmed |
| --- | --- | --- |
| Home is public, no sign-up | `curl -sI https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/` | HTTP 200 |
| Click **Harvard vitamin D (block)** | `curl -sS -X POST …/nw/check-answer -d '{"text":"","urls":["https://nutritionsource.hsph.harvard.edu/vitamin-d/"],"engine":"nutrition-coach","depth":2}'` | **BLOCK (exit 1)**. `decided_by algo.SPpaths`. Seeded strength `0.4675` (docs print **0.47**). Hops `mention` 0.55 × `uses_data_or_method` 0.85. Ishida 2004 retraction `10.1016/j.amjmed.2004.05.019` (2004-10-15). **Why the graph decided**: `Direct DOI check: 0 notices → would ship  |  Graph depth 2: retraction 10.1016/j.amjmed.2004.05.019 → BLOCK`. Signed-out live 17 Oct 2026 10:37 UTC (`:mooltrace.api.15`). |
| Click **Healthline olive oil (warn)** | same POST, olive-oil URL, depth 3 | **WARN (exit 2)**. Strength `0.30250000000000005` (docs print **0.30**). Both hops `mention` 0.55. Retraction `10.1056/nejmc1806491` (2018-06-13) on Estruch 2013. Summary: cites a review that mentions a retracted trial (Estruch 2013); the review did not appear to rely on it. Hop trail hashes `350900e5…` / `583d26db…` (recorded live 16 Oct 2026 19:52 UTC). |
| Toggle olive-oil **depth 1** | same POST, `"depth":1` | **PASS (exit 0)**. 0 notice paths. Live throwaway DB 16 Oct 2026 19:51 UTC, wall 13.6 s. Seeded replay matches. |
| Toggle olive-oil **depth 2** | same POST, `"depth":2` | **WARN (exit 2)**. Same Estruch mention path as depth 3. Strength `0.30250000000000005`. |
| Click **Healthline cinnamon (warn)** | same POST, cinnamon URL, depth 2 | **WARN (exit 2)**. Strength `0.55`. Expression of Concern `10.2337/dc25-ec09`. Depth 1 is PASS (0 notice paths). |
| Clean study (pass) | same POST, text `10.1016/j.jsps.2015.03.013`, engine `clean-check` | **pass** exit 0 at depths 1, 2, and 3 |
| Click **Not in the graph** | same POST, NHS `https://www.nhs.uk/live-well/best-way-to-wash-your-hands/`, depth 2 | **WARN (exit 2)**. Coverage **expanded 0 of 0 cited works**. Summary: “Nothing in the graph connects this answer to a study. This is not proof it is safe; the source may not be modelled.” Recorded 16 Oct 2026T20:22:08Z, page hash `5c015843460b0e872bd9a0b01bf0c5bf91a810a04a9f21b72b0574b525495329`. Hosted signed-out POST 16 Oct 2026 (T18 / T20). |
| Oversized free-text | POST 40k-char draft | HTTP **413** `Draft or URL list is too large for the public demo.` |

The 2013 PREDIMED trial was retracted and republished in 2018 after re-analysis. Both olive-oil hops are `mention`; T26 PATH_RULE turns that into WARN. This does not say olive oil or the Mediterranean diet works or does not. Ishida 2004 is a retraction; Avenell 2014 called it an included trial.

Offline replay of the five recorded presets (no HTTP; throwaway graph; T26 PATH_RULE):

```
nutrition-harvard-vitamin-d block exit 1 strength 0.4675 decided algo.SPpaths
nutrition-olive-oil warn exit 2 strength 0.30250000000000005 decided algo.SPpaths
nutrition-healthline warn exit 2 strength 0.55 decided algo.SPpaths
clean-jsps pass exit 0 strength None decided algo.SPpaths
not-in-graph warn exit 2 coverage expanded 0 of 0 cited works
```

## Verdict table

| Verdict | Exit | Confirmed by |
| --- | --- | --- |
| pass | 0 | live clean preset; offline `clean-jsps`; `test_presets_recorded.py` |
| warn | 2 | live cinnamon; fresh-clone `--summary`; `examples/answers.jsonl` |
| block | 1 | Harvard vitamin D preset; `examples/lancet.jsonl` |
| error | 3 | `tests/test_graph.py::test_sp_paths_ablation_returns_exit_3` (`sp_paths` raised → exit 3, no verdict) |

README table rows: `| pass | 0 |`, `| block | 1 |`, `| error | 3 |`, warn is exit 2.

## CI fixtures

```bash
.venv/bin/python -m mooltrace batch examples/answers.jsonl --fail-on block
```

Confirmed 16 Oct 2026 18:10 UTC, throwaway `MOOLTRACE_DB=/tmp/mt-t12-answers/mooltrace.db`, OpenAlex RPS=3, 58.46 s. Exit **0**. Worst `warn`. `failed` false. Both rows warn exit 2 on EoC `10.2337/dc25-ec09` (`nutrition-everyday-health`, `allen-2013`). GitHub annotations: `::warning`. Repo `data/mooltrace.db` unused.

```bash
.venv/bin/python -m mooltrace batch examples/lancet.jsonl --fail-on block
```

Confirmed 16 Oct 2026 18:09 UTC, throwaway `/tmp/mt-t12-lancet/mooltrace.db`, 14.06 s. Exit **1**. `worst` block. `lancet-hcq` block exit 1. Retraction `10.1016/s0140-6736(20)31324-6` on Mehra 2020 `10.1016/s0140-6736(20)31180-6`.

## MCP

Remote MCP on hosted `:mooltrace.api.15` / `:mooltrace.web.16` (T31 pin, signed-out reconfirm 17 Oct 2026 10:37 UTC). Official Python `Client` against `/mcp`: tools `['check_answer', 'what_rests_on', 'recheck_affected']`. Harvard vitamin D `check_answer` is **block** exit 1, Ishida 2004 retraction `10.1016/j.amjmed.2004.05.019`, `why_graph.title` **Why the graph decided**. `what_rests_on` on that DOI: **This retraction affects 2 stored answers.** (shared demo graph; a throwaway seed of only that preset is 1). Olive-oil `check_answer` is WARN exit 2 (mention × mention). Seeded replay (no HTTP) matches `examples/presets_recorded.json`.

```
# seeded replay, throwaway graph, T26 PATH_RULE
nutrition-harvard-vitamin-d block exit 1 strength 0.4675
nutrition-olive-oil warn exit 2 strength 0.30250000000000005
```

Local one-command (after the venv above): `.venv/bin/python -m mooltrace mcp`. Point Cursor/Claude at `mcp.example.json` (`args` `["-m", "mooltrace.mcp_server"]`). Stdio has the full tool list. Confirmed this session: `TOOLS` 9 names including `rewrite_answer`; empty draft → warn exit 2 `no_sources`.

Recorded agent acting (17 Oct 2026, `cursor-agent -p --model cursor-grok-4.6-high-fast`): [examples/agent_runs/2026-10-17/](examples/agent_runs/2026-10-17/). With MCP: `check_answer` **BLOCK** exit 1 then `rewrite_answer`. Without: shipped the Harvard URL. Output may vary run to run.

## Baseline (no-graph vs MoolTrace)

```bash
.venv/bin/python -m mooltrace baseline --out results/baseline_2026-10-16.json
```

Confirmed offline 16 Oct 2026 18:06 UTC (recorded Crossref + recorded MoolTrace labelled run). T26 re-ran `.venv/bin/python -m mooltrace baseline --out results/baseline_2026-10-17_t26.json` on 17 Oct 2026 08:23 UTC; stored labelled decisions were not re-scored (no `hops_evidence` on those rows):

```
BASELINE scored 52/52 precision=1.0 recall=0.4286 multihop_only=15
MOOLTRACE scored 52/52 precision=0.8974 recall=1.0
```

| Checker | Precision | Recall | Exact 3-way |
| --- | --- | --- | --- |
| Direct-DOI (no graph) | 1.0 | 0.4286 | 0.6154 (32/52) |
| MoolTrace (`algo.SPpaths`) | 0.8974 | 1.0 | 0.9231 (48/52) |

15 only-multi-hop catches (MoolTrace warn, direct-DOI pass). Four labelled-pass disagreements keep precision at 0.8974. Labelling rule is in `examples/labelled.jsonl`. This is not a medical accuracy score.

Live labelled (52 isolated graphs) was **not** re-run this session (486.0 s on 16 Oct 2026 15:39 UTC; OpenAlex). Schema only:

```bash
.venv/bin/python -m mooltrace labelled
```

`pytest tests/test_labelled.py` — schema, no live catalogs. Dated scores stay in `results/baseline_2026-10-16.md`.

## VITALITY Study I (17 Oct 2026)

```bash
.venv/bin/python -m mooltrace vitality --out results/vitality_2026-10-17.json
```

T26 re-ran the same offline command 17 Oct 2026 08:23 UTC (`results/vitality_2026-10-17_t26.json`). Recorded Crossref + snapshot unchanged. Snapshot reasons have no `hops_evidence`, so T26 PATH_RULE did not re-score stored rows.

```
VITALITY baseline pos=0/40 ctrl=0/40
VITALITY mooltrace d2 same_trial=31/40 false_alarms=1/40 oa429=0+0 pending=0
VITALITY mooltrace d3 same_trial=14/18 false_alarms=1/40 oa429=0+0 pending=22
decision split (80 stored rows): 26 block / 11 warn / 43 pass
positives: 26 block / 10 warn / 4 pass; controls: 39 pass / 1 warn
```

| Slice | Result |
| --- | --- |
| Direct-DOI positives flagged | 0/40 |
| Direct-DOI controls flagged | 0/40 |
| MoolTrace same-trial recall (finished, depth 2) | 31/40 |
| Counted notice (finished, depth 2) | 26/40 |
| False alarms (finished controls, depth 2) | 1/40 |
| Sampled-15 same-trial (depth 2) | 12/15 |
| MoolTrace same-trial recall (finished, depth 3) | 14/18 |
| Counted notice (finished, depth 3) | 10/18 |
| False alarms (finished controls, depth 3) | 1/40 |
| Pending depth 3 | 22 extra positives |

Depth 2 headline is **31/40** same-trial and **1/40** false alarms (`ctrl-35` / `10.1002/14651858.cd013856` warned unverified on withdrawn Cochrane `10.1002/14651858.cd006789`; not a VITALITY-named trial; not relabelled). Depth 3 is a separate recorded row: **14/18** same-trial, **1/40** false alarms (same `ctrl-35`), **22** extra positives pending. Labels frozen 16 Oct 2026 from Xu et al. BMJ 2025 / OSF osf.io/7eazq. Control check is in `examples/vitality.json`. This is not a medical accuracy score.

## Agent loop (offline)

```bash
.venv/bin/python examples/agent_loop.py
```

Confirmed exit 0:

```
1. check_answer → warn (exit 2)
   algorithm: algo.SPpaths
2. explain_path → warn
3. what_rests_on → This Expression of Concern affects 1 stored answer.
4. rewrite_answer → template recheck pass
5. recheck_affected → 1 counted answers
```

## Graph decides / flip / ablation

```bash
.venv/bin/python -m pytest tests/test_graph.py::test_sp_weight_flip_changes_verdict tests/test_graph.py::test_sp_paths_ablation_returns_exit_3 tests/test_graph.py::test_sp_paths_strength_equals_brute_force_product -q
```

Confirmed: `3 passed in 24.92s`. Weight 0.85 → warn, 0.2 → pass; `sp_paths` raised → exit 3; algorithm strength equals brute-force product.

`algo.pageRank` is **not** called (`tests/test_pagerank_unused.py`). `algo.WCC` is remediation clusters only (Lancet batch payload includes `algorithm: algo.WCC`).

## Local Compose demo

```bash
docker compose up --build
```

**Not booted this session** (Lightsail already serves the hosted demo). Confirmed `docker compose config`: services `api` / `web`; published `127.0.0.1:4317` and `127.0.0.1:4318`; `MOOLTRACE_DB=/data/demo.db`; `MOOLTRACE_PUBLIC_DEMO=1`. Volume is not `data/mooltrace.db`.

## Offline unit suite

```bash
unshare --net --map-root-user .venv/bin/python -m pytest -q
```

17 Oct 2026 10:57 UTC this checkout: 326 passed, 0 failed, 477.25 s, network namespace unshared.

## Limits quoted in README (spot-checks)

| Claim | Command | Confirmed |
| --- | --- | --- |
| Khan 2003 is an Expression of Concern, not a retraction | cinnamon `--summary` / live warn preset | Flag `10.2337/dc25-ec09` (2025-08-20), notice type `expression_of_concern` |
| Mehra / Lancet 2020 retracted | `batch examples/lancet.jsonl --fail-on block` | block; notice `10.1016/s0140-6736(20)31324-6` |
| Estruch 2013 retracted and republished | live olive-oil POST | retraction `10.1056/nejmc1806491` (2018-06-13) |
| SSRF refuses loopback / private / credentials | `pytest tests/test_ssrf.py` | passed this session |
| Rewrite changes only the flagged sentence; never `RETRACTED:`; never the notice DOI | `pytest tests/test_rewrite.py::test_rewrite_hcq_mehra_2020_only_flagged_sentence` | passed this session |
| Hosted live URL is allow-listed | POST a non-preset `healthline.com` URL with `MOOLTRACE_PUBLIC_LIVE=1`; `example.com` is 400 | allow-list + SSRF + per-IP 429 + concurrency 1 + 120 s timeout. Presets never 429. UI: Running live, about 60 s. `pytest tests/test_public_live.py` |
| `assets/demo-harvard-depth-toggle.gif` and `assets/demo-harvard-vitamin-d-block.png` are signed-out 1280×800 live captures | headless Playwright Chromium of `https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/?preset=harvard-vitamin-d`, 17 Oct 2026 11:44 UTC; cookies 0; no sign-in; GIF is depth 1 PASS then depth 2 BLOCK with **Why the graph decided** in the 800 px viewport (`:mooltrace.api.15` / `:mooltrace.web.16`) | not localhost; not synthetic |
| `assets/healthline-warn.png` is a signed-out WARN capture | local seeded `http://127.0.0.1:4318/?preset=healthline`, 17 Oct 2026; live host `:mooltrace.api.15` / `:mooltrace.web.16` same WARN | path strength 0.55, EoC `10.2337/dc25-ec09`; not 0.72 |

## Seeded gate (three runs, 17 Oct 2026 10:36–10:44 UTC)

```bash
MOOLTRACE_OPENALEX_RPS=3 \
MOOLTRACE_HTTP_CACHE=/tmp/mt-t26-audit-gate-cache MOOLTRACE_DB=/tmp/mt-t26-audit-unused/mooltrace.db \
.venv/bin/python -m mooltrace.gate
```

`data/mooltrace.db` mtime stayed `1792233098` through the three runs (offline pytest later opened the default path). Shared HTTP cache; run 1 is the cold HTTP walk. No case flipped vs T26 `results/gate_2026-10-17_t26_run1.json`: Khan-path positives stay **warn** (EoC); Lancet 2020 stays **block** (direct 1-hop retraction).

| Run | caught | alarms | wall_s | ran_at | Allen 2013 |
| --- | --- | --- | --- | --- | --- |
| 1 | 7/7 | 0/6 | 206.1 | 2026-10-17T10:39:49+00:00 | warn, hops=2, `uses_data_or_method` 0.85 |
| 2 | 7/7 | 0/6 | 114.2 | 2026-10-17T10:42:20+00:00 | warn, hops=2, `uses_data_or_method` 0.85 |
| 3 | 7/7 | 0/6 | 129.0 | 2026-10-17T10:44:29+00:00 | warn, hops=2, `uses_data_or_method` 0.85 |

Files: `results/gate_2026-10-17_t26r3_run1.json`, `run2`, `run3`.

## Prior art (re-fetched 17 Oct 2026 10:37 UTC)

`pytest tests/test_readme.py::test_readme_prior_art_links_verified_repos` — shaky-ground, scite, GhostCite, Bedrock links. Signed-out HEAD of https://shaky-ground-production.up.railway.app/ still returns **HTTP 501** (Railway). A normal GET on 17 Oct 2026 10:37 UTC returned **HTTP 200** (title “Shaky Ground”, no sign-up; Blast radius / Foundation check UI). `GET /api/config` is `allow_runs: false`. Tracing a DOI not already in their graph is refused (`GET /api/blast?paper=10.1056/nejmoa1200303` → HTTP **404**, “is not in this server's graph, and the server is read only”). GitHub repos `aryangorde6/shaky-ground`, `musharna/ghostcite`, `ibnweb3/bedrock` returned HTTP 200. `scite.ai/features` was not re-fetched this session. Raw `shaky/retractionwatch.py` line 61 still keeps only `RetractionNature == "Retraction"`. Last `aryangorde6/shaky-ground` push 2026-10-16T10:08:35Z.

## Not re-run this session

| Claim | Why |
| --- | --- |
| Cold Healthline 47.09 s / 49.18 s / 49.10 s | Replaced by the T12 fresh-clone 52.37 s check (RPS=3); not re-timed in T21 |
| Warm Healthline 23.16 s | Not repeated |
| Fresh-clone quickstart 65.06 s | T12 `/tmp` timing; not re-cloned in T21 |
| `docker compose up --build` | Config confirmed; public demo already live |
| Live `mooltrace labelled` (52 cases) | Offline baseline reproduce + schema test |
