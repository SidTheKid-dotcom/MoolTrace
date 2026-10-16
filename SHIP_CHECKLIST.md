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

## 4. Hosted demo (AWS Lightsail, ap-south-1)

`aws sts get-caller-identity` worked on 16 Oct 2026 (account `533267274451`). The public HTTPS URL is:

https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/

Read-only demo: `MOOLTRACE_PUBLIC_DEMO=1`, no `MOOLTRACE_PUBLIC_LIVE`, no Azure env vars. Power **micro** (1 GB, at most micro), scale 1, tag `project=mooltrace`. No other paid resources.

Exact commands used:

```bash
aws sts get-caller-identity
# lightsailctl must be on PATH (AWS CLI plugin for push-container-image)
# curl -fsSL https://s3.us-west-2.amazonaws.com/lightsailctl/latest/linux-amd64/lightsailctl -o ~/.local/bin/lightsailctl && chmod +x ~/.local/bin/lightsailctl

aws lightsail create-container-service \
  --region ap-south-1 \
  --service-name mooltrace \
  --power micro \
  --scale 1 \
  --tags key=project,value=mooltrace

docker build --target api -t mooltrace-api:latest .
docker build --target web -t mooltrace-web:latest \
  --build-arg MOOLTRACE_API_ORIGIN=http://localhost:4317 .

aws lightsail push-container-image --region ap-south-1 \
  --service-name mooltrace --label api --image mooltrace-api:latest
aws lightsail push-container-image --region ap-south-1 \
  --service-name mooltrace --label web --image mooltrace-web:latest

aws lightsail create-container-service-deployment \
  --region ap-south-1 \
  --cli-input-json file://deploy/lightsail-deployment.json
```

Signed-out check (web is the public endpoint; API is localhost inside the service):

```bash
curl -sI https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/
curl -sS -X POST https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/nw/check-answer \
  -H 'content-type: application/json' \
  -d '{"text":"","urls":["https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil"],"engine":"nutrition-coach","depth":3}'
```

### Teardown (stops billing)

```bash
aws lightsail delete-container-service --region ap-south-1 --service-name mooltrace
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
