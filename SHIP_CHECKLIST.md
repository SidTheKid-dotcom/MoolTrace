# Ship checklist — human only

Deadline: Sun 18 Oct 2026, 11:59 PM IST. Track 01: **Agents That Act on Connected Data**.

The pipeline already ran the offline tests, wrote the Cypher and algorithms into `SUBMISSION.md`, and deployed the signed-out demo. You do four things. Do not rewrite git history. Do not invent a number, URL, or rival claim.

## 1. Record the video

Follow [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md). Duration must be **≤90 s**.

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 <video-file>
```

The printed number must be ≤ 90. Upload to YouTube. Open the link signed-out.

Record against the live demo (no sign-up):

https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/?preset=olive-oil

Say only numbers the script cites. Both olive-oil hops are `mention`. Never say the review relies on the trial. Do not call `recheck_affected` on camera. Do not say olive oil works or does not. An Expression of Concern is not a retraction.

## 2. Make the GitHub repo public

Repo is `SidTheKid-dotcom/MoolTrace`, currently private.

```bash
gh repo edit SidTheKid-dotcom/MoolTrace --visibility public --accept-visibility-change-consequences
gh repo view SidTheKid-dotcom/MoolTrace --json isPrivate,url
```

Expect `isPrivate: false` and `https://github.com/SidTheKid-dotcom/MoolTrace`. Do not rewrite history. Older commits still show a personal Gmail; leave them.

## 3. Paste links

Paste into [SUBMISSION.md](SUBMISSION.md) (replace the placeholders) and into the hackathon form. Do not invent a URL.

| Field | Value |
| --- | --- |
| Public GitHub repo | https://github.com/SidTheKid-dotcom/MoolTrace (after step 2) |
| Demo video (YouTube, ≤90 s) | the URL from step 1 |
| Hosted demo | https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/ |
| Track | Agents That Act on Connected Data |

If the Lightsail demo is down, do not paste a substitute. Note it and stop.

## 4. Final check

Signed-out, in this order:

1. Public GitHub README: tagline, live demo URL, olive-oil BLOCK screenshot, track name **Agents That Act on Connected Data**.
2. Live demo: click **Healthline olive oil (block)**. Toggle depth 1 (PASS, 0 notice paths) then depth 3 (BLOCK, path strength 0.30, both hops `mention`, retraction `10.1056/nejmc1806491`). Click **Not in the graph**: WARN, expanded 0 of 0 cited works.
3. YouTube: duration ≤90 s, include the depth 1 → 3 toggle and the Not in the graph beat, close line "MoolTrace. Check the roots before you ship."
4. Hackathon form track is **Agents That Act on Connected Data**. `SUBMISSION.md` has the three links filled (repo, video, demo). Video placeholder `_paste after upload_` is gone.

Stop. No pushes after Sun 18 Oct 2026, 11:59 PM IST. Keep the live link, public repo, and video up through judging.

Live container images (17 Oct 2026 rebuild from current main, allow-listed live URL): `:mooltrace.api.13` (digest `sha256:b4c7b0d3bc165f56a7ce91b703083c190a7944241602c81a598af2b701ba57d8`) and `:mooltrace.web.14` (digest `sha256:1e2d7805c36954e73b2962f556356533916304831817b3ef2cc31beb84711f31`, built with `MOOLTRACE_API_ORIGIN=http://localhost:4317`). Power micro, scale 1, `MOOLTRACE_PUBLIC_DEMO=1`, `MOOLTRACE_PUBLIC_LIVE=1`, no Azure env vars. Pinned in `deploy/lightsail-deployment.json`. Toggle depth 1 then 3 on the olive-oil preset: PASS (0 notice paths) then BLOCK. Click **Not in the graph** for the NHS how-to: WARN, expanded 0 of 0 cited works. Paste a non-preset healthline.com URL for a live check (about 60 s; one at a time).

## After judging (stops Lightsail billing)

```bash
aws lightsail delete-container-service --region ap-south-1 --service-name mooltrace
```
