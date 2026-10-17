"use client"

import { useEffect, useRef, useState } from "react"
import { Chain } from "@/components/app/chain"
import {
  checkAnswer,
  monthYear,
  noticeWord,
  parseInput,
  rewriteAnswer,
  VERDICT_COPY,
  verdictOf,
  type Check,
  type Input,
  type Reason,
  type Rewrite,
} from "@/lib/api"
import { decidingReason } from "@/lib/path-diagram"
import { EXAMPLES } from "@/lib/presets"
import { cn } from "@/lib/utils"

const TONE = {
  bad: { badge: "bg-red-50 text-red-700", pill: "border-red-200 bg-red-50" },
  warn: { badge: "bg-amber-50 text-amber-700", pill: "border-amber-200 bg-amber-50" },
  ok: { badge: "bg-emerald-50 text-emerald-700", pill: "border-emerald-200 bg-emerald-50" },
}

function headline(check: Check, deciding: Reason | null): string {
  const verdict = verdictOf(check)
  if (verdict === "empty") return "No study is connected to this page. That is not proof it is safe."
  if (verdict === "pass") return "No retraction or concern found on the cited research."
  const when = monthYear(deciding?.notice_date)
  const word = noticeWord(deciding?.notice_type).toLowerCase()
  const hops = Math.max(1, (deciding?.steps?.length || 1) - 1)
  const depth = hops === 1 ? "one step down" : `${hops} steps down`
  if (word === "expression of concern") return `A study ${depth} carries an Expression of Concern${when ? ` (${when})` : ""}.`
  return `This rests on research ${word}${when ? ` in ${when}` : ""}, ${depth}.`
}

