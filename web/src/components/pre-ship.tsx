"use client"

import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Textarea } from "@/components/ui/textarea"
import { PathDiagram } from "@/components/path-diagram"
import { decidingReason, hopTrailLine } from "@/lib/path-diagram"
import { stepLabel } from "@/lib/step-label"

type Step = { kind?: string; doi?: string | null; title?: string | null; url?: string | null; year?: number | null }
type Reason = {
  code?: string
  root_doi?: string | null
  root_title?: string | null
  notice_doi?: string | null
  notice_type?: string | null
  notice_label?: string | null
  notice_date?: string | null
  notice_source?: string | null
  hops?: number | null
  steps?: Step[]
  sentence?: string | null
  reliance?: string | null
  weight?: number | null
  evidence_from?: string | null
  cypher?: string
  path_score?: number | null
  sp_cost?: number | null
  hops_evidence?: {
    weight?: number | null
    reliance?: string | null
    sentence?: string | null
    evidence_from?: string | null
    source_url?: string | null
    fetched_at?: string | null
    content_hash?: string | null
  }[]
  label?: string | null
}
type Impact = {
  notice_doi?: string | null
  notice_type?: string | null
  root_doi?: string | null
  answer_count?: number
  counted_answer_count?: number
  engines?: string[]
  cypher?: string
  summary?: string
}
type Algorithm = {
  name?: string
  weight_prop?: string
  cost_formula?: string
  strength?: number | null
  explanation?: string
  cypher?: string
}
type WhyHop = {
  relation?: string
  weight?: number | null
  sentence?: string | null
  sentence_snippet?: string | null
  source_url?: string | null
  fetched_at?: string | null
}
type WhyGraph = {
  title?: string
  cypher?: string
  path?: { nodes?: string[]; hops?: WhyHop[]; readable?: string }
  without_graph?: { line?: string; notice_count?: number; decision?: string; dois?: string[] }
  with_graph?: { line?: string; depth?: number; decision?: string; notice_doi?: string | null }
  contrast?: string
  live_sppaths?: { strength?: number | null; root_doi?: string | null; hops?: string[] } | null
}
type Check = {
  decision: "pass" | "warn" | "block"
  exit_code?: number
  summary: string
  pitch?: string | null
  reasons: Reason[]
  discounted?: Reason[]
  independent_source_count?: number
  weight_floor?: number
  path_score_floor?: number
  path_rule?: string
  coverage?: string
  not_shown?: string
  cypher?: string
  elapsed_ms?: number
  limits?: string
  errors?: string[]
  context_notes?: string[]
  impact?: Impact | null
  algorithm?: Algorithm | null
  notices_checked_ago?: string | null
  why_graph?: WhyGraph | null
}
type Rewrite = {
  rewritten?: boolean
  method?: string | null
  before?: string
  text?: string
  urls?: string[]
  recheck?: Check
}

const PRESETS = [
  {
    id: "harvard-vitamin-d",
    label: "Harvard vitamin D (block)",
    hint: "Page mention → Avenell 2014 uses_data_or_method 0.85 → Ishida 2004 retraction. Depth 1 PASS (0 notice paths); depth 2/3 BLOCK.",
    engine: "nutrition-coach",
    depth: 2,
    text: "",
    urls: ["https://nutritionsource.hsph.harvard.edu/vitamin-d/"],
  },
  {
    id: "olive-oil",
    label: "Healthline olive oil (warn)",
    hint: "Same question: depth 1 PASS (0 notice paths), depth 3 WARN (mention × mention to Estruch 2013; the review did not appear to rely on it)",
    engine: "nutrition-coach",
    depth: 3,
    text: "",
    urls: ["https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil"],
  },
  {
    id: "healthline",
    label: "Healthline cinnamon (warn)",
    hint: "URL-only page, counted 2-hop to an Expression of Concern, not a retraction",
    engine: "nutrition-coach",
    depth: 2,
    text: "",
    urls: ["https://www.healthline.com/nutrition/cinnamon-and-diabetes"],
  },
  {
    id: "clean",
    label: "Clean study (pass)",
    hint: "No flagged ancestor at depth 2; not shown beyond",
    engine: "clean-check",
    depth: 2,
    text: "10.1016/j.jsps.2015.03.013",
    urls: [] as string[],
  },
  {
    id: "not-in-graph",
    label: "Not in the graph",
    hint: "NHS how-to page with no scholarly citations. The graph cannot connect it to a study.",
    engine: "nutrition-coach",
    depth: 2,
    text: "",
    urls: ["https://www.nhs.uk/live-well/best-way-to-wash-your-hands/"],
  },
]

