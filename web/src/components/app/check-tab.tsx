"use client"

import { ArrowRight, Check, Copy, Link2, X } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { CypherPanel } from "@/components/app/cypher-panel"
import { HopGraph } from "@/components/app/hop-graph"
import {
  checkAnswer,
  parseInput,
  rewriteAnswer,
  verdictOf,
  type Check as CheckResult,
  type Input,
  type Reason,
  type Rewrite,
  type Verdict,
} from "@/lib/api"
import { cleanSnippet } from "@/lib/clean-snippet"
import { flagKind, flagLabel, monthYear, pageName, pageTitle, relianceWord } from "@/lib/naming"
import { decidingReason } from "@/lib/path-diagram"
import { EXAMPLES } from "@/lib/presets"
import { cn } from "@/lib/utils"

export const VERDICT: Record<Verdict, { title: string; icon: string; tile: string }> = {
  block: { title: "Don't ship", icon: "✕", tile: "bg-rx-soft text-rx" },
  warn: { title: "Review before shipping", icon: "!", tile: "bg-amber-soft text-amber-x" },
  pass: { title: "Clear", icon: "✓", tile: "bg-clear-soft text-clear" },
  empty: { title: "Not checked — not proof it's safe", icon: "?", tile: "bg-amber-soft text-amber-x" },
}

const STRONG = new Set(["included", "relies", "uses_data_or_method"])

function hopWord(n: number): string {
  return `${n} hop${n === 1 ? "" : "s"}`
}

function reasonLine(check: CheckResult, deciding: Reason | null, depth: number): string {
  const verdict = verdictOf(check)
  if (verdict === "empty") return "Nothing in the graph connects this page to a study."
  if (verdict === "pass") return `No retraction, withdrawal or concern found within ${hopWord(depth)}.`
  const hops = Math.max(1, (deciding?.steps?.length || 2) - 1)
  const where = `${hopWord(hops)} down${hops < depth ? ` (searched ${hopWord(depth)})` : ""}`
  const kind = flagKind(deciding?.root_doi?.startsWith("10.1002/14651858.") && deciding?.notice_type?.includes("retract") ? "withdrawal" : deciding?.notice_type)
  const label = flagLabel(deciding?.notice_type, deciding?.notice_date, deciding?.root_doi)
  if (kind === "concern") return `A study ${where} carries an Expression of Concern (${monthYear(deciding?.notice_date) || "date not confirmed"}).`
  const hopsEvidence = deciding?.hops_evidence || []
  const into = hopsEvidence[hopsEvidence.length - 1]?.reliance || ""
  const word = label.split(" · ")[0]
  if (verdict === "warn" && !STRONG.has(into)) {
    const who = hops === 1 ? "The page" : "The paper before it"
    return `${word} paper ${where}. ${who} only cites this paper; it doesn't rely on its data.`
  }
  return `Rests on research ${word.replace(/^Retracted|^Withdrawn/, (m) => m.toLowerCase())}${monthYear(deciding?.notice_date) ? ` in ${monthYear(deciding?.notice_date)}` : ""}, ${where}.`
}

