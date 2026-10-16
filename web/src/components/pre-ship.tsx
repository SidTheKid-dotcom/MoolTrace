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
}
type Rewrite = {
  rewritten?: boolean
  method?: string | null
  text?: string
  urls?: string[]
  recheck?: Check
}

const PRESETS = [
  {
    id: "olive-oil",
    label: "Healthline olive oil (block)",
    hint: "URL-only page → Schwingshackl 2014 review → Estruch 2013 retraction (mention × mention)",
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
]

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
            {(result.independent_source_count ?? 0) === 1 ? "" : "s"} at{" "}
            <span title="Reliance weight: how strongly this hop uses the next work. included is 1.0; background is 0.2.">
              weight ≥ {result.weight_floor ?? 0.5}
            </span>
            {result.path_rule ? ` · ${result.path_rule}` : ""}
            {result.coverage ? ` · ${result.coverage.replace("_", " ")}` : ""}
            {result.elapsed_ms != null ? ` · ${result.elapsed_ms} ms` : ""}
          </span>
        </div>
        <CardTitle className="text-xl leading-snug">{plainVerdict(result)}</CardTitle>
        <CardDescription>{result.summary}</CardDescription>
        {result.pitch ? <CardDescription>{result.pitch}</CardDescription> : null}
        {result.notices_checked_ago ? (
          <CardDescription>Notices checked {result.notices_checked_ago}.</CardDescription>
        ) : null}
        {result.impact?.summary ? (
          <CardDescription>{result.impact.summary}</CardDescription>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {deciding ? (
          <PathDiagram
            key={`${deciding.notice_doi || ""}-${deciding.steps?.[0]?.url || deciding.steps?.[0]?.doi || ""}`}
            reason={deciding}
          />
        ) : null}
        {counted.length === 0 ? (
          <p className="text-sm leading-6 text-muted-foreground">{result.limits}</p>
        ) : null}
        {counted.map((reason, index) => (
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
        {result.cypher ? (
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
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [result, setResult] = useState<Check | null>(null)
  const [rewrite, setRewrite] = useState<Rewrite | null>(null)
  const [rewriting, setRewriting] = useState(false)

  useEffect(() => {
    if (typeof window === "undefined") return
    const id = new URLSearchParams(window.location.search).get("preset")
    if (id === "olive-oil" || id === "healthline" || id === "clean") {
      applyPreset(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function runCheck(body: { text: string; urls: string[]; engine: string; depth: number }) {
    setLoading(true)
    setError("")
    setRewrite(null)
    try {
      const response = await fetch("/nw/check-answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      if (!response.ok) {
        throw new Error(`The check returned HTTP ${response.status}.`)
      }
      setResult((await response.json()) as Check)
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
    try {
      const response = await fetch("/nw/rewrite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          urls: urls.split(/\s+/).map((item) => item.trim()).filter(Boolean),
          engine,
          depth,
        }),
      })
      if (!response.ok) {
        throw new Error(`The rewrite returned HTTP ${response.status}.`)
      }
      const payload = (await response.json()) as Rewrite
      setRewrite(payload)
      if (payload.text) setText(payload.text)
      if (payload.urls) setUrls(payload.urls.join("\n"))
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The rewrite did not finish.")
    } finally {
      setRewriting(false)
    }
  }

  function applyPreset(id: string) {
    const preset = PRESETS.find((item) => item.id === id)
    if (!preset) return
    setText(preset.text)
    setUrls(preset.urls.join("\n"))
    setEngine(preset.engine)
    setDepth(preset.depth)
    void runCheck({ text: preset.text, urls: preset.urls, engine: preset.engine, depth: preset.depth })
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 py-8 sm:px-6 sm:py-12">
      <header className="flex flex-col gap-3">
        <p className="text-sm font-medium tracking-wide text-primary">MoolTrace</p>
        <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
          Is your AI&apos;s answer built on a flagged study?
        </h1>
        <p className="text-base leading-7 text-muted-foreground">
          Paste an answer and the links it cites. We follow every citation — page → review → trial —
          and show you the exact path to any retraction or Expression of Concern.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {PRESETS.map((preset) => (
          <Button
            key={preset.id}
            type="button"
            variant="outline"
            disabled={loading}
            onClick={() => applyPreset(preset.id)}
          >
            <span title={preset.hint}>{preset.label}</span>
          </Button>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Draft answer</CardTitle>
          <CardDescription>
            Paste the draft and the URLs or DOIs it cites. This does not give medical advice,
            and it does not say the draft is wrong.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Paste a draft answer, a DOI, or both."
            className="min-h-36"
          />
          <Textarea
            value={urls}
            onChange={(event) => setUrls(event.target.value)}
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
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              Depth
              <input
                type="number"
                min={1}
                max={3}
                value={depth}
                onChange={(event) => setDepth(Number(event.target.value) || 1)}
                className="h-8 w-16 rounded-lg border border-input bg-card px-2 text-sm text-foreground"
              />
            </label>
            <Button
              type="button"
              disabled={loading || (!text.trim() && !urls.trim())}
              onClick={() =>
                void runCheck({
                  text,
                  urls: urls.split(/\s+/).map((item) => item.trim()).filter(Boolean),
                  engine,
                  depth,
                })
              }
            >
              {loading ? "Fetching pages and checking notices…" : "Check before shipping"}
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
              Three presets: Healthline olive oil (block), Healthline cinnamon (warn), Clean study
              (pass). A warn or a block shows the deciding path, the sentence at each hop, and the
              FalkorDB algo.SPpaths call.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {loading && !result ? (
        <p className="text-sm text-muted-foreground" role="status">
          Fetching the cited page, walking reviews, then checking publisher notices…
        </p>
      ) : null}

      {result ? (
        <ResultCard result={result} onRewrite={() => void runRewrite()} rewriting={rewriting} />
      ) : null}

      {rewrite?.text ? (
        <Card>
          <CardHeader>
            <CardTitle>Rewritten draft</CardTitle>
            <CardDescription>
              Template rewrite. Only flagged sentences changed. Untouched
              sentences stayed the same, then the check ran again.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-6">{rewrite.text}</p>
          </CardContent>
        </Card>
      ) : null}

      {rewrite?.recheck ? <ResultCard result={rewrite.recheck} /> : null}

      <footer className="text-xs leading-5 text-muted-foreground">
        An Expression of Concern is not a retraction. The olive-oil path reaches Estruch 2013, which
        was retracted and republished in 2018 after re-analysis (notice 10.1056/nejmc1806491). Khan
        2003 carries an Expression of Concern. This demo does not say a food or a medicine works or
        does not work. Both olive-oil hops are mention 0.55, not relies.
        Citation-context sentences may include{" "}
        <a className="underline" href="https://www.semanticscholar.org/">
          Semantic Scholar
        </a>{" "}
        data.
      </footer>
    </main>
  )
}