const HARVARD_REWRITE_DRAFT =
  "Hand hygiene is discussed separately. A nutrition coach cites https://nutritionsource.hsph.harvard.edu/vitamin-d/."
const OLIVE_OIL_REWRITE_DRAFT =
  "Vitamin D status is discussed separately. A nutrition coach cites https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil."

const DEPTHS = [1, 2, 3] as const
const LIVE_HOSTS = [
  "healthline.com",
  "everydayhealth.com",
  "verywellhealth.com",
  "medicalnewstoday.com",
  "webmd.com",
  "pubmed.ncbi.nlm.nih.gov",
  "doi.org",
  "nutritionsource.hsph.harvard.edu",
]
const LIVE_MS = 120_000

function parseUrls(raw: string): string[] {
  return raw.split(/\s+/).map((item) => item.trim()).filter(Boolean)
}

function liveHostAllowed(url: string): boolean {
  try {
    const host = new URL(url).hostname.replace(/^www\./i, "").toLowerCase()
    return LIVE_HOSTS.includes(host)
  } catch {
    return false
  }
}

function isPresetBody(engine: string, text: string, listed: string[]): boolean {
  return PRESETS.some(
    (preset) =>
      preset.engine === engine &&
      preset.text === text &&
      preset.urls.length === listed.length &&
      preset.urls.every((url, index) => url === listed[index]),
  )
}

function isLivePaste(engine: string, text: string, listed: string[]): boolean {
  if (isPresetBody(engine, text, listed)) return false
  return listed.length > 0 && listed.every(liveHostAllowed)
}

function decisionVariant(decision: string): "default" | "secondary" | "destructive" {
  if (decision === "block") return "destructive"
  if (decision === "warn") return "secondary"
  return "default"
}

function plainVerdict(result: Check): string {
  const code = result.exit_code
  const kind = (result.reasons || []).find((item) => item.code)?.code
  if (result.decision === "block") {
    return `BLOCK (exit ${code ?? 1}) — your answer rests on a retracted study`
  }
  if (result.decision === "pass") {
    return `PASS (exit ${code ?? 0}) — no counted path to a flagged study within this depth. Pass is not a medical-accuracy check.`
  }
  if (kind === "expression_of_concern") {
    return `WARN (exit ${code ?? 2}) — your answer rests on a study flagged with an Expression of Concern`
  }
  if (kind === "unverified") {
    return `WARN (exit ${code ?? 2}) — a cited flagged study has unverified reliance`
  }
  if (kind === "no_sources") {
    return `WARN (exit ${code ?? 2}) — no verifiable citation or source was provided`
  }
  if (kind === "not_in_graph") {
    return `WARN (exit ${code ?? 2}) — nothing in the graph connects this answer to a study`
  }
  return result.summary
}

