# MoolTrace demo video script (≤3:00)

Record on 17 Oct 2026. Do not say a number that was not measured on 16 Oct 2026 in this checkout. Voice: one person, screen recording, signed-out browser for any public URL.

**Hook (0:00–0:25).** On screen: a nutrition-coach draft and the Healthline URL only.

> Your health bot cites Healthline. Looks safe. No DOI in the draft. Looks like a normal web page.

Paste into the UI (or CLI):

```bash
.venv/bin/python -m mooltrace check --url https://www.healthline.com/nutrition/cinnamon-and-diabetes --summary
```

**Path (0:25–1:20).** Click preset **Healthline cinnamon (warn)** if using the UI (`http://127.0.0.1:4318/?preset=healthline`).

Say:

> The page cites Silva 2022, a review. The review included Khan 2003, a trial. Diabetes Care posted an Expression of Concern on that trial in 2025. That is not a retraction. MoolTrace warns.

Point at the red EoC badge. Point at the path: Healthline → Silva 2022 → Khan 2003.

**Algorithm (1:20–1:45).** Open the Cypher panel.

> The verdict is not a Python if-statement. FalkorDB `algo.SPpaths` walks this answer's subgraph with cost minus ln of the hop weight. Path strength is the product of those weights. Strength 0.72, counted, Expression of Concern, so WARN. If that algorithm errors, we return exit 3. We do not invent a verdict.

On-screen text must include: `Decided by: algo.SPpaths, path strength 0.72`.

**Retraction + CI (1:45–2:15).** Click preset **Lancet 2020 HCQ (block)**. Then terminal:

```bash
.venv/bin/python -m mooltrace batch examples/lancet.jsonl --fail-on block
echo $?
```

Say:

> Same gate on a retracted 2020 Lancet paper. BLOCK. CI fails. An Expression of Concern is not this. A retraction is.

**Rewrite + reverse (2:15–2:45).** On the Lancet (or Healthline) result, click **Rewrite and recheck**. Then:

```bash
.venv/bin/python -m mooltrace what-rests-on 10.2337/dc25-ec09
```

Say only a counted-answer number you measured that day. Placeholder until the recording run: _do not say a stale N from an old README_. After the recording run, replace this line with the printed `affects N stored answers`.

> Rewrite removes the affected claim. Recheck passes if nothing flagged remains. Reverse lookup: this notice affects N stored answers.

**Close (2:45–2:55).**

> MoolTrace. Check the roots before you ship.

Stop before 3:00. Do not claim medical correctness. Do not call an Expression of Concern a retraction. Do not say “SPpaths flips the verdict” as a slogan; show the strength and the Cypher instead.

## Click order

1. UI `?preset=healthline` (or the CLI `--summary` command above)
2. Cypher / algorithm panel
3. UI `?preset=lancet`
4. Terminal `batch examples/lancet.jsonl --fail-on block`
5. Rewrite and recheck
6. `what-rests-on 10.2337/dc25-ec09`

## Numbers allowed on 16 Oct 2026 (this checkout)

- Cold Healthline `--summary`: 47.09 s / 49.18 s / 49.10 s, all WARN, EoC `10.2337/dc25-ec09`
- Warm Healthline: 23.16 s
- Flip test: weight 0.85 → warn, 0.2 → pass; algorithm disabled → exit 3
- Do not quote labelled precision until the 52-case cold run is in the README table
