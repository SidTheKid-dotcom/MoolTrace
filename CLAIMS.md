# CLAIMS

Every README claim → the command that proves it. Confirmed 16 Oct 2026 in this checkout unless a row says otherwise. Do not treat these as a medical accuracy score. An Expression of Concern is not a retraction. Track 01: **Agents That Act on Connected Data**.

Live demo (no sign-up): https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/

Remote MCP: https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/mcp

Five-minute path: [JUDGES.md](JUDGES.md).

## Fresh-clone quickstart

Fresh-clone quickstart wall time on 16 Oct 2026: **65.06 s**.

Literal README 3-line run from a fresh clone in `/tmp` (16 Oct 2026 18:06–18:08 UTC). Clone from `origin.cursor.com`. `pip` used the local wheel cache. Cinnamon check used `MOOLTRACE_MAILTO=siddhant.m.vishnu@gmail.com` and `MOOLTRACE_OPENALEX_RPS=3`. The clone wrote `/tmp/mt-t12-qs/MoolTrace/data/mooltrace.db`. Repo `data/mooltrace.db` mtime stayed `1792153156`.

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
| Click **Healthline olive oil (block)** | `curl -sS -X POST …/nw/check-answer -d '{"text":"","urls":["https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil"],"engine":"nutrition-coach","depth":3}'` | **BLOCK (exit 1)**. `decided_by algo.SPpaths`. Strength `0.30250000000000005` (docs print **0.30**). Both hops `mention` 0.55. Retraction `10.1056/nejmc1806491` (2018-06-13) on Estruch 2013. Hop trail hashes `6bf731b6…` / `ad5e550c…`. |
| Click **Healthline cinnamon (warn)** | same POST, cinnamon URL, depth 2 | **WARN (exit 2)**. Strength `0.55`. Expression of Concern `10.2337/dc25-ec09`. |
| Clean study (pass) | same POST, text `10.1016/j.jsps.2015.03.013`, engine `clean-check` | **pass** exit 0, no reasons |
| Oversized free-text | POST 40k-char draft | HTTP **413** `Draft or URL list is too large for the public demo.` |

The 2013 PREDIMED trial was retracted and republished in 2018 after re-analysis. Both olive-oil hops are `mention`. This does not say olive oil or the Mediterranean diet works or does not.

Offline replay of the same three recorded presets (no HTTP; throwaway graph):

```
nutrition-olive-oil block exit 1 strength 0.30250000000000005 decided algo.SPpaths
nutrition-healthline warn exit 2 strength 0.55 decided algo.SPpaths
clean-jsps pass exit 0 strength None decided algo.SPpaths
```

## Verdict table

| Verdict | Exit | Confirmed by |
| --- | --- | --- |
| pass | 0 | live clean preset; offline `clean-jsps`; `test_presets_recorded.py` |
| warn | 2 | live cinnamon; fresh-clone `--summary`; `examples/answers.jsonl` |
| block | 1 | live olive-oil; `examples/lancet.jsonl` |
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

Remote (official Python `Client`, 16 Oct 2026 18:41 UTC, signed-out):

```
tools ['check_answer', 'what_rests_on', 'recheck_affected']
check_answer block exit 1
notice retraction 10.1056/nejmc1806491 score 0.30250000000000005
decided_by algo.SPpaths
what_rests_on This retraction affects 1 stored answer. counted 1
```

Hosted `recheck_affected` on the same olive-oil notice still returns **warn exit 2 incomplete** (`MoolTrace could not finish this pre-ship check`) on the live `api.5` image. Cause: recheck stuffed first-hop work DOIs into draft text, minting a new answer id. Local main after `dc032d0` replays URL-only inputs and blocks (`test_public_demo_recheck_affected_replays_olive_oil_block`). Keep `recheck_affected` off camera until Lightsail is rebuilt from that commit.

Local one-command (after the venv above): `.venv/bin/python -m mooltrace mcp`. Point Cursor/Claude at `mcp.example.json` (`args` `["-m", "mooltrace.mcp_server"]`). Stdio has the full tool list. Confirmed this session: `TOOLS` 9 names including `rewrite_answer`; empty draft → warn exit 2 `no_sources`.

## Baseline (no-graph vs MoolTrace)

```bash
.venv/bin/python -m mooltrace baseline --out results/baseline_2026-10-16.json
```

Confirmed offline 16 Oct 2026 18:06 UTC (recorded Crossref + recorded MoolTrace labelled run):

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

