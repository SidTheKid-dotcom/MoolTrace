"use client"

/* eslint-disable @next/next/no-img-element */
import Link from "next/link"
import { ArrowRight, Check, Copy, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { IndexCard, Magnifier, Pin, Reveal, Stamp, Thread } from "@/components/board/board"
import { HopGraph } from "@/components/app/hop-graph"
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
        <a href="#how" className={cn("hidden py-1 sm:block", dark ? "text-cream/90 hover:text-cream" : "text-ink-2")}>How it works</a>
        <a href={REPO_URL} className={cn("hidden py-1 underline underline-offset-4 sm:block", dark ? "text-cream/90 hover:text-cream" : "text-ink-2")}>GitHub</a>
        <Link href="/app" className="rounded-full bg-cream px-6 py-3 font-semibold text-ink shadow-[0_8px_24px_-10px_rgba(0,0,0,.6)] transition hover:bg-white">
          Open the demo
        </Link>
      </nav>
    </header>
  )
}

/* ---------- B2 · hero ---------- */
type Pt = { x: number; y: number }

/** Sagging rope from pin to pin, drawn in board pixels. */
function rope(a: Pt, b: Pt, sag = 0.16): { d: string; mid: Pt } {
  const len = Math.hypot(b.x - a.x, b.y - a.y)
  const c = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 + len * sag }
  const mid = { x: 0.25 * a.x + 0.5 * c.x + 0.25 * b.x, y: 0.25 * a.y + 0.5 * c.y + 0.25 * b.y }
  return { d: `M${a.x} ${a.y} Q ${c.x} ${c.y} ${b.x} ${b.y}`, mid }
}

