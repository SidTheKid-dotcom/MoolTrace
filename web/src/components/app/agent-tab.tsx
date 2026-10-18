"use client"

import { useEffect, useRef, useState, type ReactNode } from "react"
import { runAgent, type AgentResult, type AgentStep } from "@/lib/api"
import { flagLabel, pageName, relianceWord, workName } from "@/lib/naming"
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

const TOOL_WORDS: Record<string, string> = {
  check_answer: "Checked the draft",
  explain_path: "Explained the path",
  rewrite_answer: "Rewrote and checked again",
  what_rests_on: "Walked back from the notice",
  recheck_affected: "Rechecked stored answers",
}

const PLAN = [
  "Fetch the cited page",
  "Hop 1 · page → the papers it cites",
  "Hop 2 · those papers → the studies they use",
  "Look for retractions and notices",
  "Fix the sentence and check again",
]

type Chain = NonNullable<NonNullable<AgentStep["summary"]>["chain"]>

/** "Harvard vitamin D → mentions → Cochrane 2014 (Avenell) → uses its data → Ishida 2004 (Retracted · May 2025)" */
function chainWords(chain: Chain): string {
  return chain
    .map((step, index) => {
      const name = index === 0 && !step.doi ? pageName(step.url, step.title) : workName(step, step.reliance).name
      const flag = step.notice_type ? ` (${flagLabel(step.notice_type, step.notice_date, step.doi)})` : ""
      return `${index ? `${relianceWord(step.reliance)} → ` : ""}${name}${flag}`
    })
    .join(" → ")
}

function argWords(args: Record<string, unknown> | undefined): string {
  if (!args) return ""
  const urls = Array.isArray(args.urls) ? (args.urls as string[]).map((url) => pageName(url)) : []
  const parts = [urls.length ? urls.join(", ") : args.doi ? `DOI ${String(args.doi)}` : "", args.depth != null ? `${String(args.depth)} hops` : ""]
  return parts.filter(Boolean).join(" · ")
}

function Progress({ seconds }: { seconds: number }) {
  const at = Math.min(PLAN.length - 1, Math.floor(seconds / 2))
  return (
    <div className="rounded-[20px] border border-hair bg-card-paper p-6" aria-live="polite" data-testid="agent-progress">
      <p className="text-[14px] text-ink-2">The agent is working · {seconds} s. Live pages can take up to 2 minutes.</p>
      <ol className="mt-4 flex flex-col gap-2 text-[14.5px]">
        {PLAN.map((step, index) => (
          <li key={step} className={cn("flex items-center gap-2.5", index > at ? "text-ink-2/60" : "text-ink")}>
            <span className={cn("grid size-4 place-items-center rounded-full border-2", index < at ? "border-ink bg-ink" : index === at ? "border-ink" : "border-hair")}>
              {index === at ? <span className="size-1.5 animate-pulse rounded-full bg-ink" /> : null}
            </span>
            {step}
          </li>
        ))}
      </ol>
      <p className="mt-3 text-[12px] text-ink-2">These are the stages it runs. The real tool calls, with timings, appear when it finishes.</p>
    </div>
  )
}

