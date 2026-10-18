"use client"

/* eslint-disable @next/next/no-img-element */
import Link from "next/link"
import { ArrowRight, Check, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { IndexCard, Magnifier, Pin, Reveal, Stamp, Thread } from "@/components/board/board"
import { EvidencePath } from "@/components/board/evidence-path"
import { checkAnswer, verdictOf, type Check as CheckResult } from "@/lib/api"
import { FIELD_SCAN } from "@/lib/field-scan"
import { MCP_URL, REPO_URL } from "@/lib/presets"
import { cn } from "@/lib/utils"

const HARVARD = { text: "", urls: ["https://nutritionsource.hsph.harvard.edu/vitamin-d/"], engine: "nutrition-coach" }

function Nav({ dark = true }: { dark?: boolean }) {
  return (
    <header className="relative z-10 flex items-center justify-between">
      <span className={cn("font-mono text-[22px] tracking-tight", dark ? "text-cream" : "text-ink")}>mooltrace</span>
      <nav className="flex items-center gap-7 text-[15px]">
        <a href="#how" className={cn("hidden sm:block", dark ? "text-cream/90 hover:text-cream" : "text-ink-2")}>How it works</a>
        <a href={REPO_URL} className={cn("hidden underline underline-offset-4 sm:block", dark ? "text-cream/90 hover:text-cream" : "text-ink-2")}>GitHub</a>
        <Link href="/app" className="rounded-full bg-cream px-6 py-3 font-semibold text-ink shadow-[0_8px_24px_-10px_rgba(0,0,0,.6)] transition hover:bg-white">
          Open the demo
        </Link>
      </nav>
    </header>
  )
}

/* ---------- B2 · hero ---------- */
function HeroBoard() {
  return (
    <div className="relative mx-auto aspect-[1.25] w-full max-w-[720px]" aria-label="Harvard Nutrition Source cites a Cochrane review that included the Ishida 2004 trial, retracted in 2025">
      <svg viewBox="0 0 640 512" className="absolute inset-0 size-full" aria-hidden>
        <path d="M228 168 C 214 210, 196 236, 160 262" fill="none" stroke="#b8a989" strokeWidth="2.4" className="draw" pathLength={1} style={{ animationDelay: "500ms" }} />
        <path d="M272 338 C 300 356, 352 356, 386 326" fill="none" stroke="#d4351c" strokeWidth="3.4" className="draw" pathLength={1} style={{ animationDelay: "900ms" }} />
      </svg>
      <div className="rise absolute left-[20%] top-[2%] w-[50%] -rotate-[0.6deg]" style={{ animationDelay: "150ms" }}>
        <IndexCard size="lg" label="Page · Harvard Nutrition Source" title="Vitamin D" />
      </div>
      <div className="rise absolute left-0 top-[51%] w-[43%] rotate-[0.8deg]" style={{ animationDelay: "350ms" }}>
        <IndexCard size="lg" label="Review · Cochrane 2014" title="Vitamin D and vitamin D analogues for preventing fractures" />
      </div>
      <div className="rise absolute right-0 top-[45%] w-[40%] rotate-[0.4deg]" style={{ animationDelay: "550ms" }}>
        <IndexCard size="lg" label="Trial · Ishida 2004" title="Yamaguchi osteoporosis study" tone="red" pin="red" stamp="Retracted 2025" stampDelay={1300} />
      </div>
      <div className="absolute z-20" style={{ left: "51%", top: "66%", transform: "translate(-34%,-34%)" }}>
        <Magnifier quote="an included trial" size={176} />
      </div>
    </div>
  )
}

function Hero() {
  return (
    <section className="relative isolate overflow-hidden bg-night text-cream">
      <img src="/img/desk-night.webp" alt="" aria-hidden className="absolute inset-0 -z-20 size-full object-cover object-right" />
      <div aria-hidden className="absolute inset-0 -z-10 bg-[linear-gradient(90deg,rgba(20,18,15,.96)_0%,rgba(20,18,15,.86)_42%,rgba(20,18,15,.55)_70%,rgba(20,18,15,.35)_100%)]" />
      <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_45%_55%_at_74%_55%,rgba(20,18,15,.72),rgba(20,18,15,0))]" />
      <div aria-hidden className="dotted-grid absolute inset-0 -z-10" />
      <div className="mx-auto flex min-h-[100svh] max-w-[1280px] flex-col px-6 py-7 sm:px-10">
        <Nav />
        <div className="grid flex-1 items-center gap-12 py-12 lg:grid-cols-[1fr_1fr]">
          <div className="flex flex-col gap-7">
            <p className="font-label rise text-[12px] text-cream-2">For teams shipping health AI</p>
            <h1 className="font-display rise text-[clamp(40px,4.1vw,70px)] leading-[1.0]" style={{ animationDelay: "80ms" }}>
              Your AI cites a page.
              <br />
              That page cites a review.
              <br />
              The review rests on a <span className="text-[#ff5a43]">retracted trial.</span>
            </h1>
            <p className="rise max-w-[600px] text-[18px] leading-[1.6] text-cream/85" style={{ animationDelay: "160ms" }}>
              MoolTrace builds a citation graph in FalkorDB from the answer, through each page and review, down to the trials. It blocks the answer if a source it relies on was retracted, warns on an Expression of Concern, shows you the exact path, and drafts a fix.
            </p>
            <div className="rise grid max-w-[600px] gap-2 rounded-2xl border border-cream/15 bg-black/25 p-4 text-[15px] sm:grid-cols-2" style={{ animationDelay: "200ms" }}>
              <p className="flex items-start gap-2 text-cream/85"><Check className="mt-0.5 size-4 shrink-0 text-[#5fd39c]" /> A citation check passes all 35 Harvard nutrition pages.</p>
              <p className="flex items-start gap-2 text-cream"><X className="mt-0.5 size-4 shrink-0 text-[#ff5a43]" /> MoolTrace flags 2 — both verified by hand.</p>
            </div>
            <div className="rise flex flex-wrap gap-4" style={{ animationDelay: "240ms" }}>
              <Link href="/app?preset=harvard-vitamin-d" className="inline-flex items-center gap-2.5 rounded-full bg-cream px-6 py-3.5 text-[16px] font-semibold text-ink transition hover:bg-white">
                Watch it catch the Harvard page <ArrowRight className="size-5" />
              </Link>
              <Link href="/app?tab=agent" className="inline-flex items-center rounded-full border border-cream/60 px-6 py-3.5 text-[16px] font-medium text-cream transition hover:border-cream hover:bg-cream/5">
                Run the agent on a draft
              </Link>
            </div>
            <p className="rise font-mono text-[13px] text-cream-2" style={{ animationDelay: "320ms" }}>
              Not in the graph? We say &ldquo;not checked&rdquo;, never &ldquo;safe&rdquo;.
            </p>
          </div>
          <HeroBoard />
        </div>
      </div>
    </section>
  )
}

