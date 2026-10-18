"use client"

import { useState, type ReactNode } from "react"
import { runAgent, type AgentResult } from "@/lib/api"
import { HARVARD_DRAFT, HARVARD_QUESTION } from "@/lib/presets"
import { cn } from "@/lib/utils"

const DOT: Record<string, string> = {
  block: "border-rx bg-rx",
  warn: "border-amber-x bg-amber-x",
  pass: "border-clear bg-clear",
}

const WORD: Record<string, string> = { block: "Don't ship", warn: "Review", pass: "Clear" }

function clean(text: string | undefined): string {
  return (text || "")
    .replace(/\[([^\]]+)\]\((?:https?:\/\/|\/)[^)\s]+\)/g, "$1")
    .replace(/[\[【〖]\s*(?:cite|site|source|url)[:：][^\]】〗]*[\]】〗]/gi, "")
    .replace(/[【〖][^】〗]*[】〗]/g, "")
    .replace(/\*\*/g, "")
    .trim()
}

/** Render the model's plain text with light structure; never leak raw markdown or citation markers. */
function Prose({ text }: { text: string | undefined }) {
  const lines = clean(text).split(/\n+/)
  const blocks: ReactNode[] = []
  let bullets: string[] = []
  const flush = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="my-1 list-disc space-y-0.5 pl-5">
          {bullets.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>,
      )
      bullets = []
    }
  }
  for (const raw of lines) {
    const line = raw.trim()
    if (!line) continue
    const heading = line.match(/^#{1,6}\s+(.*)$/)
    if (heading) {
      flush()
      blocks.push(
        <p key={`h-${blocks.length}`} className="mt-2 font-medium first:mt-0">
          {heading[1]}
        </p>,
      )
      continue
    }
    const bullet = line.match(/^[-*•]\s+(.*)$/)
    if (bullet) {
      bullets.push(bullet[1])
      continue
    }
    flush()
    blocks.push(<p key={`p-${blocks.length}`}>{line}</p>)
  }
  flush()
  return <div className="space-y-1">{blocks}</div>
}

export function AgentTab() {
  const [question, setQuestion] = useState("")
  const [result, setResult] = useState<AgentResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  async function go(body: Record<string, unknown>) {
    setBusy(true)
    setError("")
    setResult(null)
    try {
      setResult(await runAgent(body))
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The agent did not finish.")
    } finally {
      setBusy(false)
    }
  }

  const verdict = result?.shipped_verdict?.verdict || ""
  return (
    <div className="flex flex-col gap-5">
      <form
        className="flex items-center gap-2 rounded-2xl border border-hair bg-card-paper p-2 pl-5 shadow-[0_10px_30px_-18px_rgba(22,19,15,.35)]"
        onSubmit={(event) => {
          event.preventDefault()
          if (question.trim()) void go({ question: question.trim(), draft: "", urls: [], engine: "question", depth: 2 })
        }}
      >
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a health question. The agent answers, then checks itself."
          maxLength={300}
          className="h-12 min-w-0 flex-1 bg-transparent text-[16px] text-ink outline-none placeholder:text-ink-2/70"
          aria-label="Health question"
        />
        <button
          type="submit"
          disabled={!question.trim() || busy}
          className="h-12 rounded-xl bg-ink px-5 text-[15px] font-semibold text-cream disabled:opacity-40"
        >
          Ask
        </button>
      </form>
      <div className="-mt-2 flex flex-wrap gap-1.5">
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void go({
              question: HARVARD_QUESTION,
              draft: HARVARD_DRAFT,
              urls: ["https://nutritionsource.hsph.harvard.edu/vitamin-d/"],
              engine: "nutrition-coach",
              depth: 2,
            })
          }
          className="rounded-full border border-hair bg-card-paper px-3.5 py-1.5 text-[13px] text-ink-2 hover:text-ink"
        >
          Run it on the Harvard vitamin D answer
        </button>
        {["Is fish oil good for the heart?", "Does zinc help with colds?"].map((q) => (
          <button
            key={q}
            type="button"
            disabled={busy}
            onClick={() => {
              setQuestion(q)
              void go({ question: q, draft: "", urls: [], engine: "question", depth: 2 })
            }}
            className="rounded-full border border-hair bg-card-paper px-3.5 py-1.5 text-[13px] text-ink-2 hover:text-ink"
          >
            {q}
          </button>
        ))}
      </div>

      {error ? <p className="text-sm text-rx">{error}</p> : null}
      {busy ? (
        <div className="rounded-[20px] border border-hair bg-card-paper p-6 text-sm text-ink-2">
          The agent is working. It fetches the cited pages live, so this can take up to 2 minutes.
        </div>
      ) : null}

      {result ? (
        <section className="flex flex-col gap-4 rounded-[20px] border border-hair bg-card-paper p-6 sm:p-8" data-testid="agent-result">
          <p className="text-xs text-ink-2">
            {result.label}
            {result.elapsed_ms != null ? ` · ${(result.elapsed_ms / 1000).toFixed(0)} s` : ""}
            {result.budget?.spent_usd != null ? ` · $${result.budget.spent_usd.toFixed(3)} spent of $${result.budget.limit_usd}` : ""}
            {result.fallback_reason ? ` · ${result.fallback_reason}` : ""}
          </p>

          <ol className="ml-2 border-l-2 border-hair">
            {(result.steps || []).map((step, index) => {
              const v = step.summary?.verdict || ""
              return (
                <li key={index} className="relative pb-3 pl-5 text-sm" data-testid="agent-step">
                  <span
                    className={cn(
                      "absolute -left-[7px] top-1 size-3 rounded-full border-2 bg-card",
                      DOT[v] || "border-zinc-400",
                    )}
                  />
                  <code className="rounded bg-paper px-1.5 py-0.5 font-mono text-[12px]">{step.tool}</code>{" "}
                  {v ? <span className="font-medium">{WORD[v] || v}</span> : null}
                  {step.summary?.path ? <span className="text-ink-2"> · {step.summary.path}</span> : null}
                  {step.guard ? <span className="text-ink-2"> · added by MoolTrace</span> : null}
                  {step.ms ? <span className="ml-1 text-xs text-ink-2">{Math.round(step.ms)} ms</span> : null}
                </li>
              )
            })}
          </ol>

          {result.cited_urls?.length ? (
            <ul className="flex flex-col gap-0.5 text-xs text-ink-2">
              {result.cited_urls.map((item) => (
                <li key={item.url} className="truncate">
                  {item.ok ? "✓ checked" : `– ${item.status}`} · {item.url}
                </li>
              ))}
            </ul>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-rx/25 bg-rx-soft p-3 text-sm leading-6">
              <p className="mb-1 text-xs text-ink-2">Without MoolTrace</p>
              <Prose text={result.without_mooltrace?.text} />
            </div>
            <div className="rounded-xl border border-clear/30 bg-clear-soft p-3 text-sm leading-6">
              <p className="mb-1 text-xs text-ink-2">
                Shipped with MoolTrace{verdict ? ` · ${WORD[verdict] || verdict}` : ""}
              </p>
              <Prose text={result.shipped} />
            </div>
          </div>
          <p className="text-[11.5px] text-ink-2">
            {result.disclosure ? `${result.disclosure} ` : ""}The model picks tools; the graph decides; only tool output ships.
          </p>
        </section>
      ) : null}
    </div>
  )
}
