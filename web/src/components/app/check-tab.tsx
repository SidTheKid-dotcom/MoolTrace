"use client"

import { ArrowRight, Check, Copy, Link2, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { IndexCard, Thread } from "@/components/board/board"
import { EvidencePath, evidenceQuote, siteName } from "@/components/board/evidence-path"
import {
  checkAnswer,
  monthYear,
  noticeWord,
  parseInput,
  rewriteAnswer,
  verdictOf,
  type Check as CheckResult,
  type Input,
  type Reason,
  type Rewrite,
  type Verdict,
} from "@/lib/api"
import { decidingReason } from "@/lib/path-diagram"
import { EXAMPLES } from "@/lib/presets"
import { cn } from "@/lib/utils"

const VERDICT: Record<Verdict, { title: string; icon: string; tile: string; text: string }> = {
  block: { title: "Don't ship", icon: "✕", tile: "bg-rx-soft text-rx", text: "text-ink" },
  warn: { title: "Review before shipping", icon: "!", tile: "bg-amber-soft text-amber-x", text: "text-ink" },
  pass: { title: "Clear", icon: "✓", tile: "bg-clear-soft text-clear", text: "text-ink" },
  empty: { title: "Not checked", icon: "?", tile: "bg-amber-soft text-amber-x", text: "text-ink" },
}

function reasonLine(check: CheckResult, deciding: Reason | null, depth: number): string {
  const verdict = verdictOf(check)
  if (verdict === "empty") return "Nothing in the graph connects this page to a study. That is not proof it is safe."
  if (verdict === "pass") return `No retraction or concern found within ${depth} hop${depth > 1 ? "s" : ""}.`
  const when = monthYear(deciding?.notice_date)
  const word = noticeWord(deciding?.notice_type)
  const hops = Math.max(1, (deciding?.steps?.length || 1) - 1)
  const where = hops === 1 ? "one step down" : `${hops === 2 ? "two" : "three"} steps down`
  if (word === "Expression of Concern") return `A study ${where} carries an Expression of Concern${when ? ` (${when})` : ""}.`
  return `Rests on research ${word.toLowerCase()}${when ? ` in ${when}` : ""}, ${where}.`
}

function Drawer({ check, onClose }: { check: CheckResult; onClose: () => void }) {
  const deciding = decidingReason(check.reasons || [])
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Evidence">
      <button type="button" aria-label="Close" onClick={onClose} className="absolute inset-0 bg-ink/25 backdrop-blur-[1px]" />
      <aside className="rise relative flex h-full w-full max-w-[480px] flex-col gap-5 overflow-y-auto border-l border-hair bg-card-paper p-7 shadow-2xl">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-[34px] leading-none">Evidence</h3>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-full p-2 text-ink-2 hover:bg-paper">
            <X className="size-5" />
          </button>
        </div>
        {(deciding?.hops_evidence || []).map((hop, index) => {
          const quote = evidenceQuote(hop.sentence)
          return (
            <section key={index} className="flex flex-col gap-2 border-b border-hair pb-5">
              <p className="font-label text-[10.5px] text-ink-2">
                Hop {index + 1} · {(hop.reliance || "").replaceAll("_", " ")}
                {hop.weight != null ? ` · weight ${hop.weight}` : ""}
              </p>
              {quote ? <p className="font-display text-[26px] italic leading-tight">“{quote}”</p> : null}
              <p className="text-[14px] leading-6 text-ink-2">{hop.sentence || "No citing sentence was found for this hop."}</p>
              {hop.source_url ? (
                <a className="font-label truncate text-[10.5px] text-pin underline-offset-2 hover:underline" href={hop.source_url} target="_blank" rel="noreferrer">
                  {hop.source_url.replace(/^https?:\/\//, "")}
                  {hop.fetched_at ? ` · fetched ${hop.fetched_at.slice(0, 10)}` : ""}
                </a>
              ) : null}
            </section>
          )
        })}
        {deciding?.notice_doi ? (
          <section className="rounded-xl border border-rx/25 bg-rx-soft p-4">
            <p className="font-label text-[10.5px] text-rx">
              {noticeWord(deciding.notice_type)} · {monthYear(deciding.notice_date) || "date not confirmed"}
            </p>
            <a className="mt-1 block font-mono text-[13px] underline underline-offset-2" href={`https://doi.org/${deciding.notice_doi}`} target="_blank" rel="noreferrer">
              doi.org/{deciding.notice_doi} ↗
            </a>
          </section>
        ) : null}
        <details className="group rounded-xl border border-hair p-4">
          <summary className="font-label cursor-pointer text-[10.5px] text-ink-2">Cypher · {check.algorithm?.explanation || "algo.SPpaths"}</summary>
          <pre className="mt-3 overflow-x-auto font-mono text-[11px] leading-[1.55] text-ink">{check.why_graph?.cypher || check.algorithm?.cypher}</pre>
        </details>
        {check.coverage ? <p className="font-label text-[10.5px] text-ink-2">Coverage · {check.coverage.replace("_", " ")}</p> : null}
      </aside>
    </div>
  )
}

export function CheckTab({ initial }: { initial?: { input: Input } }) {
  const [raw, setRaw] = useState("")
  const [input, setInput] = useState<Input | null>(null)
  const [check, setCheck] = useState<CheckResult | null>(null)
  const [fix, setFix] = useState<Rewrite | null>(null)
  const [busy, setBusy] = useState<"" | "check" | "fix">("")
  const [error, setError] = useState("")
  const [drawer, setDrawer] = useState(false)
  const [copied, setCopied] = useState(false)
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
  const v = verdict ? VERDICT[verdict] : null
  const deciding = check ? decidingReason(check.reasons || []) : null
  const depth = input?.depth ?? 2
  const noDoi = check?.why_graph?.without_graph?.notice_count === 0
  const exitCode = check ? check.exit_code ?? (check.decision === "block" ? 1 : check.decision === "warn" ? 2 : 0) : 0

  return (
    <div className="flex flex-col gap-6">
      <form
        className="flex items-center gap-3 rounded-2xl border border-hair bg-card-paper p-2 pl-5 shadow-[0_10px_30px_-18px_rgba(22,19,15,.35)] focus-within:ring-2 focus-within:ring-ink/15"
        onSubmit={(event) => {
          event.preventDefault()
          if (raw.trim()) void run(parseInput(raw, depth))
        }}
      >
        <Link2 className="size-5 shrink-0 text-ink-2" aria-hidden />
        <input
          value={raw}
          onChange={(event) => setRaw(event.target.value)}
          placeholder="Paste an AI answer or the link it cites"
          className="h-12 min-w-0 flex-1 bg-transparent text-[16px] text-ink outline-none placeholder:text-ink-2/70"
          aria-label="Answer or link to check"
        />
        <button
          type="submit"
          disabled={!raw.trim() || busy !== ""}
          aria-label="Check"
          className="grid h-12 w-14 place-items-center rounded-xl bg-ink text-cream transition hover:bg-ink/85 disabled:opacity-40"
        >
          {busy === "check" ? <span className="size-4 animate-spin rounded-full border-2 border-cream/40 border-t-cream" /> : <ArrowRight className="size-5" />}
        </button>
      </form>

      <div className="-mt-3 flex flex-wrap gap-2" data-testid="examples">
        {EXAMPLES.map((example) => (
          <button
            key={example.id}
            type="button"
            disabled={busy !== ""}
            onClick={() => {
              setRaw(example.urls.join(" ") || example.text)
              void run({ text: example.text, urls: example.urls, engine: example.engine, depth: example.depth })
            }}
            className="rounded-full border border-hair bg-card-paper px-3.5 py-1.5 text-[13px] text-ink-2 transition hover:border-ink/30 hover:text-ink"
          >
            {example.label}
          </button>
        ))}
      </div>

      {error ? <p className="rounded-xl border border-rx/20 bg-rx-soft px-4 py-3 text-[14px] text-rx">{error}</p> : null}

      {!check && busy !== "check" && !error ? (
        <div className="flex flex-col items-center gap-6 py-10">
          <div className="flex w-full max-w-xl items-center opacity-60">
            {[0, 1, 2].map((i) => (
              <div key={i} className="contents">
                {i > 0 ? <Thread /> : null}
                <div className="flex-1">
                  <IndexCard label="—" title={<span className="text-ink/30">· · ·</span>} />
                </div>
              </div>
            ))}
          </div>
          <p className="text-[14px] text-ink-2">Pick an example, or paste your own.</p>
        </div>
      ) : null}

      {busy === "check" && !check ? (
        <div className="flex flex-col items-center gap-3 rounded-[20px] border border-hair bg-card-paper py-14">
          <span className="font-label text-[11px] text-ink-2" style={{ animation: "mt-pulse 1.4s ease-in-out infinite" }}>
            Following citations · page → review → trial
          </span>
        </div>
      ) : null}

      {check && v && verdict ? (
        <section
          className={cn("rise flex flex-col gap-6 rounded-[20px] border border-hair bg-card-paper p-6 shadow-[0_18px_40px_-28px_rgba(22,19,15,.45)] sm:p-8", busy === "check" && "opacity-60")}
          key={`${verdict}-${depth}-${check.reasons?.length}`}
        >
          <div className="flex items-start gap-4">
            <div className={cn("grid size-12 shrink-0 place-items-center rounded-2xl text-[26px] font-semibold sm:size-16 sm:text-[34px]", v.tile)}>{v.icon}</div>
            <div className="min-w-0 flex-1">
              <h2 className="font-display text-[40px] leading-[1.02] sm:text-[52px]" data-testid="verdict">
                {v.title}
              </h2>
              <p className="mt-1 text-[17px] text-ink-2">{reasonLine(check, deciding, depth)}</p>
            </div>
            <span
              title="CI exit code: clear 0 · review 2 · don't ship 1"
              className={cn(
                "hidden rounded-md px-2.5 py-1 font-mono text-[13px] sm:inline",
                verdict === "block" ? "bg-rx-soft text-rx" : verdict === "pass" ? "bg-clear-soft text-clear" : "bg-amber-soft text-amber-x",
              )}
            >
              exit {exitCode}
            </span>
          </div>

          <div className="h-px bg-hair" />

          {verdict !== "empty" && noDoi ? (
            <div className="flex flex-wrap gap-3" data-testid="contrast">
              <span className="inline-flex items-center gap-2 rounded-xl border border-clear/40 bg-clear-soft/60 px-3.5 py-2 text-[14px] font-medium text-clear">
                <span className="grid size-5 place-items-center rounded-full bg-clear text-white"><Check className="size-3.5" /></span>
                Citation check · looks fine
              </span>
              {verdict === "pass" ? (
                <span className="inline-flex items-center gap-2 rounded-xl border border-clear/40 bg-clear-soft/60 px-3.5 py-2 text-[14px] font-medium text-clear">
                  <span className="grid size-5 place-items-center rounded-full bg-clear text-white"><Check className="size-3.5" /></span>
                  MoolTrace · nothing flagged underneath
                </span>
              ) : (
                <span className={cn("inline-flex items-center gap-2 rounded-xl px-3.5 py-2 text-[14px] font-medium", verdict === "block" ? "bg-rx-soft text-rx" : "bg-amber-soft text-amber-x")}>
                  <span className={cn("grid size-5 place-items-center rounded-full text-white", verdict === "block" ? "bg-rx" : "bg-amber-x")}>
                    <X className="size-3.5" />
                  </span>
                  MoolTrace · {noticeWord(deciding?.notice_type).toLowerCase()} {deciding?.notice_type?.includes("concern") ? "found" : "research found"}
                </span>
              )}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-3 text-[15px] text-ink-2">
            Look
            <div className="inline-flex rounded-xl border border-hair bg-paper p-1" role="radiogroup" aria-label="Depth">
              {[1, 2, 3].map((d) => (
                <button
                  key={d}
                  type="button"
                  role="radio"
                  aria-checked={depth === d}
                  disabled={busy !== "" || !input}
                  onClick={() => input && void run({ ...input, depth: d })}
                  className={cn(
                    "whitespace-nowrap rounded-lg px-3 py-1.5 font-mono text-[14px] transition sm:px-4",
                    depth === d ? "bg-ink text-cream shadow" : "text-ink-2 hover:text-ink",
                  )}
                >
                  {d} hop{d > 1 ? "s" : ""}
                </button>
              ))}
            </div>
            deep
            {verdict === "pass" && depth < 3 ? (
              <button type="button" onClick={() => input && void run({ ...input, depth: depth + 1 })} className="ml-1 text-[14px] font-medium text-ink underline underline-offset-4">
                Look deeper →
              </button>
            ) : null}
          </div>

          <div className="pt-3">
            {verdict === "empty" ? (
              <div className="flex max-w-md items-center">
                <div className="flex-1">
                  <IndexCard label={`Page · ${siteName(input?.urls[0])}`} title={input?.urls[0]?.replace(/^https?:\/\/(www\.)?/, "").split("/").slice(-2).join(" ").replaceAll("-", " ") || "Cited page"} />
                </div>
                <Thread className="opacity-40" />
                <span className="font-label text-[10px] text-ink-2">no study</span>
              </div>
            ) : check.reasons?.length ? (
              <EvidencePath reasons={check.reasons} onOpen={() => setDrawer(true)} />
            ) : (
              <div className="flex max-w-md items-center">
                <div className="flex-1">
                  <IndexCard label={input?.urls[0] ? `Page · ${siteName(input.urls[0])}` : "Paper"} title={input?.urls[0] ? "Cited page" : input?.text || "Cited work"} />
                </div>
                <Thread />
                <span className="font-label text-[10px] text-clear">nothing flagged</span>
              </div>
            )}
          </div>

          <div className="h-px bg-hair" />

          {(verdict === "block" || verdict === "warn") && fix ? (
            <div className="rise flex flex-col gap-3 rounded-2xl border border-hair bg-paper/60 p-5" data-testid="fix">
              <p className="font-label text-[10.5px] text-ink-2">Fixed answer</p>
              {fix.before && fix.before !== fix.text ? (
                <p className="text-[16px] leading-7 text-ink-2 line-through decoration-rx decoration-2">{fix.before}</p>
              ) : null}
              <p className="rounded-lg bg-clear-soft px-3 py-2 text-[16px] leading-7 text-ink">{fix.text}</p>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="inline-flex items-center gap-2 text-[14px] text-ink-2">
                  <Check className="size-4 text-clear" /> Only the affected sentence changed · rechecked:{" "}
                  {fix.recheck ? VERDICT[verdictOf(fix.recheck)].title.toLowerCase() : "—"}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard?.writeText(fix.text || "")
                    setCopied(true)
                    setTimeout(() => setCopied(false), 1500)
                  }}
                  className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-2.5 text-[14px] font-semibold text-cream"
                >
                  <Copy className="size-4" /> {copied ? "Copied" : "Copy fixed answer"}
                </button>
              </div>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-6">
            {(verdict === "block" || verdict === "warn") && !fix ? (
              <button
                type="button"
                disabled={busy !== ""}
                onClick={() => void runFix()}
                className="inline-flex items-center gap-3 rounded-full bg-ink px-7 py-3.5 text-[16px] font-semibold text-cream transition hover:bg-ink/85 disabled:opacity-40"
              >
                {busy === "fix" ? "Fixing…" : "Fix the answer"} <ArrowRight className="size-5" />
              </button>
            ) : null}
            {check.reasons?.length ? (
              <button type="button" onClick={() => setDrawer(true)} className="text-[16px] text-ink underline underline-offset-4">
                Why — evidence and query ↓
              </button>
            ) : null}
            {verdict === "pass" ? <span className="text-[13px] text-ink-2">Clear is not a medical-accuracy check.</span> : null}
          </div>
        </section>
      ) : null}

      {drawer && check ? <Drawer check={check} onClose={() => setDrawer(false)} /> : null}
    </div>
  )
}