export function CheckTab({ initial }: { initial?: { input: Input; label?: string } }) {
  const [raw, setRaw] = useState("")
  const [input, setInput] = useState<Input | null>(null)
  const [check, setCheck] = useState<Check | null>(null)
  const [fix, setFix] = useState<Rewrite | null>(null)
  const [busy, setBusy] = useState<"" | "check" | "fix">("")
  const [error, setError] = useState("")
  const started = useRef(false)

  async function run(next: Input) {
    setInput(next)
    setFix(null)
    setError("")
    setBusy("check")
    try {
      setCheck(await checkAnswer(next))
    } catch (exc) {
      setCheck(null)
      setError(exc instanceof Error ? exc.message : "The check did not finish.")
    } finally {
      setBusy("")
    }
  }

  async function runFix() {
    if (!input) return
    const draft = input.text || `Source: ${input.urls.join(" ")}`
    setBusy("fix")
    setError("")
    try {
      setFix(await rewriteAnswer({ ...input, text: draft }))
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The fix did not finish.")
    } finally {
      setBusy("")
    }
  }

  useEffect(() => {
    if (started.current || !initial) return
    started.current = true
    setRaw(initial.input.urls.join(" ") || initial.input.text)
    void run(initial.input)
  }, [initial])

  const verdict = check ? verdictOf(check) : null
  const copy = verdict ? VERDICT_COPY[verdict] : null
  const tone = copy ? TONE[copy.tone as keyof typeof TONE] : null
  const deciding = check ? decidingReason(check.reasons || []) : null
  const noDoi = check?.why_graph?.without_graph?.notice_count === 0

  return (
    <div className="flex flex-col gap-5">
      <form
        className="flex items-center gap-2 rounded-2xl border bg-card p-2 pl-4 shadow-sm focus-within:ring-2 focus-within:ring-ring/30"
        onSubmit={(event) => {
          event.preventDefault()
          if (raw.trim()) void run(parseInput(raw, input?.depth || 2))
        }}
      >
        <input
          value={raw}
          onChange={(event) => setRaw(event.target.value)}
          placeholder="Paste an AI answer or the link it cites"
          className="h-10 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground"
          aria-label="Answer or link to check"
        />
        <button
          type="submit"
          disabled={!raw.trim() || busy !== ""}
          className="h-10 rounded-xl bg-foreground px-4 text-sm font-medium text-background disabled:opacity-40"
        >
          {busy === "check" ? "Checking…" : "Check"}
        </button>
      </form>

      <div className="-mt-2 flex flex-wrap gap-1.5" data-testid="examples">
        {EXAMPLES.map((example) => (
          <button
            key={example.id}
            type="button"
            disabled={busy !== ""}
            onClick={() => {
              setRaw(example.urls.join(" ") || example.text)
              void run({ text: example.text, urls: example.urls, engine: example.engine, depth: example.depth })
            }}
            className="rounded-full border px-3 py-1 text-[12.5px] text-muted-foreground transition hover:border-foreground/30 hover:text-foreground"
          >
            {example.label}
          </button>
        ))}
      </div>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}

      {busy === "check" && !check ? (
        <div className="rounded-2xl border p-6 text-sm text-muted-foreground">
          Following citations: page → review → trial…
        </div>
      ) : null}

      {check && copy && tone ? (
        <section className={cn("flex flex-col gap-4 rounded-2xl border bg-card p-5", busy === "check" && "opacity-60")}>
          <div className="flex items-start gap-3">
            <div className={cn("grid size-11 shrink-0 place-items-center rounded-xl text-xl font-semibold", tone.badge)}>
              {copy.icon}
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-2xl font-semibold tracking-tight" data-testid="verdict">
                {copy.title}
              </h2>
              <p className="text-sm text-muted-foreground">{headline(check, deciding)}</p>
            </div>
            <span
              title="CI exit code: pass 0 · warn 2 · block 1"
              className="rounded-md border px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
            >
              exit {check.exit_code ?? (check.decision === "block" ? 1 : check.decision === "warn" ? 2 : 0)}
            </span>
          </div>

          {verdict !== "empty" && noDoi ? (
            <div className="grid gap-2 sm:grid-cols-2" data-testid="contrast">
              <div className={cn("rounded-xl border px-3 py-2 text-sm", TONE.ok.pill)}>
                <p className="text-xs text-muted-foreground">Citation check</p>✓ Looks fine — 0 notices
              </div>
              <div className={cn("rounded-xl border px-3 py-2 text-sm", verdict === "pass" ? TONE.ok.pill : tone.pill)}>
                <p className="text-xs text-muted-foreground">MoolTrace · {input?.depth ?? 2} hops deep</p>
                {verdict === "pass" ? "✓ Nothing flagged underneath" : `✕ ${noticeWord(deciding?.notice_type)} research found`}
              </div>
            </div>
          ) : null}

          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            Look
            <div className="inline-flex rounded-lg bg-muted p-0.5" role="radiogroup" aria-label="Depth">
              {[1, 2, 3].map((depth) => (
                <button
                  key={depth}
                  type="button"
                  role="radio"
                  aria-checked={input?.depth === depth}
                  disabled={busy !== "" || !input}
                  onClick={() => input && void run({ ...input, depth })}
                  className={cn(
                    "rounded-md px-2.5 py-1 font-medium",
                    input?.depth === depth ? "bg-card text-foreground shadow-sm" : "hover:text-foreground",
                  )}
                >
                  {depth} hop{depth > 1 ? "s" : ""}
                </button>
              ))}
            </div>
            deep
          </div>

          <Chain reasons={check.reasons || []} />

          {verdict === "block" || verdict === "warn" ? (
            fix ? (
              <div className="rounded-xl border p-3 text-sm leading-6" data-testid="fix">
                {fix.before && fix.before !== fix.text ? (
                  <p className="text-red-800 line-through decoration-red-400">{fix.before}</p>
                ) : null}
                <p className="bg-emerald-50 text-emerald-900">{fix.text}</p>
                <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span>
                    Only the affected sentence changes · rechecked:{" "}
                    {fix.recheck ? VERDICT_COPY[verdictOf(fix.recheck)].title.toLowerCase() : "—"}
                  </span>
                  <button
                    type="button"
                    onClick={() => void navigator.clipboard?.writeText(fix.text || "")}
                    className="rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background"
                  >
                    Copy fixed answer
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                disabled={busy !== ""}
                onClick={() => void runFix()}
                className="self-start rounded-xl bg-foreground px-4 py-2 text-sm font-medium text-background disabled:opacity-40"
              >
                {busy === "fix" ? "Fixing…" : "Fix the answer"}
              </button>
            )
          ) : null}

          <details className="text-sm">
            <summary className="cursor-pointer text-xs text-muted-foreground">Why — evidence and query</summary>
            <div className="mt-2 flex flex-col gap-2">
              {(deciding?.hops_evidence || []).map((hop, index) => (
                <div key={index} className="rounded-lg bg-muted px-3 py-2">
                  <p className="text-[11px] text-muted-foreground">
                    hop {index + 1} · {(hop.reliance || "").replaceAll("_", " ")}
                    {hop.weight != null ? ` · weight ${hop.weight}` : ""}
                  </p>
                  <p className="leading-6">{hop.sentence || "No sentence found for this hop."}</p>
                  {hop.source_url ? (
                    <a href={hop.source_url} target="_blank" rel="noreferrer" className="break-all text-xs underline">
                      {hop.source_url}
                    </a>
                  ) : null}
                </div>
              ))}
              {deciding?.notice_doi ? (
                <p className="text-xs text-muted-foreground">
                  Notice: <a className="underline" href={`https://doi.org/${deciding.notice_doi}`} target="_blank" rel="noreferrer">{deciding.notice_doi}</a>
                </p>
              ) : null}
              <p className="text-xs text-muted-foreground">
                {check.algorithm?.explanation || "Decided by algo.SPpaths"} · {check.coverage?.replace("_", " ")}
              </p>
              {check.why_graph?.cypher || check.algorithm?.cypher ? (
                <pre className="max-h-48 overflow-auto rounded-lg bg-muted p-3 font-mono text-[11px] leading-4">
                  {check.why_graph?.cypher || check.algorithm?.cypher}
                </pre>
              ) : null}
              {check.impact?.summary ? <p className="text-xs text-muted-foreground">{check.impact.summary}</p> : null}
            </div>
          </details>
        </section>
      ) : null}
    </div>
  )
}