/* ---------- B3 · live demo ---------- */
function LiveDemo() {
  const [depth, setDepth] = useState(1)
  const [check, setCheck] = useState<CheckResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [started, setStarted] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const auto = useRef(false)

  async function run(d: number) {
    setDepth(d)
    setBusy(true)
    try {
      setCheck(await checkAnswer({ ...HARVARD, depth: d }))
    } catch {
      setCheck(null)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        io.disconnect()
        setStarted(true)
      }
    }, { threshold: 0.35 })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    if (!started) return
    let cancelled = false
    void (async () => {
      await run(1)
      await new Promise((r) => setTimeout(r, 1800))
      if (!cancelled && !auto.current) await run(2)
    })()
    return () => {
      cancelled = true
    }
  }, [started])

  const verdict = check ? verdictOf(check) : null
  return (
    <section className="bg-paper px-6 py-24 text-ink sm:px-10">
      <div ref={ref} className="mx-auto flex max-w-[1180px] flex-col gap-8">
        <div>
          <p className="font-label text-[12px] text-ink-2">Live · Harvard vitamin D page</p>
          <h2 className="font-display mt-2 text-[48px] leading-none sm:text-[60px]">Watch it catch one.</h2>
        </div>
        <div className="grid gap-8 rounded-[24px] border border-hair bg-card-paper p-6 shadow-[0_24px_60px_-40px_rgba(22,19,15,.5)] sm:p-9 lg:grid-cols-[110px_minmax(0,1fr)_260px]">
          <div className="flex flex-row gap-3 lg:flex-col" role="radiogroup" aria-label="Depth">
            {[1, 2, 3].map((d) => (
              <button
                key={d}
                type="button"
                role="radio"
                aria-checked={depth === d}
                disabled={busy}
                onClick={() => {
                  auto.current = true
                  void run(d)
                }}
                className="flex items-center gap-3 text-left font-mono text-[15px]"
              >
                <span className={cn("grid size-5 place-items-center rounded-full border-2 transition", depth === d ? "border-ink bg-ink" : "border-hair")}>
                  {depth === d ? <span className="size-1.5 rounded-full bg-cream" /> : null}
                </span>
                <span className={depth === d ? "text-ink" : "text-ink-2"}>{d} hop{d > 1 ? "s" : ""}</span>
              </button>
            ))}
            <p className="hidden pt-2 text-[12px] text-ink-2 lg:block">click to look deeper</p>
          </div>
          <div className={cn("min-h-[190px] transition-opacity", busy && "opacity-50")}>
            {check?.reasons?.length ? (
              <EvidencePath reasons={check.reasons} compact />
            ) : (
              <div className="flex max-w-sm items-center pt-4">
                <div className="flex-1">
                  <IndexCard label="Page · Harvard Nutrition Source" title="Vitamin D" />
                </div>
                <Thread />
                <span className="font-mono text-[11px] text-clear">{check ? "nothing flagged at 1 hop" : "checking…"}</span>
              </div>
            )}
          </div>
          <div className="flex flex-col gap-3 border-t border-hair pt-6 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0">
            {verdict === "block" ? (
              <>
                <div className="flex items-center gap-3">
                  <span className="grid size-10 place-items-center rounded-xl bg-rx-soft text-xl font-bold text-rx">✕</span>
                  <span className="font-display text-[36px] leading-none">Don&apos;t ship</span>
                </div>
                <p className="text-[15px] text-ink-2">Rests on research retracted in May 2025, two steps down.</p>
                <span className="inline-flex w-fit items-center gap-2 rounded-lg border border-clear/40 px-2.5 py-1 text-[13px] text-clear"><Check className="size-3.5" /> Citation check: looks fine</span>
                <span className="inline-flex w-fit items-center gap-2 rounded-lg bg-rx px-2.5 py-1 text-[13px] text-white"><X className="size-3.5" /> MoolTrace: retracted trial found</span>
              </>
            ) : verdict === "pass" ? (
              <>
                <div className="flex items-center gap-3">
                  <span className="grid size-10 place-items-center rounded-xl bg-clear-soft text-xl font-bold text-clear">✓</span>
                  <span className="font-display text-[36px] leading-none">Clear</span>
                </div>
                <p className="text-[15px] text-ink-2">At {depth} hop{depth > 1 ? "s" : ""} this page looks clean.</p>
              </>
            ) : (
              <p className="font-label text-[11px] text-ink-2">Following citations…</p>
            )}
          </div>
        </div>
        <p className="text-[17px] text-ink-2">At 1 hop this page looks clean. The problem is two steps down.</p>
      </div>
    </section>
  )
}