function ResultCard({
  result,
  onRewrite,
  rewriting,
}: {
  result: Check
  onRewrite?: () => void
  rewriting?: boolean
}) {
  const counted = (result.reasons || []).filter((reason) => reason.code && reason.code !== "incomplete")
  const deciding = decidingReason(counted)
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={decisionVariant(result.decision)}>{result.decision}</Badge>
          <span className="text-xs text-muted-foreground">
            {result.independent_source_count ?? 0} independent source
            {(result.independent_source_count ?? 0) === 1 ? "" : "s"}
            {result.algorithm?.explanation ? ` · ${result.algorithm.explanation}` : ""}
            {result.coverage ? ` · ${result.coverage.replace("_", " ")}` : ""}
            {result.elapsed_ms != null ? ` · ${result.elapsed_ms} ms` : ""}
          </span>
        </div>
        <CardTitle className="text-lg leading-snug sm:text-xl">{plainVerdict(result)}</CardTitle>
        <CardDescription>{result.summary}</CardDescription>
        {result.coverage && result.coverage.startsWith("expanded ") ? (
          <CardDescription>Coverage: {result.coverage}</CardDescription>
        ) : null}
        {result.pitch ? <CardDescription>{result.pitch}</CardDescription> : null}
        {result.notices_checked_ago ? (
          <CardDescription>Notices checked {result.notices_checked_ago}.</CardDescription>
        ) : null}
        {result.impact?.summary ? (
          <CardDescription>{result.impact.summary}</CardDescription>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {result.why_graph ? (
          <section
            data-testid="why-the-graph-decided"
            className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs leading-5"
          >
            {/* Contrast line is built from the run / recorded without_graph, never hard-coded. */}
            <p className="font-medium">{result.why_graph.title || "Why the graph decided"}</p>
            {result.why_graph.cypher ? (
              <pre className="mt-1 max-h-20 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-4">
                {result.why_graph.cypher}
              </pre>
            ) : null}
            {result.why_graph.path?.readable ? (
              <p className="mt-1">{result.why_graph.path.readable}</p>
            ) : null}
            {(result.why_graph.path?.hops || []).map((hop, index) => (
              <p key={`${hop.relation}-${index}`} className="mt-0.5 text-muted-foreground">
                {hop.relation}
                {hop.weight != null ? ` ${hop.weight}` : ""}
                {hop.sentence_snippet || hop.sentence
                  ? ` — ${hop.sentence_snippet || hop.sentence}`
                  : ""}
                {hop.source_url || hop.fetched_at
                  ? ` (${[hop.source_url, hop.fetched_at].filter(Boolean).join(" · ")})`
                  : ""}
              </p>
            ))}
            {result.why_graph.live_sppaths?.strength != null ? (
              <p className="mt-1 text-muted-foreground">
                Live SPpaths also returned {result.why_graph.live_sppaths.strength}
                {result.why_graph.live_sppaths.hops?.length
                  ? ` (${result.why_graph.live_sppaths.hops.join(" × ")} → ${result.why_graph.live_sppaths.root_doi})`
                  : ""}
              </p>
            ) : null}
            <p className="mt-1" data-testid="without-the-graph">
              {result.why_graph.contrast ||
                [result.why_graph.without_graph?.line, result.why_graph.with_graph?.line]
                  .filter(Boolean)
                  .join("  |  ")}
            </p>
          </section>
        ) : null}
        {deciding ? (
          <PathDiagram
            key={`${deciding.notice_doi || ""}-${deciding.steps?.[0]?.url || deciding.steps?.[0]?.doi || ""}`}
            reason={deciding}
          />
        ) : null}
        {counted.length === 0 ? (
          <p className="text-sm leading-6 text-muted-foreground">{result.limits}</p>
        ) : null}
        {result.why_graph
          ? null
          : counted.map((reason, index) => (
          <article key={`${reason.notice_doi}-${reason.root_doi}-${index}`} className="flex flex-col gap-3">
            {index > 0 ? <Separator /> : null}
            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span
                title={
                  reason.code === "expression_of_concern"
                    ? "An Expression of Concern is a publisher notice that a paper's reliability is under review. It is not a retraction."
                    : reason.code === "retraction"
                      ? "The publisher withdrew the paper. A counted path to one blocks."
                      : "Publisher notice on the root study."
                }
              >
                {reason.label || reason.notice_type || reason.code}
              </span>
              {reason.notice_doi ? <span>{reason.notice_doi}</span> : null}
              {reason.notice_date ? <span>{reason.notice_date}</span> : null}
              {reason.reliance ? (
                <span>
                  {reason.reliance} · weight {reason.weight}
                </span>
              ) : null}
              {reason.evidence_from ? <span>{reason.evidence_from}</span> : null}
            </div>
            {reason.sentence ? (
              <blockquote className="border-l-2 border-primary pl-3 text-sm leading-6">
                {reason.sentence}
              </blockquote>
            ) : null}
            <ol className="flex flex-col gap-1 text-sm sm:flex-row sm:flex-wrap sm:items-center sm:gap-2">
              {(reason.steps || []).map((step, stepIndex) => (
                <li key={`${stepLabel(step)}-${stepIndex}`} className="flex items-center gap-2">
                  {stepIndex > 0 ? <span className="text-muted-foreground">→</span> : null}
                  <span className="break-all rounded-md bg-muted px-2 py-1">{stepLabel(step)}</span>
                </li>
              ))}
            </ol>
            {reason.hops_evidence && reason.hops_evidence.length > 0 ? (
              <ol className="flex flex-col gap-2 text-sm">
                {reason.hops_evidence.map((hop, hopIndex) => (
                  <li key={`${hop.reliance}-${hopIndex}`} className="rounded-md bg-muted px-3 py-2">
                    <p className="text-xs text-muted-foreground">
                      hop {hopIndex + 1}
                      {hop.reliance ? ` · ${hop.reliance}` : ""}
                      {hop.weight != null ? ` · weight ${hop.weight}` : ""}
                      {hop.evidence_from ? ` · ${hop.evidence_from}` : ""}
                    </p>
                    {hopTrailLine(hop) ? (
                      <p className="mt-1 break-all font-mono text-[11px] leading-5 text-muted-foreground">
                        {hopTrailLine(hop)}
                      </p>
                    ) : null}
                    {hop.sentence ? (
                      <p className="mt-1 leading-6">{hop.sentence}</p>
                    ) : (
                      <p className="mt-1 text-muted-foreground">Reliance unverified on this hop.</p>
                    )}
                  </li>
                ))}
                <li className="text-xs text-muted-foreground">
                  path score {reason.path_score ?? "—"}
                  {reason.sp_cost != null ? ` · SPpaths cost ${reason.sp_cost}` : ""}
                </li>
              </ol>
            ) : null}
          </article>
        ))}
        {(result.discounted || []).length > 0 ? (
          <p className="text-sm text-muted-foreground">
            {result.discounted?.length} citation path
            {result.discounted?.length === 1 ? "" : "s"} reached a notice only as background,
            a scholarly dispute, or a path score below the floor, so{" "}
            {result.discounted?.length === 1 ? "it does" : "they do"} not change this check.
            Coverage is not shown beyond the requested depth.
          </p>
        ) : null}
        {result.context_notes && result.context_notes.length > 0 ? (
          <p className="text-xs text-muted-foreground">{result.context_notes.join(" ")}</p>
        ) : null}
        {onRewrite && result.decision !== "pass" ? (
          <Button type="button" disabled={rewriting} onClick={onRewrite}>
            {rewriting ? "Rewriting and rechecking…" : "Rewrite and recheck"}
          </Button>
        ) : null}
        {result.cypher && !result.why_graph ? (
          <div className="flex flex-col gap-2">
            <p
              className="text-xs text-muted-foreground"
              title="algo.SPpaths walks RESTS_ON with cost −ln(weight). Path strength is the product of hop weights and is the verdict."
            >
              {result.algorithm?.explanation ||
                "Decided by: algo.SPpaths"}
            </p>
            <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs leading-5">
              {result.algorithm?.cypher || result.cypher}
            </pre>
          </div>
        ) : null}
        {result.impact?.cypher ? (
          <div className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">Reverse impact Cypher (what rests on this notice).</p>
            <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs leading-5">{result.impact.cypher}</pre>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

export function PreShip() {
  const [text, setText] = useState(PRESETS[0].text)
  const [urls, setUrls] = useState(PRESETS[0].urls.join("\n"))
  const [engine, setEngine] = useState(PRESETS[0].engine)
  const [depth, setDepth] = useState(PRESETS[0].depth)
  const [presetId, setPresetId] = useState(PRESETS[0].id)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [result, setResult] = useState<Check | null>(null)
  const [byDepth, setByDepth] = useState<Partial<Record<number, Check>>>({})
  const [rewrite, setRewrite] = useState<Rewrite | null>(null)
  const [rewriting, setRewriting] = useState(false)
  const listed = parseUrls(urls)
  const liveRunning = loading && isLivePaste(engine, text, listed)

  useEffect(() => {
    if (typeof window === "undefined") return
    const params = new URLSearchParams(window.location.search)
    const id = params.get("preset") || PRESETS[0].id
    const requested = Number(params.get("depth"))
    const startDepth = DEPTHS.includes(requested as (typeof DEPTHS)[number])
      ? requested
      : undefined
    if (PRESETS.some((item) => item.id === id)) {
      applyPreset(id, startDepth)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function syncQuery(id: string, nextDepth: number) {
    if (typeof window === "undefined") return
    const url = new URL(window.location.href)
    url.searchParams.set("preset", id)
    url.searchParams.set("depth", String(nextDepth))
    window.history.replaceState({}, "", url)
  }

  async function fetchCheck(body: { text: string; urls: string[]; engine: string; depth: number }) {
    const response = await fetch("/nw/check-answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(LIVE_MS),
    })
    if (!response.ok) {
      const detail = await response.text()
      if (response.status === 429) {
        throw new Error("A live check is already running, or this IP hit the rate limit. Try a preset, or wait about 60 s.")
      }
      if (response.status === 504) {
        throw new Error("Live check hit the 120 s limit. Try a preset or a shorter page.")
      }
      if (response.status === 413) {
        throw new Error("Draft or URL list is too large for the public demo.")
      }
      if (response.status === 400 && /allow/i.test(detail)) {
        throw new Error(
          `Live checks only run for ${LIVE_HOSTS.join(", ")}. Try a preset or paste one of those URLs.`,
        )
      }
      throw new Error(`The check returned HTTP ${response.status}.`)
    }
    return (await response.json()) as Check
  }

  async function runCheck(body: { text: string; urls: string[]; engine: string; depth: number }) {
    setLoading(true)
    setError("")
    setRewrite(null)
    try {
      const payload = await fetchCheck(body)
      setResult(payload)
      setByDepth((current) => ({ ...current, [body.depth]: payload }))
    } catch (exc) {
      setResult(null)
      setError(exc instanceof Error ? exc.message : "The pre-ship check did not finish.")
    } finally {
      setLoading(false)
    }
  }

  async function runRewrite() {
    setRewriting(true)
    setError("")
    const listed = urls.split(/\s+/).map((item) => item.trim()).filter(Boolean)
    const recordedDraft =
      presetId === "harvard-vitamin-d" && !text.trim()
        ? HARVARD_REWRITE_DRAFT
        : presetId === "olive-oil" && !text.trim()
          ? OLIVE_OIL_REWRITE_DRAFT
          : text
    if (recordedDraft !== text) setText(recordedDraft)
    try {
      const response = await fetch("/nw/rewrite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: recordedDraft,
          urls: listed,
          engine,
          depth,
        }),
      })
      if (!response.ok) {
        throw new Error(`The rewrite returned HTTP ${response.status}.`)
      }
      const payload = (await response.json()) as Rewrite
      setRewrite(payload)
      if (payload.urls) setUrls(payload.urls.join("\n"))
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The rewrite did not finish.")
    } finally {
      setRewriting(false)
    }
  }

  async function applyPreset(id: string, startDepth?: number) {
    const preset = PRESETS.find((item) => item.id === id)
    if (!preset) return
    const nextDepth = startDepth ?? preset.depth
    setText(preset.text)
    setUrls(preset.urls.join("\n"))
    setEngine(preset.engine)
    setDepth(nextDepth)
    setPresetId(preset.id)
    setByDepth({})
    setRewrite(null)
    setLoading(true)
    setError("")
    syncQuery(preset.id, nextDepth)
    const body = {
      text: preset.text,
      urls: preset.urls,
      engine: preset.engine,
    }
    try {
      const first = await fetchCheck({ ...body, depth: nextDepth })
      setByDepth({ [nextDepth]: first })
      setResult(first)
      setLoading(false)
      const rest = DEPTHS.filter((item) => item !== nextDepth)
      const payloads = await Promise.all(
        rest.map((item) => fetchCheck({ ...body, depth: item })),
      )
      setByDepth(() => {
        const cached: Partial<Record<number, Check>> = { [nextDepth]: first }
        rest.forEach((item, index) => {
          cached[item] = payloads[index]
        })
        return cached
      })
    } catch (exc) {
      setResult(null)
      setError(exc instanceof Error ? exc.message : "The pre-ship check did not finish.")
      setLoading(false)
    }
  }

  function selectDepth(nextDepth: number) {
    const bound = Math.min(3, Math.max(1, nextDepth))
    setDepth(bound)
    setRewrite(null)
    syncQuery(presetId, bound)
    const cached = byDepth[bound]
    if (cached) {
      setResult(cached)
      return
    }
    void runCheck({
      text,
      urls: urls.split(/\s+/).map((item) => item.trim()).filter(Boolean),
      engine,
      depth: bound,
    })
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-3 px-4 py-4 sm:px-6">
      <header className="flex flex-col gap-1">
        <p className="text-sm font-medium tracking-wide text-primary">MoolTrace</p>
        <h1 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
          Is your AI&apos;s answer built on a flagged study?
        </h1>
      </header>

      <div className="flex flex-wrap gap-1.5" data-testid="preset-row">
        {PRESETS.map((preset) => (
          <Button
            key={preset.id}
            type="button"
            size="sm"
            variant={presetId === preset.id ? "default" : "outline"}
            disabled={loading}
            onClick={() => applyPreset(preset.id)}
          >
            <span title={preset.hint}>{preset.label}</span>
          </Button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>Depth</span>
          <div
            data-testid="depth-toggle"
            role="radiogroup"
            aria-label="Depth"
            className="inline-flex rounded-lg border border-input bg-muted p-[3px]"
          >
            {DEPTHS.map((item) => (
              <Button
                key={item}
                type="button"
                size="sm"
                data-depth={item}
                role="radio"
                aria-checked={depth === item}
                variant={depth === item ? "default" : "ghost"}
                disabled={loading}
                onClick={() => selectDepth(item)}
              >
                {item}
              </Button>
            ))}
          </div>
        </div>
        {presetId === "harvard-vitamin-d" && depth !== 1 ? (
          <button
            type="button"
            data-testid="try-depth-1"
            className="text-sm font-medium text-primary underline-offset-4 hover:underline"
            disabled={loading}
            onClick={() => selectDepth(1)}
          >
            Try depth 1 — same page, 0 notice paths, PASS
          </button>
        ) : null}
      </div>

      {result ? (
        <div data-testid="verdict-first">
          <ResultCard result={result} onRewrite={() => void runRewrite()} rewriting={rewriting} />
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Draft answer</CardTitle>
          <CardDescription>
            Paste the draft and the URLs or DOIs it cites. Live URL checks are only for{" "}
            {LIVE_HOSTS.join(", ")}. This does not give medical advice, and it does not say
            the draft is wrong.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Textarea
            value={text}
            onChange={(event) => {
              setPresetId("")
              setText(event.target.value)
            }}
            placeholder="Paste a draft answer, a DOI, or both."
            className={result ? "min-h-16" : "min-h-36"}
          />
          <Textarea
            value={urls}
            onChange={(event) => {
              setPresetId("")
              setUrls(event.target.value)
            }}
            placeholder="One cited URL or DOI per line"
            className="min-h-20"
          />
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              Engine
              <input
                value={engine}
                onChange={(event) => setEngine(event.target.value)}
                className="h-8 rounded-lg border border-input bg-card px-2 text-sm text-foreground"
              />
            </label>
            <Button
              type="button"
              disabled={loading || (!text.trim() && !urls.trim())}
              onClick={() =>
                void runCheck({
                  text,
                  urls: listed,
                  engine,
                  depth,
                })
              }
            >
              {liveRunning
                ? "Running live, about 60 s…"
                : loading
                  ? "Fetching pages and checking notices…"
                  : "Check before shipping"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error ? (
        <Card>
          <CardHeader>
            <CardTitle>The check did not finish</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {!result && !error && !loading ? (
        <Card>
          <CardHeader>
            <CardTitle>Nothing checked yet</CardTitle>
            <CardDescription>
              Five presets: Harvard vitamin D (block), Healthline olive oil (warn), Healthline cinnamon (warn), Clean study
              (pass), and Not in the graph (NHS how-to with no scholarly citations). Toggle depth 1 /
              2 / 3 on the same question. Olive oil depth 1 is PASS (0 notice paths); depth 3 is WARN
              (mention × mention; the review did not appear to rely on Estruch 2013). Harvard vitamin D is BLOCK at depth 2/3 (uses_data_or_method into Ishida 2004). Not in the graph says so plainly: nothing connects that page to a study.
              This is not proof it is safe; the source may not be modelled. Coverage is expanded X of
              Y cited works on every verdict. You can also paste your own URL from healthline.com,
              everydayhealth.com, verywellhealth.com, medicalnewstoday.com, webmd.com,
              pubmed.ncbi.nlm.nih.gov, doi.org, or nutritionsource.hsph.harvard.edu. That check runs live, about 60 s.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {liveRunning ? (
        <p className="text-sm text-muted-foreground" role="status" data-testid="live-running">
          Running live, about 60 s. One live check at a time on this host. Presets stay instant.
        </p>
      ) : loading && !result ? (
        <p className="text-sm text-muted-foreground" role="status">
          Fetching the cited page, walking reviews, then checking publisher notices…
        </p>
      ) : null}

      {presetId === "not-in-graph" ? (
        <p className="text-sm leading-6 text-muted-foreground" data-testid="not-in-graph-note">
          Nothing in the graph connects this answer to a study. This is not proof it is safe; the
          source may not be modelled. Coverage: expanded 0 of 0 cited works.
        </p>
      ) : null}

      {presetId === "harvard-vitamin-d" && !result ? (
        <p className="text-sm leading-6 text-muted-foreground" data-testid="block-hero">
          Harvard T.H. Chan Nutrition Source vitamin D. Depth 1: PASS (0 notice paths). Depth 2/3:
          BLOCK — page mention 0.55 → Avenell 2014 Cochrane uses_data_or_method 0.85 → Ishida 2004
          retraction (same DOI as the article, 2004-10-15). The review called Ishida an included trial.
          This does not say vitamin D works or does not.
        </p>
      ) : null}

      {presetId === "olive-oil" ? (
        <p className="text-sm leading-6 text-muted-foreground" data-testid="depth-contrast">
          Same olive-oil question. Depth 1: PASS (0 notice paths). Depth 3: WARN — page mention 0.55
          → Schwingshackl 2014 mention 0.55 → Estruch 2013 retraction 10.1056/nejmc1806491. Both hops
          are mention; the review did not appear to rely on the trial. The 2013 trial was retracted
          and republished in 2018 after re-analysis.
        </p>
      ) : null}

      {rewrite?.text ? (
        <Card data-testid="rewritten-draft">
          <CardHeader>
            <CardTitle>Rewritten draft</CardTitle>
            <CardDescription>
              Template rewrite. Only flagged sentences changed. Untouched
              sentences stayed the same, then the check ran again.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {rewrite.before ? (
              <div>
                <p className="text-xs font-medium text-muted-foreground">Before</p>
                <p className="text-sm leading-6" data-testid="rewrite-before">
                  {rewrite.before}
                </p>
              </div>
            ) : null}
            <div>
              <p className="text-xs font-medium text-muted-foreground">After</p>
              <p className="text-sm leading-6" data-testid="rewrite-after">
                {rewrite.text}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {rewrite?.recheck ? <ResultCard result={rewrite.recheck} /> : null}

      <footer className="text-xs leading-5 text-muted-foreground">
        An Expression of Concern is not a retraction. BLOCK requires the hop into a retracted work to
        be included, relies, or uses_data_or_method. The Harvard vitamin D path reaches Ishida 2004
        that way. The olive-oil path reaches Estruch 2013 only as a mention, so it is WARN (notice
        10.1056/nejmc1806491; retracted and republished in 2018). Khan 2003 carries an Expression of
        Concern. This demo does not say a food or a medicine works or does not work.
        Citation-context sentences may include{" "}
        <a className="underline" href="https://www.semanticscholar.org/">
          Semantic Scholar
        </a>{" "}
        data.
      </footer>
    </main>
  )
}
