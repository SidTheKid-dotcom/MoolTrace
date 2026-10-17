# Judges — 5-minute path

Track 01: **Agents That Act on Connected Data**. No sign-up.

WeMakeDevs COO judging guide (15 Oct 2026): https://www.wemakedevs.org/blogs/how-to-build-an-agent-that-reasons-over-a-graph

## WeMakeDevs judging guide -> where MoolTrace does it

| Guide item | Where MoolTrace does it |
| --- | --- |
| Graph does work the agent could not do without it | Same Harvard URL: Direct-DOI would ship (`mooltrace/graph_why.py:44`); graph depth 2 **BLOCK** (`examples/presets_recorded.json:472`; live signed-out `https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/?preset=harvard-vitamin-d`). Recorded agent: with MCP ships the rewrite (`examples/agent_runs/2026-10-17/run_a_with_mooltrace.txt:2`); without ships the Harvard citation (`examples/agent_runs/2026-10-17/run_b_without_mooltrace.txt:4`). Labelled no-graph misses: `results/baseline_2026-10-16.json`. |
| Same question at depth 1, then deeper, with the path | Live signed-out Harvard toggle this session: depth 1 **PASS** (exit 0, 0 notice paths, Why `Graph depth 1: 0 notice paths → PASS`) then depth 2 **BLOCK** (exit 1, `mention` × `uses_data_or_method`, Why panel names Ishida 2004). Recorded: `examples/presets_recorded.json:459` / `examples/presets_recorded.json:472`. UI nudge `web/src/components/pre-ship.tsx:737`. |
| Ask something not in the graph and let it say so | Click **Not in the graph** on the live demo. WARN, “Nothing in the graph connects this answer to a study. This is not proof it is safe; the source may not be modelled.” (`mooltrace/decision.py:41`, `mooltrace/decision.py:458`; preset `web/src/components/pre-ship.tsx:174`). |
| Fixed tool catalogue; model never writes Cypher; params validated | Hosted MCP is only `check_answer`, `what_rests_on`, `recheck_affected` (`mooltrace/mcp_http.py:3`). Depth is `Field(ge=1, le=3)` (`mooltrace/mcp_http.py:78`). Local stdio also exposes `ro_cypher` (`mooltrace/mcp_server.py:249`); writes are rejected. In-app agent (`POST /nw/agent`, `mooltrace/api.py:184`) may call only `check_answer`, `explain_path`, `rewrite_answer`, `what_rests_on` (`mooltrace/agent.py:109`). URLs go through the public-demo allow-list; DOIs must already be in the graph. The model does not compose the verdict query. |
| Resolve names against the DB | `check_study` resolves a DOI/PMID then `MATCH (w:Work {doi: $doi})` (`mooltrace/trace.py:1269`, `mooltrace/graph.py:443`). Rewrite author/year comes from `graph.work_row` (`mooltrace/rewrite.py:296`). Remote reverse-lookup DOIs must be a recorded preset notice unless live fetch is on (`mooltrace/public_demo.py:265`). This is Work/DOI lookup, not Blast Radius service-name resolution. |
| Algorithms as tools (`algo.SPpaths` etc) | Verdict is `CALL algo.SPpaths` inside `check_answer` (`mooltrace/cypher.py:52`, `mooltrace/graph.py:511`). It is not a separate MCP tool named `algo.SPpaths`. `algo.pageRank` is registered in FalkorDBLite and is **not** called (`tests/test_pagerank_unused.py:1`). Embedded FalkorDBLite (`mooltrace/graph.py:3`), not FalkorDB Cloud. |
| Memory is more nodes | Each check `MERGE`s an `Answer` node (`mooltrace/graph.py:241`); `what_rests_on` counts stored answers (`mooltrace/mcp_http.py:103`). There is no dated “answered from memory” outcome. |
| Return the path with the answer; check the sentence against graph rows | `nodes(path)` and hop sentences return with the verdict (`mooltrace/cypher.py:69`; Why panel `web/src/components/pre-ship.tsx:301`). Rewrite text is filled from those rows (`mooltrace/rewrite.py:3`). In-app agent grounding (`mooltrace/agent.py:665`): every DOI, author-year, and URL in the shipped text must appear in the tool results, else the deterministic rewrite is shipped. This is not Blast Radius `accepts()`. |

## 1. Open the live demo, click BLOCK, read the path (90 s)

https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/

Click **Harvard vitamin D (block)**. You should see **BLOCK** (exit 1), path strength **0.47**, hops `mention` 0.55 × `uses_data_or_method` 0.85, and Ishida 2004 retraction `10.1016/j.amjmed.2004.05.019` (2004-10-15). `Decided by: algo.SPpaths`. The **Why the graph decided** panel reads `Direct DOI check: 0 notices → would ship  |  Graph depth 2: retraction 10.1016/j.amjmed.2004.05.019 → BLOCK`. The Cochrane review called Ishida an included trial. This does not say vitamin D works or does not.

Click **Healthline olive oil (warn)**. Toggle **depth 1**: **PASS** (0 notice paths). Toggle **depth 3**: **WARN** (exit 2), path strength **0.30**, both hops `mention` 0.55, Estruch 2013 retraction `10.1056/nejmc1806491` (2018-06-13). The review did not appear to rely on the trial. The 2013 trial was retracted and republished in 2018 after re-analysis. This does not say olive oil or the Mediterranean diet works or does not.

Click **Healthline cinnamon (warn)** for an Expression of Concern (`relies` 1.0, path strength **0.55**). Depth 1 is PASS; depth 2/3 is WARN. An Expression of Concern is not a retraction.

