# Ship checklist — Sun 18 Oct 2026, 11:59 PM IST

Do these in order after the video is uploaded. Do **not** rewrite git history unless you explicitly choose option B below.

## 1. Tests (this machine)

```bash
unshare --net --map-root-user .venv/bin/python -m pytest -q
.venv/bin/python examples/agent_loop.py
.venv/bin/python -m mooltrace.gate
```

Do not push if pytest is red.

## 2. Flip the GitHub repo public

Repo is `SidTheKid-dotcom/MoolTrace`, currently private.

```bash
gh repo edit SidTheKid-dotcom/MoolTrace --visibility public --accept-visibility-change-consequences
gh repo view SidTheKid-dotcom/MoolTrace --json isPrivate,url
```

Confirm Origin mirror (if you keep one) has the same HEAD:

```bash
git fetch origin
git rev-parse HEAD origin/main
```

## 3. README render

Open the public GitHub README signed-out. Check: screenshot PNG, mermaid diagram, CI snippet, MCP JSON, Honest results table.

## 4. Hosted demo

This session had **no** Railway / Fly / Hugging Face / Render token. Do not paste a fake URL.

When a login exists, pick one:

```bash
# Fly (API only in fly.toml — add a web process or a combined image before going live)
fly auth login
fly launch --copy-config --yes
# or
railway login && railway init && railway up
```

Public demo **must** set `MOOLTRACE_PUBLIC_DEMO=1` (offline presets, no arbitrary URL fetch). Optional live checks: `MOOLTRACE_PUBLIC_LIVE=1` plus the existing SSRF guard. Signed-out check:

```bash
curl -sI https://<host>/health
```

Paste the URL into README **outside** the `## Demo` compose section, and into `SUBMISSION.md`.

## 5. Video link

Paste the YouTube URL into README and `SUBMISSION.md`. Duration must be under 180 s:

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 <video-file>
```

Open the YouTube link signed-out.

## 6. Older commits carry a personal Gmail

Newer commits use `Siddhant Vishnu <SidTheKid-dotcom@users.noreply.github.com>`. Older commits on `main` still show a personal Gmail. **Do not rewrite history in this session.**

Choose on 18 Oct, before flipping public:

| Option | What happens |
| --- | --- |
| A. Leave as is | Public GitHub shows the Gmail on old commits. Simplest. No force-push. |
| B. `git filter-repo` + mailmap | Rewrites author emails on already-pushed commits. Requires a force-push. Do this **before** the repo is public, and only if you accept rewriting Origin. |

This file does not run option B.

## 7. Secrets scan

```bash
git ls-files AGENTS.md CLAUDE.md .agents .claude docs design
# must print nothing
git grep -I -E 'AZURE_INFERENCE_API_KEY=|sk-|BEGIN PRIVATE' -- ':!.github' || true
```

## 8. Stop

No pushes after Sun 18 Oct 2026, 11:59 PM IST. Keep the live link, repo, and video up through judging.