/* ---------- B4 · finding ---------- */
function Finding() {
  const flagged = FIELD_SCAN.filter((p) => p.flag)
  return (
    <section className="bg-paper px-6 pb-24 text-ink sm:px-10">
      <Reveal className="mx-auto grid max-w-[1180px] gap-10 lg:grid-cols-[1.4fr_1fr] lg:items-center">
        <div>
          <p className="font-display text-[120px] leading-[0.9] text-rx sm:text-[150px]">
            {flagged.length} of {FIELD_SCAN.length}
          </p>
          <h2 className="font-display mt-3 text-[40px] leading-[1.04] sm:text-[54px]">Harvard nutrition pages rest on withdrawn or retracted research.</h2>
          <p className="mt-4 text-[22px] text-ink-2">A citation check passes all {FIELD_SCAN.length}.</p>
        </div>
        <a href="https://doi.org/10.1002/14651858.CD001364.pub5" target="_blank" rel="noreferrer" className="block rotate-[0.8deg] transition hover:rotate-0">
          <div className="paper-texture index-card relative rounded-[6px] p-7">
            <Pin className="size-6" />
            <p className="font-display text-[34px] leading-tight">Zinc for the common cold</p>
            <p className="font-label mt-2 text-[12px] text-ink-2">Cochrane · 2011 version · cited by Harvard&apos;s zinc page</p>
            <p className="mt-4 text-[15px] leading-6 text-ink-2">Withdrawn by Cochrane in April 2015 over concerns about the calculation and analysis of data.</p>
            <span className="absolute -bottom-3 right-4">
              <Stamp className="text-[20px]">Withdrawn</Stamp>
            </span>
          </div>
        </a>
        <div className="lg:col-span-2">
          <div className="grid grid-cols-7 gap-1.5 sm:grid-cols-[repeat(35,minmax(0,1fr))]">
            {FIELD_SCAN.map((page, i) => (
              <Link
                key={page.url}
                href={`/app?url=${encodeURIComponent(page.url)}`}
                className={cn(
                  "group relative grid h-11 place-items-center rounded-md border font-mono text-[12px] transition hover:-translate-y-0.5",
                  page.flag ? "border-rx bg-rx text-white" : "border-hair bg-card-paper text-ink-2 hover:border-ink/40",
                )}
              >
                {i + 1}
                <span className="pointer-events-none absolute bottom-[calc(100%+8px)] left-1/2 z-10 hidden w-max max-w-[220px] -translate-x-1/2 rounded-lg border border-hair bg-card-paper px-3 py-1.5 text-left font-mono text-[11px] text-ink shadow-lg group-hover:block">
                  {page.name}
                  {page.flag ? " · rests on withdrawn or retracted research" : ""}
                </span>
              </Link>
            ))}
          </div>
          <p className="font-label mt-5 border-t border-hair pt-4 text-[11px] text-ink-2">
            Every page linked from Harvard&apos;s Vitamins &amp; Minerals index · checked 17 Oct 2026 · each hit verified by hand
          </p>
        </div>
      </Reveal>
    </section>
  )
}

