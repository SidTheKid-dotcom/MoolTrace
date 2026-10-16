# Judges — 5-minute path

Track 01: **Agents That Act on Connected Data**. No sign-up.

## 1. Open the live demo, click BLOCK, read the path (90 s)

https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/

Click **Healthline olive oil (block)**. You should see **BLOCK** (exit 1), path strength **0.30**, both hops `mention` 0.55, and Estruch 2013 retraction `10.1056/nejmc1806491` (2018-06-13). `Decided by: algo.SPpaths`. The 2013 trial was retracted and republished in 2018 after re-analysis. This does not say olive oil or the Mediterranean diet works or does not.

Click **Healthline cinnamon (warn)** for an Expression of Concern (`relies` 1.0, path strength **0.55**). An Expression of Concern is not a retraction.

## 2. One CLI command (90 s)

```bash
python3 -m venv .venv && .venv/bin/pip install -e . && export MOOLTRACE_MAILTO=you@example.com
.venv/bin/python -m mooltrace batch examples/lancet.jsonl --fail-on block; echo $?
```

Expect exit **1** (Lancet HCQ retraction `10.1016/s0140-6736(20)31324-6`). `examples/answers.jsonl` warns and exits 0 under `--fail-on block`.

Fresh-clone quickstart (clone + `pip install -e .` + cinnamon `--summary`) was **65.06 s** from `/tmp` on 16 Oct 2026. Commands and outputs: [CLAIMS.md](CLAIMS.md).

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

Claude Desktop can also use `"type": "http"` next to `url`. Tools are only `check_answer`, `what_rests_on`, `recheck_affected`. Call `check_answer` with the olive-oil preset:

```json
{
  "text": "",
  "urls": ["https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil"],
  "engine": "nutrition-coach",
  "depth": 3
}
```

Expect **block**, exit 1, retraction `10.1056/nejmc1806491`, path strength `0.3025`, `decided_by: algo.SPpaths`. Confirmed with the official Python MCP `Client` against that URL on 16 Oct 2026 18:09 UTC:

```
tools ['check_answer', 'what_rests_on', 'recheck_affected']
check_answer block exit 1
notice retraction 10.1056/nejmc1806491 score 0.30250000000000005
```

Presets never 429.

**Local (one command).** After the venv from step 2:

```bash
.venv/bin/python -m mooltrace mcp
```

Point Cursor/Claude at `mcp.example.json` (`command` is this venv's `python`, `args` `["-m", "mooltrace.mcp_server"]`). That stdio server has the full tool list, including `rewrite_answer` and `ro_cypher`.
