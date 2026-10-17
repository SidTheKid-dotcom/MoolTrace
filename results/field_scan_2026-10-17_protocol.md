# Field scan protocol (written before any page was checked)

Date: 17 Oct 2026 (IST evening). Author: Siddhant Vishnu.

**Question.** How many pages in one trusted consumer nutrition reference rest, within two citation hops, on research that carries a retraction or an Expression of Concern?

**Sampling frame (no hand-picking).** Every link inside the article body of Harvard T.H. Chan School of Public Health, *The Nutrition Source*, "Vitamins and Minerals" index page (https://nutritionsource.hsph.harvard.edu/vitamins/), fetched 17 Oct 2026. That body links **35** pages (30 single vitamins or minerals, 4 food-group pages, 1 multivitamin page). All 35 are checked. None are dropped; any page that fails is reported as failed with the reason. The list is frozen in `results/field_scan_2026-10-17_pages.json`.

**Method.** Each page URL is checked as a URL-only answer with `mooltrace check-answer --url <page> --depth 1` and then `--depth 2`, each on a fresh throwaway graph (shared HTTP cache only), under the current reliance policy: a retraction is BLOCK only if the hop into the retracted work is included / relies / uses_data_or_method and every hop passes the per-hop gate; an Expression of Concern is WARN; mention-only chains are WARN. The direct-DOI baseline is the payload's own "Direct DOI check" line.

**What is reported.** Counts of block / warn / pass / incomplete / failed at each depth, and for every BLOCK and every notice-backed WARN: page → cited work → flagged work (DOI, first author, year) → notice (DOI, type, date as resolved after the T42 date fix), with each hop's reliance label, weight and evidence sentence.

**What it does not claim.** "Rests on" means a citation path exists under the policy above. It does not mean the page is wrong, that the page's advice changes, or that Harvard relied on the flagged work. Every BLOCK is checked by hand against the publisher notice before it is quoted anywhere.
