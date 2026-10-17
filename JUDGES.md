# Judges — 5-minute path

Track 01: **Agents That Act on Connected Data**. No sign-up.

## 1. Open the live demo, click BLOCK, read the path (90 s)

https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/

Click **Harvard vitamin D (block)**. You should see **BLOCK** (exit 1), path strength **0.47**, hops `mention` 0.55 × `uses_data_or_method` 0.85, and Ishida 2004 retraction `10.1016/j.amjmed.2004.05.019` (2004-10-15). `Decided by: algo.SPpaths`. The **Why the graph decided** panel reads `Direct DOI check: 0 notices → would ship  |  Graph depth 2: retraction 10.1016/j.amjmed.2004.05.019 → BLOCK`. The Cochrane review called Ishida an included trial. This does not say vitamin D works or does not.

Click **Healthline olive oil (warn)**. Toggle **depth 1**: **PASS** (0 notice paths). Toggle **depth 3**: **WARN** (exit 2), path strength **0.30**, both hops `mention` 0.55, Estruch 2013 retraction `10.1056/nejmc1806491` (2018-06-13). The review did not appear to rely on the trial. The 2013 trial was retracted and republished in 2018 after re-analysis. This does not say olive oil or the Mediterranean diet works or does not.

Click **Healthline cinnamon (warn)** for an Expression of Concern (`relies` 1.0, path strength **0.55**). Depth 1 is PASS; depth 2/3 is WARN. An Expression of Concern is not a retraction.

Click **Not in the graph**. This is the NHS page “How to wash your hands” (`https://www.nhs.uk/live-well/best-way-to-wash-your-hands/`), fetched 2026-10-16T20:22:08+00:00, content hash `5c015843460b0e872bd9a0b01bf0c5bf91a810a04a9f21b72b0574b525495329`. The page has no scholarly citations. You should see **WARN** and “Nothing in the graph connects this answer to a study. This is not proof it is safe; the source may not be modelled.” Coverage: **expanded 0 of 0 cited works**. That is not a pass, and it is not proof the page is safe.

Every verdict also prints a coverage line (`expanded X of Y cited works`) instead of treating leftover expansion as a scary incomplete flag when a notice path already decides.

Optional: paste your own URL that is **not** a preset, from `healthline.com`, `everydayhealth.com`, `verywellhealth.com`, `medicalnewstoday.com`, `webmd.com`, `pubmed.ncbi.nlm.nih.gov`, or `doi.org`. The UI shows **Running live, about 60 s**. One live check at a time; presets stay instant. Other domains are refused. SSRF, a size cap, a per-IP rate limit, and a 120 s hard stop still apply.

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