Click **Not in the graph**. This is the NHS page “How to wash your hands” (`https://www.nhs.uk/live-well/best-way-to-wash-your-hands/`), fetched 2026-10-16T20:22:08+00:00, content hash `5c015843460b0e872bd9a0b01bf0c5bf91a810a04a9f21b72b0574b525495329`. The page has no scholarly citations. You should see **WARN** and “Nothing in the graph connects this answer to a study. This is not proof it is safe; the source may not be modelled.” Coverage: **expanded 0 of 0 cited works**. That is not a pass, and it is not proof the page is safe.

Every verdict also prints a coverage line (`expanded X of Y cited works`) instead of treating leftover expansion as a scary incomplete flag when a notice path already decides.

Optional: paste your own URL that is **not** a preset, from `healthline.com`, `everydayhealth.com`, `verywellhealth.com`, `medicalnewstoday.com`, `webmd.com`, `pubmed.ncbi.nlm.nih.gov`, `doi.org`, or `nutritionsource.hsph.harvard.edu`. The UI shows **Running live, about 60 s**. One live check at a time; presets stay instant. Other domains are refused. SSRF, a size cap, a per-IP rate limit, and a 120 s hard stop still apply.

## 2. One CLI command (90 s)

```bash
python3 -m venv .venv && .venv/bin/pip install -e . && export MOOLTRACE_MAILTO=you@example.com
.venv/bin/python -m mooltrace batch examples/lancet.jsonl --fail-on block; echo $?
```

Expect exit **1** (Lancet HCQ retraction `10.1016/s0140-6736(20)31324-6`). `examples/answers.jsonl` warns and exits 0 under `--fail-on block`.

Fresh-clone quickstart (clone + `pip install -e .` + cinnamon `--summary`) was **65.06 s** from `/tmp` on 16 Oct 2026. Commands and outputs: [CLAIMS.md](CLAIMS.md).

Sealed VITALITY (Xu et al., BMJ 2025): `.venv/bin/python -m mooltrace vitality --out results/vitality_2026-10-17.json`. Depth 2, n=40+40: Direct-DOI **0/40** and **0/40**; MoolTrace same-trial **31/40**; false alarms **1/40**. T26 stored-row split: **26 block / 11 warn / 43 pass** (snapshot has no `hops_evidence`, so PATH_RULE was not re-scored). Depth 3 (separate row; 18 positives + 40 controls finished, 22 extra positives pending): same-trial **14/18**; false alarms **1/40**. Do not replace the depth-2 headline. Not a medical accuracy score.

## 3. See an MCP call (2 min)

**Remote (no install).** Cursor or Claude Desktop:

```json
{
  "mcpServers": {
    "mooltrace": {
      "url": "https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/mcp"
    }
  }
}
```

Claude Desktop can also use `"type": "http"` next to `url`. Tools are only `check_answer`, `what_rests_on`, `recheck_affected`. Call `check_answer` with the Harvard vitamin D preset:

```json
{
  "text": "",
  "urls": ["https://nutritionsource.hsph.harvard.edu/vitamin-d/"],
  "engine": "nutrition-coach",
  "depth": 2
}
```

Expect **block**, exit 1, retraction `10.1016/j.amjmed.2004.05.019`, path strength `0.4675`, hops `mention` × `uses_data_or_method`, `decided_by: algo.SPpaths`. Seeded replay of the recorded hops (T25 live 17 Oct 2026; T26 PATH_RULE).

Olive-oil MCP at depth 3 is **warn**, exit 2, Estruch 2013 mention × mention, path strength `0.3025`.

Presets never 429.

**Local (one command).** After the venv from step 2:

```bash
.venv/bin/python -m mooltrace mcp
```

Point Cursor/Claude at `mcp.example.json` (`command` is this venv's `python`, `args` `["-m", "mooltrace.mcp_server"]`). That stdio server has the full tool list, including `rewrite_answer` and `ro_cypher`.

## 4. Agent acting (2 min)

Track 01 is **Agents That Act on Connected Data**. On the live (or local) demo, click **Harvard vitamin D (block)** then **Run the agent**. `POST /nw/agent` (`mooltrace/api.py:184`) runs `check_answer` → `explain_path` → `rewrite_answer` → `what_rests_on` with a 6-call cap. Azure OpenAI `gpt-5.4-mini` is used when a key and budget remain; otherwise the UI labels **rule-based fallback, no model**. The shipped column is the graph-checked rewrite; **without MoolTrace** is a tool-less model call or the draft unchanged. Grounding (`mooltrace/agent.py:665`) rejects invented citations.

A recorded `cursor-agent -p --model cursor-grok-4.6-high-fast` pair on 17 Oct 2026 asked the same consumer question (“Does vitamin D help prevent fractures in older adults?”) and required a citation of the Harvard BLOCK page. Files: [examples/agent_runs/2026-10-17/](examples/agent_runs/2026-10-17/). Output may vary run to run.

- **With** local stdio MCP on a throwaway graph seeded from the recorded presets: the agent called `check_answer`, got **BLOCK** (exit 1, Ishida 2004 retraction `10.1016/j.amjmed.2004.05.019`, path strength `0.4675`), called `rewrite_answer`, and shipped the rewritten text. The first sentence stayed; the citing sentence became the Ishida 2004 retraction disclosure.
- **Without** MoolTrace: the agent found no `check_answer` tool and shipped the consumer claim citing `https://nutritionsource.hsph.harvard.edu/vitamin-d/`.

This does not say vitamin D works or does not.
