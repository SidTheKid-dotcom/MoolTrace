"use client"

import { useState } from "react"
import { runAgent, type AgentResult } from "@/lib/api"
import { HARVARD_DRAFT, HARVARD_QUESTION } from "@/lib/presets"
import { cn } from "@/lib/utils"

const DOT: Record<string, string> = {
  block: "border-red-500 bg-red-500",
  warn: "border-amber-500 bg-amber-500",
  pass: "border-emerald-500 bg-emerald-500",
}

const WORD: Record<string, string> = { block: "Don't ship", warn: "Review", pass: "Clear" }

function clean(text: string | undefined): string {
  return (text || "").replace(/\*\*/g, "")
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
        className="flex items-center gap-2 rounded-2xl border bg-card p-2 pl-4 shadow-sm"
        onSubmit={(event) => {
          event.preventDefault()
          if (question.trim()) void go({ question: question.trim(), draft: "", urls: [], engine: "question", depth: 2 })
        }}
      >
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a health question — the agent answers, then checks itself"
          maxLength={300}
          className="h-10 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground"
          aria-label="Health question"
        />
        <button
          type="submit"
          disabled={!question.trim() || busy}
          className="h-10 rounded-xl bg-foreground px-4 text-sm font-medium text-background disabled:opacity-40"
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
          className="rounded-full border px-3 py-1 text-[12.5px] text-muted-foreground hover:text-foreground"
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
            className="rounded-full border px-3 py-1 text-[12.5px] text-muted-foreground hover:text-foreground"
          >
            {q}
          </button>
        ))}
      </div>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {busy ? (
        <div className="rounded-2xl border p-6 text-sm text-muted-foreground">
          The agent is working — it fetches the cited pages live, up to 2 minutes.
        </div>
      ) : null}

      {result ? (
        <section className="flex flex-col gap-4 rounded-2xl border bg-card p-5" data-testid="agent-result">
          <p className="text-xs text-muted-foreground">
            {result.label}
            {result.elapsed_ms != null ? ` · ${(result.elapsed_ms / 1000).toFixed(0)} s` : ""}
            {result.budget?.spent_usd != null ? ` · $${result.budget.spent_usd.toFixed(3)} spent of $${result.budget.limit_usd}` : ""}
            {result.fallback_reason ? ` · ${result.fallback_reason}` : ""}
          </p>

          <ol className="ml-2 border-l-2 border-border">
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
                  <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[12px]">{step.tool}</code>{" "}
                  {v ? <span className="font-medium">{WORD[v] || v}</span> : null}
                  {step.summary?.path ? <span className="text-muted-foreground"> · {step.summary.path}</span> : null}
                  {step.guard ? <span className="text-muted-foreground"> · added by MoolTrace</span> : null}
                  {step.ms ? <span className="ml-1 text-xs text-muted-foreground">{Math.round(step.ms)} ms</span> : null}
                </li>
              )
            })}
          </ol>

          {result.cited_urls?.length ? (
            <ul className="flex flex-col gap-0.5 text-xs text-muted-foreground">
              {result.cited_urls.map((item) => (
                <li key={item.url} className="truncate">
                  {item.ok ? "✓ checked" : `– ${item.status}`} · {item.url}
                </li>
              ))}
            </ul>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-red-200 bg-red-50/60 p-3 text-sm leading-6">
              <p className="mb-1 text-xs text-muted-foreground">Without MoolTrace</p>
              <p className="whitespace-pre-line">{clean(result.without_mooltrace?.text)}</p>
            </div>
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3 text-sm leading-6">
              <p className="mb-1 text-xs text-muted-foreground">
                Shipped with MoolTrace{verdict ? ` · ${WORD[verdict] || verdict}` : ""}
              </p>
              <p className="whitespace-pre-line">{clean(result.shipped)}</p>
            </div>
          </div>
          <p className="text-[11.5px] text-muted-foreground">
            {result.disclosure ? `${result.disclosure} ` : ""}The model picks tools; the graph decides; only tool output ships.
          </p>
        </section>
      ) : null}
    </div>
  )
}