/* ---------- B5 · how it works ---------- */
function HowItWorks() {
  const steps = [
    {
      n: "01",
      title: "Give it an answer",
      body: "A draft, the links it cites, or a call from your agent over MCP.",
      visual: <div className="rounded-2xl rounded-bl-sm border border-hair bg-paper px-3 py-2 text-[13px] text-ink-2">Vitamin D prevents fractures — Harvard</div>,
    },
    {
      n: "02",
      title: "It builds the citation graph",
      body: "Pages are resolved to papers (Crossref, OpenAlex, PubMed) and stored in FalkorDB as page → review → trial. Retractions and Expressions of Concern attach as dated notice nodes.",
      visual: (
        <div className="flex flex-wrap items-center gap-1 font-mono text-[11px]">
          <span className="rounded-md border border-hair bg-paper px-2 py-1">Page</span>→<span className="rounded-md border border-hair bg-paper px-2 py-1">Review</span>→
          <span className="rounded-md border border-hair bg-paper px-2 py-1">Trial</span>←<span className="rounded-md border border-rx/30 bg-rx-soft px-2 py-1 text-rx">Notice</span>
        </div>
      ),
    },
    {
      n: "03",
      title: "It weighs each link",
      body: "A trial included in a review counts fully; a passing mention counts much less. FalkorDB's shortest-path search finds the strongest chain to any flagged paper.",
      visual: (
        <div className="flex flex-col gap-1 font-mono text-[11px]">
          {[["included", 100], ["uses its data", 85], ["mention", 55], ["background", 20]].map(([k, w]) => (
            <div key={k} className="flex items-center gap-2">
              <span className="w-24 text-ink-2">{k}</span>
              <span className="h-1.5 rounded-full bg-ink/70" style={{ width: `${Number(w) * 0.9}px` }} />
            </div>
          ))}
        </div>
      ),
    },
    {
      n: "04",
      title: "It gives a verdict",
      body: "Don't ship, Review, Clear, or Not checked — always with the path and the sentence behind each hop.",
      visual: (
        <div className="flex flex-wrap gap-1.5 text-[12px] font-medium">
          <span className="rounded-md bg-rx-soft px-2 py-1 text-rx">Don&apos;t ship</span>
          <span className="rounded-md bg-amber-soft px-2 py-1 text-amber-x">Review</span>
          <span className="rounded-md bg-clear-soft px-2 py-1 text-clear">Clear</span>
          <span className="rounded-md bg-paper px-2 py-1 text-ink-2">Not checked</span>
        </div>
      ),
    },
    {
      n: "05",
      title: "It ships the fix",
      body: "It rewrites only the sentence that leaned on the flagged source, then checks the answer again.",
      visual: (
        <div className="text-[13px]">
          <p className="text-ink-2 line-through decoration-rx decoration-2">…Harvard reviews the evidence.</p>
          <p className="mt-1 rounded-md bg-clear-soft px-2 py-1">…source removed — retracted May 2025.</p>
        </div>
      ),
    },
  ]
  return (
    <section id="how" className="bg-paper px-6 pb-24 text-ink sm:px-10">
      <Reveal className="mx-auto flex max-w-[1180px] flex-col gap-8">
        <div>
          <h2 className="font-display text-[48px] leading-none sm:text-[60px]">How it works</h2>
          <p className="mt-3 text-[19px] text-ink-2">What goes in, what the graph does, what comes out.</p>
        </div>
        <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {steps.map((step) => (
            <li key={step.n} className="flex flex-col gap-3 rounded-[20px] border border-hair bg-card-paper p-5">
              <p className="font-label text-[11px] text-ink-2">{step.n}</p>
              <p className="text-[19px] font-semibold leading-tight">{step.title}</p>
              <p className="text-[14px] leading-6 text-ink-2">{step.body}</p>
              <div className="mt-auto pt-2">{step.visual}</div>
            </li>
          ))}
        </ol>
        <div className="grid overflow-hidden rounded-[20px] border border-hair md:grid-cols-2">
          <div className="flex items-center gap-3 bg-clear-soft/70 px-6 py-5 text-[17px]">
            <span className="grid size-7 place-items-center rounded-full bg-clear text-white"><Check className="size-4" /></span>
            Checking the answer&apos;s own citations → <b className="text-clear">looks fine</b>
          </div>
          <div className="flex items-center gap-3 bg-rx-soft px-6 py-5 text-[17px]">
            <span className="grid size-7 place-items-center rounded-full bg-rx text-white"><X className="size-4" /></span>
            Walking the citation graph → <b className="text-rx">don&apos;t ship</b>
          </div>
        </div>
      </Reveal>
    </section>
  )
}