**Not booted this session** (Lightsail already serves the same three presets). Confirmed `docker compose config`: services `api` / `web`; published `127.0.0.1:4317` and `127.0.0.1:4318`; `MOOLTRACE_DB=/data/demo.db`; `MOOLTRACE_PUBLIC_DEMO=1`. Volume is not `data/mooltrace.db`.

## Offline unit suite

```bash
unshare --net --map-root-user .venv/bin/python -m pytest -q
```

17 Oct 2026 this checkout: 266 passed, 0 failed, 421.76 s, network namespace unshared.

## Limits quoted in README (spot-checks)

| Claim | Command | Confirmed |
| --- | --- | --- |
| Khan 2003 is an Expression of Concern, not a retraction | cinnamon `--summary` / live warn preset | Flag `10.2337/dc25-ec09` (2025-08-20), notice type `expression_of_concern` |
| Mehra / Lancet 2020 retracted | `batch examples/lancet.jsonl --fail-on block` | block; notice `10.1016/s0140-6736(20)31324-6` |
| Estruch 2013 retracted and republished | live olive-oil POST | retraction `10.1056/nejmc1806491` (2018-06-13) |
| SSRF refuses loopback / private / credentials | `pytest tests/test_ssrf.py` | passed this session |
| Rewrite changes only the flagged sentence; never `RETRACTED:`; never the notice DOI | `pytest tests/test_rewrite.py::test_rewrite_hcq_mehra_2020_only_flagged_sentence` | passed this session |
| Hosted free-text is presets-only | oversize POST | 413 |
| `assets/healthline-warn.png` is a signed-out live WARN capture | `/?preset=healthline` on the Lightsail demo, 17 Oct 2026 | path strength 0.55, EoC `10.2337/dc25-ec09`; not 0.72 |

## Seeded gate (T14, three runs)

```bash
MOOLTRACE_MAILTO=siddhant.m.vishnu@gmail.com MOOLTRACE_OPENALEX_RPS=3 \
MOOLTRACE_HTTP_CACHE=/tmp/mt-t14-gate-cache MOOLTRACE_DB=/tmp/mt-t14-unused/mooltrace.db \
.venv/bin/python -m mooltrace.gate
```

`data/mooltrace.db` mtime stayed `1792153156`. Shared HTTP cache; run 1 is the cold HTTP walk.

| Run | caught | alarms | wall_s | ran_at | Allen 2013 |
| --- | --- | --- | --- | --- | --- |
| 1 | 7/7 | 0/6 | 150.4 | 2026-10-16T18:43:02+00:00 | warn, hops=2, `uses_data_or_method` 0.85 |
| 2 | 7/7 | 0/6 | 97.0 | 2026-10-16T18:45:03+00:00 | warn, hops=2, `uses_data_or_method` 0.85 |
| 3 | 7/7 | 0/6 | 98.5 | 2026-10-16T18:51:18+00:00 | warn, hops=2, `uses_data_or_method` 0.85 |

Files: `results/gate_2026-10-16_t14_run1.json`, `run2`, `run3`.

## Prior art (re-fetched 16 Oct 2026 18:43 UTC)

`pytest tests/test_readme.py::test_readme_prior_art_links_verified_repos` — shaky-ground, scite, GhostCite, Bedrock links. Signed-out HEAD of https://shaky-ground-production.up.railway.app/ returned **HTTP 501**. GitHub repos `aryangorde6/shaky-ground`, `musharna/ghostcite`, `ibnweb3/bedrock` returned HTTP 200. `scite.ai/features` returned HTTP 403 from this host (CloudFront). Raw `shaky/retractionwatch.py` line 61 still keeps only `RetractionNature == "Retraction"`.

## Not re-run this session

| Claim | Why |
| --- | --- |
| Cold Healthline 47.09 s / 49.18 s / 49.10 s | Replaced by the T12 fresh-clone 52.37 s check (RPS=3); not re-timed in T14 |
| Warm Healthline 23.16 s | Not repeated |
| Fresh-clone quickstart 65.06 s | T12 `/tmp` timing; not re-cloned in T14 |
| `docker compose up --build` | Config confirmed; public demo already live |
| Live `mooltrace labelled` (52 cases) | Offline baseline reproduce + schema test |
| Lightsail rebuild after `dc032d0` | Hosted `recheck_affected` still warn/incomplete on `api.5` |
