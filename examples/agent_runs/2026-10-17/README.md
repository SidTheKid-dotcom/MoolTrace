# Recorded agent run — 17 Oct 2026

Track 01: **Agents That Act on Connected Data**.

One `cursor-agent` session pair on the Harvard vitamin D BLOCK preset page (`https://nutritionsource.hsph.harvard.edu/vitamin-d/`). **Output may vary run to run.** This folder is that day's transcript, not a guarantee of later runs.

- Date: 17 Oct 2026
- Model: `cursor-grok-4.6-high-fast`
- Consumer question in `prompt.txt`: “Does vitamin D help prevent fractures in older adults?”
- Demo graph: throwaway `MOOLTRACE_DB`, seeded `mooltrace.seed --offline` from `examples/presets_recorded.json`. `data/mooltrace.db` was not used.

## Commands

Same prompt file for both runs. Machine paths below are placeholders. Do not commit a project `.cursor/mcp.json` that holds a home directory or a personal mailbox.

Seed (shell `MOOLTRACE_MAILTO` only; not stored in this folder):

```bash
export MOOLTRACE_DB=/tmp/throwaway-mooltrace-graph/mooltrace.db
export MOOLTRACE_PUBLIC_DEMO=1
.venv/bin/python -m mooltrace.seed --offline
```

Temp project `.cursor/mcp.json` for Run A pointed `command` at this repo's `.venv/bin/python` and `args` at a local logging wrapper that calls `mooltrace.mcp_server.main()` — the same stdio server as:

```bash
.venv/bin/python -m mooltrace mcp
```

Env on that server: `MOOLTRACE_DB` = the throwaway graph, `MOOLTRACE_PUBLIC_DEMO=1` (preset replay, no live OpenAlex). User-level `~/.cursor/mcp.json` was emptied for these two runs so the agent would not attach the shared graph.

Run A (with MoolTrace):

```bash
cursor-agent -p --model cursor-grok-4.6-high-fast \
  --output-format stream-json \
  --trust --approve-mcps --force --sandbox disabled \
  --workspace /tmp/temp-project-with-mcp \
  "$(cat prompt.txt)"
```

Started 2026-10-17T11:06:23Z, ended 2026-10-17T11:06:57Z.

Run B (no MoolTrace): same `cursor-agent` line, empty project `mcpServers`, workspace `/tmp/temp-project-without-mcp`. Started 2026-10-17T11:07:19Z, ended 2026-10-17T11:10:26Z.

## What this recording shows

**Run A** (`run_a_with_mooltrace.stream.jsonl`, `run_a_mcp_calls.json`): the agent called MCP `check_answer` on its two-sentence draft plus the Harvard URL, engine `nutrition-coach`, depth 2. The tool returned **block**, exit 1, Ishida 2004 retraction `10.1016/j.amjmed.2004.05.019`, `algo.SPpaths` path strength `0.4675`. It then called `rewrite_answer` with the same arguments. `rewritten` was true. The first sentence stayed; the citing sentence became the Ishida 2004 retraction disclosure. The agent shipped that rewritten `text`:

```
SHIPPED:
For most older adults who already get enough vitamin D, extra supplements have not been shown to prevent broken bones. An earlier version of this answer cited Ishida et al. 2004; that paper was retracted on 15 Oct 2004, so this claim was removed.
```

**Run B** (`run_b_without_mooltrace.stream.jsonl`): no MoolTrace tools were configured. The stream shows the agent looking for `check_answer` / `rewrite_answer` and then shipping the citing draft:

```
SHIPPED:
For most older adults who already get enough vitamin D, extra supplements have not been shown to prevent broken bones. Harvard's Nutrition Source reviews this evidence at https://nutritionsource.hsph.harvard.edu/vitamin-d/.
```

This does not say vitamin D works or does not. An Expression of Concern is not a retraction. The Ishida 2004 notice in this recording is a retraction.

**Date bug in this recording:** the shipped rewrite says “retracted on 15 Oct 2004” and `notice_date` is `2004-10-15` with `notice_doi` equal to the article DOI. That text was produced by the old Crossref in-place `updated-by` bug (the 2004-10-15 value is the article publication date). The real notice is `10.1016/j.amjmed.2025.03.001`, May 2025 (PubMed PMID 15465502 RetractionIn PMID 40222753). The JSONL/JSON/TXT transcripts above are left byte-identical.

## Files

| File | What it is |
| --- | --- |
| `prompt.txt` | Exact prompt given to both runs |
| `run_a_with_mooltrace.stream.jsonl` | Raw `cursor-agent --output-format stream-json` for Run A |
| `run_a_with_mooltrace.txt` | Final assistant text containing `SHIPPED:` |
| `run_a_mcp_calls.json` | Wrapper log of MCP arguments and results |
| `run_a_host_mcp_tool_events.json` | Host `mcpToolCall` start/complete events from the Run A stream |
| `run_b_without_mooltrace.stream.jsonl` | Raw stream for Run B (paths and mail redacted) |
| `run_b_without_mooltrace.txt` | Final assistant text containing `SHIPPED:` |