function Drawer({ check, onClose }: { check: CheckResult; onClose: () => void }) {
  const deciding = decidingReason(check.reasons || [])
  const panel = useRef<HTMLElement>(null)
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    const el = panel.current
    el?.querySelector<HTMLElement>("button, a")?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== "Tab" || !el) return
      const items = Array.from(el.querySelectorAll<HTMLElement>("button, a, summary")).filter((item) => !item.hasAttribute("disabled"))
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("keydown", onKey)
      opener?.focus()
    }
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-labelledby="evidence-title">
      <div aria-hidden onClick={onClose} className="absolute inset-0 bg-ink/25" />
      <aside ref={panel} className="relative flex h-full w-full max-w-[480px] flex-col gap-5 overflow-y-auto border-l border-hair bg-card-paper p-7 shadow-2xl">
        <div className="flex items-center justify-between">
          <h3 id="evidence-title" className="font-display text-[34px] leading-none">Evidence</h3>
          <button type="button" onClick={onClose} aria-label="Close (Escape)" className="rounded-full p-2 text-ink-2 hover:bg-paper">
            <X className="size-5" />
          </button>
        </div>
        {(deciding?.hops_evidence || []).map((hop, index) => {
          const snippet = cleanSnippet(hop.sentence)
          return (
            <section key={index} className="flex flex-col gap-2 border-b border-hair pb-5">
              <p className="font-label text-[10.5px] text-ink-2">
                Hop {index + 1} · {relianceWord(hop.reliance)}
                {hop.weight != null ? ` · weight ${hop.weight}` : ""}
              </p>
              <p className="text-[15px] leading-6 text-ink">{snippet ? `“${snippet}”` : "No citing sentence was found for this hop."}</p>
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
            <p className="font-label text-[10.5px] text-rx">{flagLabel(deciding.notice_type, deciding.notice_date, deciding.root_doi)}</p>
            <a className="mt-1 block font-mono text-[13px] underline underline-offset-2" href={`https://doi.org/${deciding.notice_doi}`} target="_blank" rel="noreferrer">
              doi.org/{deciding.notice_doi} ↗
            </a>
          </section>
        ) : null}
        <CypherPanel check={check} open />
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
  const [pending, setPending] = useState<string>("")
  const [animate, setAnimate] = useState(false)
  const [error, setError] = useState("")
  const [drawer, setDrawer] = useState(false)
  const [copied, setCopied] = useState(false)
  const started = useRef(false)
  const closeDrawer = useCallback(() => setDrawer(false), [])

  async function run(next: Input, via: "depth" | "other" = "other", id = "") {
    setInput(next)
    setFix(null)
    setError("")
    setBusy("check")
    setPending(id)
    try {
      const result = await checkAnswer(next)
      // Only a depth change animates: the path grows, then the verdict lands. Presets and tabs switch instantly.
      setAnimate(via === "depth")
      setCheck(result)
    } catch (exc) {
      setCheck(null)
      setError(exc instanceof Error ? exc.message : "The check did not finish.")
    } finally {
      setBusy("")
      setPending("")
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
  const explored = (check as unknown as { explored?: { source_title?: string }[] } | null)?.explored || []
  const verdictDelay = animate ? (depth + 1) * 120 + 250 : 0

  return (
    <div className="flex flex-col gap-6">
      <form
        className="flex items-center gap-3 rounded-2xl border border-hair bg-card-paper p-2 pl-5 shadow-[0_10px_30px_-18px_rgba(22,19,15,.35)] focus-within:ring-2 focus-within:ring-ink/15"
        onSubmit={(event) => {
          event.preventDefault()
          if (raw.trim()) void run(parseInput(raw, depth), "other", "submit")
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
          className="grid h-12 w-14 place-items-center rounded-xl bg-ink text-cream transition hover:bg-ink/85 active:scale-95 disabled:opacity-40"
        >
          {pending === "submit" ? <span className="size-4 animate-spin rounded-full border-2 border-cream/40 border-t-cream" /> : <ArrowRight className="size-5" />}
        </button>
      </form>

      <div className="-mt-3 flex flex-wrap gap-2" data-testid="examples">
        {EXAMPLES.map((example) => (
          <button
            key={example.id}
            type="button"
            disabled={busy !== ""}
            aria-pressed={!!input && input.urls.join(" ") === example.urls.join(" ") && input.text === example.text}
            onClick={() => {
              setRaw(example.urls.join(" ") || example.text)
              void run({ text: example.text, urls: example.urls, engine: example.engine, depth: example.depth }, "other", example.id)
            }}
            className={cn(
              "inline-flex items-center gap-2 rounded-full border border-hair bg-card-paper px-3.5 py-1.5 text-[13px] text-ink-2 transition hover:border-ink/30 hover:text-ink active:scale-95 aria-pressed:border-ink aria-pressed:text-ink",
              pending === example.id && "border-ink text-ink",
            )}
          >
            {pending === example.id ? <span className="size-3 animate-spin rounded-full border-2 border-ink/30 border-t-ink" /> : null}
            {example.label}
          </button>
        ))}
      </div>

      {error ? <p className="rounded-xl border border-rx/20 bg-rx-soft px-4 py-3 text-[14px] text-rx">{error}</p> : null}

      {!check && busy !== "check" && !error ? (
        <div className="flex flex-col items-center gap-3 rounded-[20px] border border-dashed border-hair py-14 text-center">
          <p className="font-display text-[30px] leading-none">Pick an example, or paste your own.</p>
          <p className="max-w-md text-[14.5px] text-ink-2">Start with Harvard vitamin D: it is clear at 1 hop and blocked at 2.</p>
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
          className={cn("flex flex-col gap-6 rounded-[20px] border border-hair bg-card-paper p-6 shadow-[0_18px_40px_-28px_rgba(22,19,15,.45)] transition-opacity sm:p-8", busy === "check" && "opacity-60")}
          data-testid="check-result"
        >
          <div className={cn("flex items-start gap-4", animate && "rise")} style={animate ? { animationDelay: `${verdictDelay}ms` } : undefined}>
            <div className={cn("grid size-12 shrink-0 place-items-center rounded-2xl text-[26px] font-semibold sm:size-16 sm:text-[34px]", v.tile)} aria-hidden>{v.icon}</div>
            <div className="min-w-0 flex-1">
              <h2 className={cn("font-display leading-[1.02]", verdict === "empty" ? "text-[34px] sm:text-[44px]" : "text-[40px] sm:text-[52px]")} data-testid="verdict">
                {v.title}
              </h2>
              <p className="mt-1 text-[17px] text-ink-2" data-testid="reason-line">{reasonLine(check, deciding, depth)}</p>
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
                  MoolTrace · nothing flagged within {hopWord(depth)}
                </span>
              ) : (
                <span className={cn("inline-flex items-center gap-2 rounded-xl px-3.5 py-2 text-[14px] font-medium", verdict === "block" ? "bg-rx-soft text-rx" : "bg-amber-soft text-amber-x")}>
                  <span className={cn("grid size-5 place-items-center rounded-full text-white", verdict === "block" ? "bg-rx" : "bg-amber-x")}>
                    <X className="size-3.5" />
                  </span>
                  MoolTrace · {flagLabel(deciding?.notice_type, deciding?.notice_date, deciding?.root_doi).split(" · ")[0].replace(/^Retracted|^Withdrawn/, (m) => m.toLowerCase())} paper found
                </span>
              )}
            </div>
          ) : null}

          {verdict !== "empty" ? (
            <div className="flex flex-wrap items-center gap-3 text-[15px] text-ink-2">
              Hops searched
              <div className="inline-flex rounded-xl border border-hair bg-paper p-1" role="radiogroup" aria-label="Hops searched">
                {[1, 2, 3].map((d) => (
                  <button
                    key={d}
                    type="button"
                    role="radio"
                    aria-checked={depth === d}
                    disabled={busy !== "" || !input}
                    onClick={() => input && depth !== d && void run({ ...input, depth: d }, "depth", `depth-${d}`)}
                    className={cn(
                      "inline-flex min-h-9 items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 font-mono text-[14px] transition active:scale-95 sm:px-4",
                      depth === d ? "bg-ink text-cream shadow" : "text-ink-2 hover:text-ink",
                    )}
                  >
                    {pending === `depth-${d}` ? <span className="size-3 animate-spin rounded-full border-2 border-ink/30 border-t-ink" /> : null}
                    {hopWord(d)}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="min-h-[132px] pt-2" data-testid="graph-area">
            {verdict === "empty" ? (
              <div className="flex max-w-md flex-col gap-2">
                <div className="paper-texture index-card rounded-[6px] px-3.5 pb-3 pt-3">
                  <p className="font-label text-[10.5px] text-ink-2">Page · {pageName(input?.urls[0]).split(" · ")[0]}</p>
                  <p className="font-display mt-1 text-[21px] leading-[1.08]">{pageTitle(explored[0]?.source_title) || "Cited page"}</p>
                  <p className="mt-2 text-[12.5px] text-ink-2">No study in the graph connects to this page.</p>
                </div>
              </div>
            ) : (
              <HopGraph check={check} depth={depth} url={input?.urls[0]} animate={animate} onOpen={check.reasons?.length ? () => setDrawer(true) : undefined} />
            )}
          </div>

          {verdict !== "empty" ? <CypherPanel check={check} /> : null}

          <div className="h-px bg-hair" />

          {(verdict === "block" || verdict === "warn") && fix ? (
            <div className="flex flex-col gap-3 rounded-2xl border border-hair bg-paper/60 p-5" data-testid="fix">
              <p className="font-label text-[10.5px] text-ink-2">Fixed answer</p>
              {fix.before && fix.before !== fix.text ? (
                <p className="text-[16px] leading-7 text-ink-2 line-through decoration-rx decoration-2">{fix.before}</p>
              ) : null}
              <p className="rounded-lg bg-clear-soft px-3 py-2 text-[16px] leading-7 text-ink">{fix.text}</p>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="inline-flex items-center gap-2 text-[14px] text-ink-2">
                  <Check className="size-4 text-clear" /> Only the affected sentence changed · checked again:{" "}
                  {fix.recheck ? VERDICT[verdictOf(fix.recheck)].title.toLowerCase() : "—"}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard?.writeText(fix.text || "")
                    setCopied(true)
                    setTimeout(() => setCopied(false), 1500)
                  }}
                  className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-2.5 text-[14px] font-semibold text-cream active:scale-95"
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
                className="inline-flex items-center gap-3 rounded-full bg-ink px-7 py-3.5 text-[16px] font-semibold text-cream transition hover:bg-ink/85 active:scale-95 disabled:opacity-40"
              >
                {busy === "fix" ? "Fixing…" : "Fix the answer"} <ArrowRight className="size-5" />
              </button>
            ) : null}
            {check.reasons?.length && verdict !== "empty" ? (
              <button type="button" onClick={() => setDrawer(true)} className="text-[16px] text-ink underline underline-offset-4">
                Why: evidence and query →
              </button>
            ) : null}
            {verdict === "pass" ? <span className="text-[13px] text-ink-2">Clear is not a medical-accuracy check.</span> : null}
          </div>
        </section>
      ) : null}

      {drawer && check ? <Drawer check={check} onClose={closeDrawer} /> : null}
    </div>
  )
}