/* ---------- B6 · agents ---------- */
function Agents() {
  const steps = [
    { dot: "bg-rx", tool: "check_answer", tag: "don't ship", tagClass: "text-rx", line: "Walks page → review → trial in FalkorDB." },
    { dot: "bg-ink-2", tool: "explain_path", tag: "Harvard → Cochrane → Ishida", tagClass: "text-ink", line: "Shows the exact chain and the sentence behind each hop." },
    { dot: "bg-clear", tool: "rewrite_answer", tag: "fixed, clear", tagClass: "text-clear", line: "Removes the retracted source, then checks again." },
  ]
  return (
    <section className="bg-paper px-6 pb-28 text-ink sm:px-10">
      <Reveal className="mx-auto flex max-w-[1180px] flex-col gap-8">
        <div>
          <p className="font-label text-[12px] text-ink-2">Track 01 · Agents that act on connected data</p>
          <h2 className="font-display mt-2 text-[48px] leading-none sm:text-[60px]">Works where answers get made.</h2>
        </div>
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="flex flex-col rounded-[20px] border border-hair bg-card-paper p-8 lg:row-span-2">
            <h3 className="font-display text-[40px] leading-none">Your agent checks itself.</h3>
            <p className="mt-3 text-[17px] text-ink-2">The model picks the tools. The graph decides. Only tool output ships.</p>
            <ol className="mt-8 flex flex-col gap-7 border-l-2 border-hair pl-7">
              {steps.map((s) => (
                <li key={s.tool} className="relative">
                  <span className={cn("absolute -left-[37px] top-1.5 size-4 rounded-full ring-4 ring-card-paper", s.dot)} />
                  <p className="font-mono text-[17px]">
                    {s.tool} <span className="text-ink-2">·</span> <span className={s.tagClass}>{s.tag}</span>
                  </p>
                  <p className="mt-1 text-[15px] text-ink-2">{s.line}</p>
                </li>
              ))}
            </ol>
            <Link href="/app?tab=agent" className="mt-auto inline-flex w-fit items-center gap-2 pt-8 text-[16px] font-semibold underline underline-offset-4">
              Run the agent <ArrowRight className="size-4" />
            </Link>
          </div>
          <div className="rounded-[20px] border border-hair bg-card-paper p-8">
            <h3 className="font-display text-[34px] leading-none">Any agent, over MCP.</h3>
            <p className="mt-3 text-[16px] text-ink-2">Point Claude, Cursor or your own agent at the remote endpoint.</p>
            <p className="mt-5 break-all rounded-xl border border-hair bg-paper px-4 py-3 font-mono text-[13px]">{MCP_URL}</p>
            <div className="mt-4 flex flex-wrap gap-2 font-mono text-[13px]">
              {["check_answer", "what_rests_on", "recheck_affected"].map((t) => (
                <span key={t} className="rounded-lg border border-hair bg-paper px-3 py-1.5">{t}</span>
              ))}
            </div>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="rounded-[20px] border border-hair bg-card-paper p-7">
              <h3 className="font-display text-[30px] leading-none">CI blocks the PR.</h3>
              <p className="mt-3 text-[15px] text-ink-2">Fail the build when an answer rests on a retracted source.</p>
              <p className="mt-4 rounded-lg bg-paper px-3 py-2 font-mono text-[12px]">mooltrace batch --fail-on block</p>
              <span className="mt-3 inline-flex items-center gap-2 rounded-lg bg-rx-soft px-3 py-1.5 font-mono text-[13px] text-rx"><X className="size-3.5" /> exit 1</span>
            </div>
            <div className="rounded-[20px] border border-hair bg-card-paper p-7">
              <h3 className="font-display text-[30px] leading-none">Retractions arrive later.</h3>
              <p className="mt-3 text-[15px] text-ink-2">When a paper is retracted, find every shipped answer that rests on it.</p>
              <div className="mt-5 flex items-end gap-2">
                {[1, 2, 3].map((n) => (
                  <span key={n} className="paper-texture index-card relative h-12 flex-1 rounded-[4px]">
                    <span className="absolute -right-1 -top-1 size-3 rounded-full bg-rx ring-2 ring-card-paper" />
                  </span>
                ))}
              </div>
              <p className="font-label mt-3 text-[10.5px] text-ink-2">answers ← Ishida 2004</p>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  )
}