export function AgentTab({ autorun = false }: { autorun?: boolean }) {
  const [question, setQuestion] = useState("")
  const [result, setResult] = useState<AgentResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState("")
  const ran = useRef(false)

  async function go(body: Record<string, unknown>) {
    setBusy(true)
    setSeconds(0)
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

  const runDraft = () =>
    go({
      question: HARVARD_QUESTION,
      draft: HARVARD_DRAFT,
      urls: ["https://nutritionsource.hsph.harvard.edu/vitamin-d/"],
      engine: "nutrition-coach",
      depth: 2,
    })

  useEffect(() => {
    if (!busy) return
    const timer = setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => clearInterval(timer)
  }, [busy])

  useEffect(() => {
    if (!autorun || ran.current) return
    ran.current = true
    void Promise.resolve().then(runDraft)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autorun])

  const verdict = result?.shipped_verdict?.verdict || ""
  const chainStep = (result?.steps || []).find((step) => step.summary?.chain?.length)
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
          className="h-12 rounded-xl bg-ink px-5 text-[15px] font-semibold text-cream active:scale-95 disabled:opacity-40"
        >
          Ask
        </button>
      </form>
      <div className="-mt-2 flex flex-wrap gap-1.5">
        <button
          type="button"
          disabled={busy}
          onClick={() => void runDraft()}
          className="rounded-full border border-ink bg-card-paper px-3.5 py-1.5 text-[13px] text-ink active:scale-95"
        >
          Run it on the Harvard vitamin D draft
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
            className="rounded-full border border-hair bg-card-paper px-3.5 py-1.5 text-[13px] text-ink-2 hover:text-ink active:scale-95"
          >
            {q}
          </button>
        ))}
      </div>

      {error ? <p className="text-sm text-rx">{error}</p> : null}
      {busy && seconds >= 1 ? <Progress seconds={seconds} /> : null}

      {!result && !busy && !error ? (
        <div className="rounded-[20px] border border-dashed border-hair p-6 text-[14.5px] text-ink-2">
          Run the agent on the Harvard vitamin D draft to watch it check, explain, fix and check again. Or ask your own question.
        </div>
      ) : null}

      {result ? (
        <section className="flex min-w-0 flex-col gap-5 rounded-[20px] border border-hair bg-card-paper p-5 sm:p-8" data-testid="agent-result">
          <p className="text-xs text-ink-2">
            {result.fallback_reason ? `Rule-based fallback (${result.fallback_reason})` : "Agent run"}
            {result.elapsed_ms != null ? ` · ${(result.elapsed_ms / 1000).toFixed(1)} s` : ""}
          </p>

          {chainStep?.summary?.chain ? (
            <p className="text-[15px] leading-7" data-testid="agent-chain">
              <span className="font-label mr-2 text-[10.5px] text-ink-2">Path</span>
              {chainWords(chainStep.summary.chain)}
            </p>
          ) : null}

          <div className="-mx-1 max-w-full overflow-x-auto px-1">
            <table className="w-full min-w-[560px] text-left text-[13.5px]" data-testid="agent-trace">
              <thead className="font-label text-[10.5px] text-ink-2">
                <tr className="border-b border-hair">
                  <th className="py-2 pr-3 font-normal">Tool</th>
                  <th className="py-2 pr-3 font-normal">Args</th>
                  <th className="py-2 pr-3 font-normal">Result</th>
                  <th className="py-2 pr-3 text-right font-normal">ms</th>
                  <th className="py-2 text-right font-normal">Rows</th>
                </tr>
              </thead>
              <tbody>
                {(result.steps || []).map((step, index) => {
                  const v = step.summary?.verdict || ""
                  return (
                    <tr key={index} className="border-b border-hair/70 align-top" data-testid="agent-step">
                      <td className="py-2 pr-3">
                        <span className={cn("mr-2 inline-block size-2.5 rounded-full border-2", DOT[v] || "border-zinc-400")} />
                        <code className="font-mono text-[12.5px]">{step.tool}</code>
                        <div className="text-[12px] text-ink-2">
                          {TOOL_WORDS[step.tool || ""] || ""}
                          {step.guard ? " · added by MoolTrace" : ""}
                        </div>
                      </td>
                      <td className="py-2 pr-3 text-ink-2">{argWords(step.args)}</td>
                      <td className="py-2 pr-3 font-medium">{v ? WORD[v] || v : step.ok === false ? "error" : "done"}</td>
                      <td className="py-2 pr-3 text-right font-mono text-[12.5px] text-ink-2">{step.ms != null ? Math.round(step.ms) : "—"}</td>
                      <td className="py-2 text-right font-mono text-[12.5px] text-ink-2">{step.summary?.rows ?? "—"}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {result.cited_urls?.length ? (
            <ul className="flex flex-col gap-0.5 text-xs text-ink-2">
              {result.cited_urls.map((item) => (
                <li key={item.url} className="truncate">
                  {item.ok ? "✓ fetched" : `– ${item.status}`} · {item.url}
                </li>
              ))}
            </ul>
          ) : null}

          <div className="grid min-w-0 gap-3 sm:grid-cols-2">
            <div className="min-w-0 rounded-xl border border-rx/25 bg-rx-soft p-4 text-[14.5px] leading-6 [overflow-wrap:anywhere]">
              <p className="mb-1 text-xs text-ink-2">Without MoolTrace · ships as written</p>
              <Prose text={result.without_mooltrace?.text} />
            </div>
            <div className="min-w-0 rounded-xl border border-clear/30 bg-clear-soft p-4 text-[14.5px] leading-6 [overflow-wrap:anywhere]">
              <p className="mb-1 text-xs text-ink-2">
                Shipped with MoolTrace{verdict ? ` · checked again: ${WORD[verdict] || verdict}` : ""}
              </p>
              <Prose text={result.shipped} />
            </div>
          </div>
          <p className="text-[11.5px] text-ink-2">The model picks the tools. The graph decides. Only tool output ships.</p>
        </section>
      ) : null}
    </div>
  )
}
