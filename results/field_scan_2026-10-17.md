# Field scan: Harvard Nutrition Source, vitamins and minerals (17 Oct 2026)

Protocol (written and committed before any page was checked): [field_scan_2026-10-17_protocol.md](field_scan_2026-10-17_protocol.md). Frozen list: [field_scan_2026-10-17_pages.json](field_scan_2026-10-17_pages.json). Raw payload summary: [field_scan_2026-10-17.json](field_scan_2026-10-17.json). Every page of the frame was checked; none failed.

## Counts (35 pages)

| | pass | warn | warn (incomplete) | block |
|---|---:|---:|---:|---:|
| Depth 1 | 26 | 5 | 3 | 1 |
| Depth 2 | 18 | 9 | 5 | 3 |
| Direct-DOI check (no graph) | 35 "0 notices → would ship" | | | 0 |

## Every BLOCK, checked by hand

| Page | Path | Notice | Hand check |
|---|---|---|---|
| [Zinc](https://nutritionsource.hsph.harvard.edu/zinc/) | Page reference list cites Singh M, Das RR. *Zinc for the common cold.* Cochrane 2011;(2):CD001364 (`10.1002/14651858.cd001364.pub3`) — one hop, depth 1 and 2 | Withdrawal notice `10.1002/14651858.cd001364.pub5`, 30 Apr 2015; Retraction Watch record 32240 lists it as a retraction | **Verified.** Cochrane withdrew the review in April 2015 over data and calculation concerns; plagiarism allegations were also raised about the 2013 version (Cochrane notice, PMID 25924708; Retraction Watch, 7 Oct 2015). |
| [Vitamin D](https://nutritionsource.hsph.harvard.edu/vitamins/vitamin-d/) | Page → Avenell 2014 Cochrane review (`mention` 0.55) → Ishida 2004, *Am J Med* (`uses_data_or_method` 0.85; PMC sentence: "Ishida 2004, an included trial, has been retracted") | Retraction notice `10.1016/j.amjmed.2025.03.001`, May 2025 (PubMed PMID 40222753) | **Verified.** Notice: "the evidence presented below strongly argues for scientific misconduct." |
| [Salt and sodium](https://nutritionsource.hsph.harvard.edu/salt-and-sodium/) | Page → He 2013 Cochrane/BMJ (`mention`) → Taylor 2011 Cochrane *Reduced dietary salt…* (`relies` 1.0) | Retraction Watch record 32856, notice `10.1002/14651858.cd009217.pub2`, Nov 2013 | **Not verified as reliance.** The `relies` label rests on a reference-list title, not a sentence showing the review relied on that work. Not counted in the headline. |

**Headline (verified only): 2 of 35 Harvard Nutrition Source vitamin and mineral pages rest on withdrawn or retracted research — Zinc directly (one hop), Vitamin D two hops down. A direct DOI check passes all 35.**

## Notice-backed WARNs (not blocks)

Expression of Concern or mention-only paths: Potassium and Salt (EoC `10.1042/cs-20070193_eoc`), Niacin (EoC `10.1093/cvr/cvaa248`), Selenium (EoC `10.1017/s0007114521002014`), Magnesium (retraction paths with an `unverified` hop). These are WARN by policy: an Expression of Concern is not a retraction, and a mention is not reliance.

## What this does not say

It does not say Harvard's advice is wrong, that the pages relied on these works for their conclusions, or that zinc or vitamin D do or do not work. It says a citation path exists from the page to a withdrawn or retracted work, and that a check limited to DOIs in the answer would not see it.