/* ---------- B7 · proof + CTA ---------- */
function Closing() {
  const stats = [
    { big: "0 → 31", unit: "of 40", label: "reviews distorted by retracted trials (BMJ 2025 answer key): a DOI check finds 0, MoolTrace reaches the trial in 31" },
    { big: "0.43 → 1.00", unit: "recall", label: "on 52 labelled answers, DOI-only check vs MoolTrace" },
    { big: "2", unit: "of 35", label: "Harvard nutrition pages rest on withdrawn or retracted research" },
  ]
  return (
    <section className="relative isolate overflow-hidden bg-night px-6 py-24 text-cream sm:px-10">
      <img src="/img/desk-night-flip.webp" alt="" aria-hidden className="absolute inset-0 -z-20 size-full object-cover object-left opacity-90" />
      <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_center,rgba(20,18,15,.78),rgba(20,18,15,.92))]" />
      <Reveal className="mx-auto flex max-w-[1180px] flex-col items-center gap-14 text-center">
        <div className="grid w-full gap-10 md:grid-cols-3">
          {stats.map((s) => (
            <div key={s.big} className="flex flex-col items-center gap-2">
              <p className="font-display text-[54px] leading-none">
                {s.big} <span className="text-[24px] text-cream-2">{s.unit}</span>
              </p>
              <p className="font-label max-w-[300px] text-[11px] leading-5 text-cream-2">{s.label}</p>
            </div>
          ))}
        </div>
        <h2 className="font-display text-[52px] leading-none sm:text-[72px]">Check the roots before you ship.</h2>
        <div className="flex flex-wrap justify-center gap-4">
          <Link href="/app?preset=harvard-vitamin-d" className="inline-flex items-center gap-3 rounded-full bg-cream px-7 py-4 text-[17px] font-semibold text-ink hover:bg-white">
            Open the demo <ArrowRight className="size-5" />
          </Link>
          <a href={REPO_URL} className="inline-flex items-center rounded-full border border-cream/60 px-7 py-4 text-[17px] text-cream hover:border-cream">
            Read the code
          </a>
        </div>
      </Reveal>
      <footer className="mx-auto mt-20 flex max-w-[1180px] flex-wrap justify-center gap-x-6 gap-y-1 border-t border-cream/15 pt-5 text-[12px] text-cream-2">
        <span>Built on FalkorDB · WeMakeDevs × FalkorDB Graph Hacks 2026</span>
        <span>Not medical advice. An Expression of Concern is not a retraction.</span>
      </footer>
    </section>
  )
}

export function Landing() {
  // Old links (/?preset=…) open the app directly.
  useEffect(() => {
    if (window.location.search.includes("preset=") || window.location.search.includes("url=")) {
      window.location.replace(`/app${window.location.search}`)
    }
  }, [])
  return (
    <div className="flex flex-1 flex-col">
      <Hero />
      <LiveDemo />
      <Finding />
      <HowItWorks />
      <Agents />
      <Closing />
    </div>
  )
}