function HeroBoard() {
  const board = useRef<HTMLDivElement>(null)
  const cards = useRef<(HTMLDivElement | null)[]>([])
  const [geo, setGeo] = useState<{ w: number; h: number; pins: Pt[] } | null>(null)

  useEffect(() => {
    const el = board.current
    if (!el) return
    const measure = () => {
      // offsetLeft/Top ignore the rise animation's transform, so pins stay exact.
      const pins = cards.current.map((card) => (card ? { x: card.offsetLeft + card.offsetWidth / 2, y: card.offsetTop + 1 } : { x: 0, y: 0 }))
      setGeo({ w: el.clientWidth, h: el.clientHeight, pins })
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const grey = geo ? rope(geo.pins[0], geo.pins[1], 0.12) : null
  const red = geo ? rope(geo.pins[1], geo.pins[2], 0.05) : null
  const lens = Math.round(Math.min(176, (geo?.w ?? 700) * 0.27))
  const big = (geo?.w ?? 700) > 520

  return (
    <div
      ref={board}
      className="relative mx-auto aspect-[1.25] w-full max-w-[720px]"
      aria-label="Page: Harvard vitamin D, cites Review: Cochrane 2014 (Avenell), which uses data from Trial: Ishida 2004, retracted May 2025"
    >
      <div ref={(el) => { cards.current[0] = el }} className="rise absolute left-[22%] top-[3%] z-10 w-[48%] -rotate-[0.6deg]" style={{ animationDelay: "150ms" }}>
        <IndexCard size={big ? "lg" : "md"} pin={null} label="Page" title="Harvard vitamin D" />
      </div>
      <div ref={(el) => { cards.current[1] = el }} className="rise absolute left-0 top-[52%] z-10 w-[43%] rotate-[0.8deg]" style={{ animationDelay: "350ms" }}>
        <IndexCard size={big ? "lg" : "md"} pin={null} label="Review" title="Cochrane 2014 (Avenell)" />
      </div>
      <div ref={(el) => { cards.current[2] = el }} className="rise absolute right-0 top-[46%] z-10 w-[40%] rotate-[0.4deg]" style={{ animationDelay: "550ms" }}>
        <IndexCard size={big ? "lg" : "md"} pin={null} label="Trial" title="Ishida 2004" tone="red" stamp="Retracted · May 2025" stampDelay={1300} />
      </div>
      {geo && grey && red ? (
        <>
          <svg viewBox={`0 0 ${geo.w} ${geo.h}`} className="pointer-events-none absolute inset-0 z-[5] size-full overflow-visible" aria-hidden>
            <path d={grey.d} fill="none" stroke="#cbbd9f" strokeWidth="2.2" strokeLinecap="round" className="draw" pathLength={1} style={{ animationDelay: "600ms", filter: "drop-shadow(0 2px 1.5px rgba(0,0,0,.45))" }} />
          </svg>
          <svg viewBox={`0 0 ${geo.w} ${geo.h}`} className="pointer-events-none absolute inset-0 z-[15] size-full overflow-visible" aria-hidden>
            <path d={red.d} fill="none" stroke="#e0412a" strokeWidth="3" strokeLinecap="round" className="draw" pathLength={1} style={{ animationDelay: "1000ms", filter: "drop-shadow(0 3px 2px rgba(0,0,0,.4))" }} />
          </svg>
        </>
      ) : null}
      {/* pins sit on top of the rope ends */}
      {geo
        ? geo.pins.map((p, i) => (
            <img
              key={i}
              src={i === 2 ? "/img/pin-red.webp" : "/img/pin-blue.webp"}
              alt=""
              aria-hidden
              className="pointer-events-none absolute z-20 size-[20px] -translate-x-1/2 -translate-y-1/2 drop-shadow-[0_2px_2px_rgba(0,0,0,.5)]"
              style={{ left: p.x, top: p.y }}
            />
          ))
        : null}
      {red ? (
        <div className="absolute z-30" style={{ left: red.mid.x - lens * 0.34, top: red.mid.y - lens * 0.12 }}>
          <Magnifier quote="an included trial" size={lens} />
        </div>
      ) : null}
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
              <p className="flex items-start gap-2 text-cream"><X className="mt-0.5 size-4 shrink-0 text-[#ff5a43]" /> MoolTrace flags 2, and I checked both by hand.</p>
            </div>
            <div className="rise flex flex-wrap gap-4" style={{ animationDelay: "240ms" }}>
              <Link href="/app?preset=harvard-vitamin-d" className="inline-flex items-center gap-2.5 rounded-full bg-cream px-6 py-3.5 text-[16px] font-semibold text-ink transition hover:bg-white">
                Watch it catch the Harvard page <ArrowRight className="size-5" />
              </Link>
              <Link href="/app?tab=agent&preset=harvard-vitamin-d" className="inline-flex items-center rounded-full border border-cream/60 px-6 py-3.5 text-[16px] font-medium text-cream transition hover:border-cream hover:bg-cream/5">
                Run the agent on a draft
              </Link>
            </div>
            <p className="rise font-mono text-[13px] text-cream-2" style={{ animationDelay: "320ms" }}>
              Not in the graph? MoolTrace says &ldquo;not checked&rdquo;, never &ldquo;safe&rdquo;.
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
  const [shownDepth, setShownDepth] = useState(1)
  const [busy, setBusy] = useState(false)
  const [started, setStarted] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const depthRef = useRef(1)
  const auto = useRef(false)

  async function run(d: number) {
    setDepth(d)
    setBusy(true)
    try {
      const result = await checkAnswer({ ...HARVARD, depth: d })
      if (auto.current && d !== depthRef.current) return
      setShownDepth(d)
      setCheck(result)
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
        <div className="grid grid-cols-1 gap-8 rounded-[24px] border border-hair bg-card-paper p-6 shadow-[0_24px_60px_-40px_rgba(22,19,15,.5)] sm:p-9 lg:grid-cols-[90px_minmax(0,1fr)_220px]">
          <div className="flex flex-row flex-wrap gap-x-4 gap-y-2 lg:flex-col lg:gap-3" role="radiogroup" aria-label="Depth">
            {[1, 2, 3].map((d) => (
              <button
                key={d}
                type="button"
                role="radio"
                aria-checked={depth === d}
                onClick={() => {
                  auto.current = true
                  depthRef.current = d
                  void run(d)
                }}
                className="flex items-center gap-3 py-0.5 text-left font-mono text-[15px]"
              >
                <span className={cn("grid size-5 place-items-center rounded-full border-2 transition", depth === d ? "border-ink bg-ink" : "border-hair")}>
                  {depth === d ? <span className="size-1.5 rounded-full bg-cream" /> : null}
                </span>
                <span className={depth === d ? "text-ink" : "text-ink-2"}>{d} hop{d > 1 ? "s" : ""}</span>
              </button>
            ))}
            <p className="hidden pt-2 text-[12px] text-ink-2 lg:block">click to look deeper</p>
          </div>
          <div className={cn("min-w-0 transition-opacity md:min-h-[140px]", busy && "opacity-50")}>
            {check ? (
              <HopGraph check={check} depth={shownDepth} url={HARVARD.urls[0]} compact />
            ) : (
              <div className="paper-texture index-card h-[118px] max-w-[240px] rounded-[6px] px-3.5 pt-3">
                <p className="font-label text-[10.5px] text-ink-2">Page</p>
                <p className="font-display mt-1 text-[19px]">Harvard vitamin D</p>
                <p className="mt-3 font-mono text-[11px] text-ink-2">checking…</p>
              </div>
            )}
          </div>
          <div key={`${shownDepth}-${verdict}`} className="rise flex flex-col gap-3 border-t border-hair pt-6 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0" style={{ animationDelay: `${(shownDepth + 1) * 120 + 200}ms` }}>
            {verdict === "block" ? (
              <>
                <div className="flex items-center gap-3">
                  <span className="grid size-10 place-items-center rounded-xl bg-rx-soft text-xl font-bold text-rx">✕</span>
                  <span className="font-display text-[36px] leading-none">Don&apos;t ship</span>
                </div>
                <p className="text-[15px] text-ink-2">Rests on research retracted in May 2025, 2 hops down.</p>
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
        <p className="text-[17px] text-ink-2" aria-live="polite">
          {depth === 1
            ? "At 1 hop the page looks clean: nothing it cites directly is flagged."
            : depth === 2
              ? "At 2 hops the problem appears: the review the page cites uses data from a trial retracted in May 2025."
              : "At 3 hops the verdict holds: the graph has nothing further past the retracted trial."}
        </p>
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
          <h2 className="font-display mt-3 text-[40px] leading-[1.04] sm:text-[54px]">
            A citation check passes all {FIELD_SCAN.length} — MoolTrace flags {flagged.length}.
          </h2>
          <p className="mt-4 text-[20px] text-ink-2">Harvard nutrition pages that rest on withdrawn or retracted research. I checked both by hand.</p>
        </div>
        <a href="https://doi.org/10.1002/14651858.CD001364.pub5" target="_blank" rel="noreferrer" className="block rotate-[0.8deg] transition hover:rotate-0">
          <div className="paper-texture index-card relative rounded-[6px] p-7">
            <Pin className="size-6" />
            <p className="font-display text-[34px] leading-tight">Zinc for the common cold</p>
            <p className="font-label mt-2 text-[12px] text-ink-2">Review · Cochrane 2011 (Singh) · cited by Harvard zinc</p>
            <p className="mt-4 text-[15px] leading-6 text-ink-2">Withdrawn by Cochrane in April 2015 over concerns about the calculation and analysis of data.</p>
            <span className="absolute -bottom-3 right-4">
              <Stamp className="text-[20px]">Withdrawn by Cochrane · 2015</Stamp>
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
                <span aria-hidden>{i + 1}</span>
                <span className="sr-only">{page.name}{page.flag ? ", rests on withdrawn or retracted research" : ", nothing flagged"}</span>
                <span aria-hidden className="pointer-events-none absolute bottom-[calc(100%+8px)] left-1/2 z-10 hidden w-max max-w-[220px] -translate-x-1/2 rounded-lg border border-hair bg-card-paper px-3 py-1.5 text-left font-mono text-[11px] text-ink shadow-lg group-hover:block">
                  {page.name}
                  {page.flag ? " · rests on withdrawn or retracted research" : ""}
                </span>
              </Link>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-[13.5px] text-ink" data-testid="tile-legend">
            <span className="inline-flex items-center gap-2"><span className="size-4 rounded border border-rx bg-rx" aria-hidden /> Rests on withdrawn or retracted research (MoolTrace flags it)</span>
            <span className="inline-flex items-center gap-2"><span className="size-4 rounded border border-hair bg-card-paper" aria-hidden /> Nothing flagged (both checks pass)</span>
            <span className="text-ink-2">Click a tile to check that page.</span>
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
function Node({ label, title, tone = "neutral", stamp, className }: { label: string; title: string; tone?: "neutral" | "red"; stamp?: string; className?: string }) {
  return (
    <div className={cn("min-w-0 flex-1", className)}>
      <IndexCard label={label} title={title} tone={tone} pin={tone === "red" ? "red" : "blue"} stamp={stamp} stampDelay={400} />
    </div>
  )
}

function HowItWorks() {
  const steps = [
    { n: "1", title: "You give it an answer", body: "Paste a draft or the links it cites. Or let your agent call it over MCP." },
    { n: "2", title: "It builds the graph", body: "Every page gets resolved to the papers behind it (Crossref, OpenAlex, PubMed) and stored in FalkorDB as page, review and trial. Retractions and concerns hang off the papers they flag." },
    { n: "3", title: "It weighs every link", body: "A trial the review actually included counts fully. A passing mention barely counts. FalkorDB's shortest path search finds the strongest chain to a flagged paper." },
    { n: "4", title: "You get a verdict", body: "Don't ship, Review, Clear or Not checked. Always with the path and the sentence behind each hop." },
    { n: "5", title: "It fixes the answer", body: "Only the sentence that leaned on the bad source changes. Then it checks the answer again." },
  ]
  return (
    <section id="how" className="bg-paper px-6 pb-28 text-ink sm:px-10">
      <Reveal className="mx-auto flex max-w-[1180px] flex-col gap-10">
        <div>
          <h2 className="font-display text-[48px] leading-none sm:text-[64px]">How it works</h2>
          <p className="mt-3 text-[19px] text-ink-2">What goes in, what the graph does, what comes out.</p>
        </div>

        {/* the board: a flowchart drawn as pinned cards and rope */}
        <div className="relative overflow-hidden rounded-[28px] border border-[#d9ccb2] bg-[#ece2cc] p-6 shadow-[inset_0_2px_30px_rgba(120,96,60,.18)] sm:p-10">
          <div aria-hidden className="absolute inset-0 bg-[radial-gradient(rgba(90,70,40,.12)_1px,transparent_1.3px)] bg-[length:18px_18px]" />
          <div className="relative flex flex-col gap-6">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:gap-6">
              <p className="font-label w-12 shrink-0 text-[11px] text-ink-2">In</p>
              <div className="md:w-[340px]">
                <Node label="Your answer" title="“Vitamin D prevents fractures.” Source: Harvard" />
              </div>
              <p className="text-[14px] text-ink-2 md:max-w-[260px]">A draft, its links, or a call from your agent.</p>
            </div>

            <div className="relative rounded-2xl border-2 border-dashed border-ink/20 px-4 pb-6 pt-10 sm:px-8">
              <p className="font-label absolute left-6 top-3.5 text-[11px] text-ink-2">The graph · FalkorDB</p>
              <div className="flex flex-col items-stretch md:flex-row md:items-center">
                <Node label="Page" title="Harvard vitamin D" />
                <Thread vertical className="md:hidden" label="mentions 0.55" />
                <Thread className="hidden md:flex md:!w-28 lg:!w-32" label="mentions 0.55" />
                <Node label="Review" title="Cochrane 2014 (Avenell)" />
                <Thread vertical className="md:hidden" tone="red" label="uses its data 0.85" />
                <Thread className="hidden md:flex md:!w-28 lg:!w-36" tone="red" label="uses its data 0.85" />
                <Node label="Trial" title="Ishida 2004" tone="red" />
                <Thread vertical className="md:hidden" tone="red" label="flagged by" />
                <Thread className="hidden md:flex md:!w-24 lg:!w-28" tone="red" label="flagged by" />
                <Node label="Notice" title="Retracted · May 2025" tone="red" stamp="Retracted" />
              </div>
              <p className="mt-6 text-center font-mono text-[12.5px] text-ink-2">strongest chain: 0.55 × 0.85 = 0.47, found with algo.SPpaths</p>
            </div>

            <div className="flex flex-col gap-3 md:flex-row md:items-stretch md:gap-6">
              <p className="font-label w-12 shrink-0 self-center text-[11px] text-ink-2">Out</p>
              <div className="flex-1 rounded-2xl border border-rx/25 bg-card-paper p-5 shadow-sm">
                <p className="flex items-center gap-3 font-display text-[32px] leading-none">
                  <span className="grid size-8 place-items-center rounded-lg bg-rx-soft text-[16px] font-bold text-rx">✕</span>Don&apos;t ship
                </p>
                <p className="mt-2 text-[14.5px] text-ink-2">Rests on research retracted in May 2025, 2 hops down. The path and the sentence behind each hop come with it.</p>
              </div>
              <div className="flex-1 rounded-2xl border border-clear/30 bg-card-paper p-5 shadow-sm">
                <p className="font-label text-[10.5px] text-ink-2">The fix</p>
                <p className="mt-2 text-[14.5px] text-ink-2 line-through decoration-rx decoration-2">Harvard reviews the evidence at nutritionsource.hsph.harvard.edu/vitamin-d.</p>
                <p className="mt-1.5 rounded-md bg-clear-soft px-2.5 py-1.5 text-[14.5px] leading-6">An earlier version of this answer cited the Harvard Nutrition Source page &ldquo;Vitamin D&rdquo;, which cites Avenell et al. 2014, which uses data from Ishida et al. 2004, a paper that was retracted in May 2025, so that source was removed.</p>
              </div>
            </div>
          </div>
        </div>

        <ol className="grid gap-x-8 gap-y-7 sm:grid-cols-2 lg:grid-cols-5">
          {steps.map((step) => (
            <li key={step.n} className="flex flex-col gap-2">
              <span className="grid size-8 place-items-center rounded-full border border-ink/20 font-mono text-[13px]">{step.n}</span>
              <p className="text-[18px] font-semibold leading-snug">{step.title}</p>
              <p className="text-[15.5px] leading-[1.65] text-[#4a443b]">{step.body}</p>
            </li>
          ))}
        </ol>

        <div className="grid overflow-hidden rounded-[20px] border border-hair md:grid-cols-2">
          <div className="flex items-center gap-3 bg-clear-soft/70 px-6 py-5 text-[17px]">
            <span className="grid size-7 place-items-center rounded-full bg-clear text-white"><Check className="size-4" /></span>
            Checking only the answer&apos;s own citations: <b className="text-clear">looks fine</b>
          </div>
          <div className="flex items-center gap-3 bg-rx-soft px-6 py-5 text-[17px]">
            <span className="grid size-7 place-items-center rounded-full bg-rx text-white"><X className="size-4" /></span>
            Walking the citation graph: <b className="text-rx">don&apos;t ship</b>
          </div>
        </div>
      </Reveal>
    </section>
  )
}

function CopyCode({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="mt-5 flex items-stretch overflow-hidden rounded-xl border border-hair bg-paper">
      <code className="min-w-0 flex-1 break-all px-4 py-3 font-mono text-[13px]">{text}</code>
      <button
        type="button"
        onClick={() => {
          void navigator.clipboard?.writeText(text)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        }}
        className="inline-flex shrink-0 items-center gap-1.5 border-l border-hair px-4 text-[13px] font-semibold hover:bg-card-paper active:scale-95"
        aria-label="Copy the MCP URL"
      >
        {copied ? <Check className="size-4 text-clear" /> : <Copy className="size-4" />}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
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
            <div className="mt-8 grid gap-3 text-[14px] leading-6 sm:grid-cols-2">
              <div className="min-w-0 rounded-xl border border-rx/25 bg-rx-soft p-4 [overflow-wrap:anywhere]">
                <p className="mb-1 text-[11.5px] text-ink-2">Without MoolTrace · ships as written</p>
                Vitamin D helps prevent fractures in older adults. Harvard reviews the evidence at nutritionsource.hsph.harvard.edu/vitamin-d.
              </div>
              <div className="min-w-0 rounded-xl border border-clear/30 bg-clear-soft p-4 [overflow-wrap:anywhere]">
                <p className="mb-1 text-[11.5px] text-ink-2">With MoolTrace · checked again: clear</p>
                Vitamin D helps prevent fractures in older adults (no checked source remains for this claim). An earlier version of this answer cited the Harvard Nutrition Source page &ldquo;Vitamin D&rdquo;, which cites Avenell et al. 2014, which uses data from Ishida et al. 2004, a paper that was retracted in May 2025, so that source was removed.
              </div>
            </div>
            <Link href="/app?tab=agent&preset=harvard-vitamin-d" className="mt-8 inline-flex w-fit items-center gap-2 text-[16px] font-semibold underline underline-offset-4">
              Run the agent on this draft <ArrowRight className="size-4" />
            </Link>
          </div>
          <div className="rounded-[20px] border border-hair bg-card-paper p-8">
            <h3 className="font-display text-[34px] leading-none">Any agent, over MCP.</h3>
            <p className="mt-3 text-[16px] text-ink-2">Point Claude, Cursor or your own agent at the remote endpoint.</p>
            <CopyCode text={MCP_URL} />
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
              <p className="mt-4 rounded-lg bg-paper px-3 py-2 font-mono text-[12px] leading-5">Trial · Ishida 2004 · Retracted<br />← Review · Cochrane 2014 (Avenell)<br />← Page · Harvard vitamin D<br />← stored answers citing it</p>
              <Link href="/app?tab=alert" className="mt-3 inline-flex text-[14px] font-semibold underline underline-offset-4">Try the retraction alert →</Link>
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
      <footer className="mx-auto mt-20 flex max-w-[1180px] flex-wrap justify-center gap-x-6 gap-y-1 border-t border-cream/25 pt-5 text-[12.5px] text-cream">
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
      <main className="flex flex-1 flex-col">
        <Hero />
        <LiveDemo />
        <Finding />
        <HowItWorks />
        <Agents />
        <Closing />
      </main>
    </div>
  )
}
