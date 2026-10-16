# MoolTrace — Graph Hacks submission draft

Fill the video URL, public-repo URL, and hosted-demo URL on 18 Oct 2026. Do not invent them before they exist.

**Name:** MoolTrace

**Tagline:** Check the roots before you ship.

**Track:** 01 — Agents That Act on Connected Data

**Deadline:** Sun 18 Oct 2026, 11:59 PM IST

## 150-word description

Health-AI products (symptom checkers, nutrition coaches, patient chatbots) cite consumer pages. Those pages cite reviews, which cite trials. Some of those trials now carry a publisher Expression of Concern or a retraction. MoolTrace turns one pasted answer plus its URLs into a FalkorDB graph (Answer → Source → Work → Notice), then **algo.SPpaths** with cost `-ln(weight)` decides pass / warn / block from path strength. Judges see the hops, the sentence on each hop, and the Cypher. An Expression of Concern is not a retraction and is never scored as one. CI (`mooltrace batch`) and MCP (`check_answer`, `rewrite_answer`, `what_rests_on`) are the same check. After a new notice, reverse lookup lists which stored answers rest on it. Rewrite removes only the affected sentences and rechecks. This is a pre-ship gate, not a medical-accuracy claim.

## How judges run it in two minutes

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
export MOOLTRACE_MAILTO=you@example.com
.venv/bin/python -m mooltrace check --url https://www.healthline.com/nutrition/cinnamon-and-diabetes --summary
```

Expect **WARN (exit 2)** and `Decided by: algo.SPpaths, path strength 0.55` (Healthline page `mention` × Silva→Khan `relies`, recorded 16 Oct 2026 / 15 Oct 2026). Then:

```bash
.venv/bin/python -m mooltrace batch examples/lancet.jsonl --fail-on block; echo $?
```

Expect exit **1** (retraction). Optional UI: `docker compose up --build` → http://127.0.0.1:4318 — presets Healthline olive oil (block, path strength 0.30) / cinnamon (warn, 0.55) / clean.

## Tech used

- FalkorDBLite 0.10.0 (embedded FalkorDB)
- Verdict: `algo.SPpaths` on `RESTS_ON.cost = -ln(weight)`; path strength = product of weights
- MCP stdio server (`mooltrace.mcp_server`) wrapping the same Python tools
- Notices: Crossref. Citation lists: OpenAlex. Sentences: Semantic Scholar contexts, PMC, page, or draft
- Rewrite is a deterministic template: only sentences that cite flagged work change; every other sentence stays byte-identical. Code still strips flagged citations.

## Links (paste on 18 Oct)

| Field | Value |
| --- | --- |
| Public GitHub repo | _paste after flipping the repo public_ |
| Demo video (YouTube, ≤3 min) | _paste after upload_ |
| Hosted demo | https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/ |

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
