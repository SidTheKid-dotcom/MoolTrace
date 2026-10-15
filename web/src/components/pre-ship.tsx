"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"

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
  hops_evidence?: { weight?: number | null; reliance?: string | null; sentence?: string | null }[]
  label?: string | null
}
type Check = {
  decision: "pass" | "warn" | "block"
  summary: string
  pitch?: string | null
  reasons: Reason[]
  discounted?: Reason[]
  independent_source_count?: number
  weight_floor?: number
  cypher?: string
  elapsed_ms?: number
  limits?: string
  errors?: string[]
  context_notes?: string[]
  remediation_clusters?: { clusters?: unknown[]; call?: string }
}
type Reverse = {
  notice_doi?: string | null
  notice_type?: string | null
  root_doi?: string | null
  root_title?: string | null
  answer_count?: number
  source_count?: number
  engines?: string[]
  cypher?: string
  elapsed_ms?: number
}

const PRESETS = [
  {
    id: "everyday",
    label: "Everyday Health",
    hint: "URL-only nutrition-coach page",
    engine: "nutrition-coach",
    depth: 2,
    text: "",
    urls: ["https://www.everydayhealth.com/diabetes/cinnamon-for-diabetes/"],
  },
  {
    id: "allen",
    label: "Allen 2013",
    hint: "Expression of Concern path",
    engine: "allen-2013",
    depth: 2,
    text: "10.1370/afm.1517",
    urls: [] as string[],
  },
  {
    id: "lancet",
    label: "Lancet 2020",
    hint: "Retracted registry paper",
    engine: "patient-chatbot",
    depth: 1,
    text: "A draft patient note says a 2020 Lancet registry analysis by Mehra and colleagues reported outcomes for hydroxychloroquine. DOI 10.1016/S0140-6736(20)31180-6. This note is not a recommendation to start or stop a medicine.",
    urls: [] as string[],
  },
  {
    id: "clean",
    label: "Clean DOI",
    hint: "No flagged ancestor at depth 2",
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

function stepLabel(step: Step): string {
  return step.doi || step.url || step.title || "step"
}

export function PreShip() {
  const [text, setText] = useState(PRESETS[0].text)
  const [urls, setUrls] = useState(PRESETS[0].urls.join("\n"))
  const [engine, setEngine] = useState(PRESETS[0].engine)
  const [depth, setDepth] = useState(2)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [result, setResult] = useState<Check | null>(null)
  const [reverseDoi, setReverseDoi] = useState("10.2337/dc25-ec09")
  const [reverseLoading, setReverseLoading] = useState(false)
  const [reverseError, setReverseError] = useState("")
  const [reverse, setReverse] = useState<Reverse | null>(null)

  async function runCheck(body: { text: string; urls: string[]; engine: string; depth: number }) {
    setLoading(true)
    setError("")
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

  function applyPreset(id: string) {
    const preset = PRESETS.find((item) => item.id === id)
    if (!preset) return
    setText(preset.text)
    setUrls(preset.urls.join("\n"))
    setEngine(preset.engine)
    setDepth(preset.depth)
    void runCheck({ text: preset.text, urls: preset.urls, engine: preset.engine, depth: preset.depth })
  }

  async function runReverse() {
    setReverseLoading(true)
    setReverseError("")
    try {
      const response = await fetch(`/nw/rests-on?doi=${encodeURIComponent(reverseDoi.trim())}`)
      if (!response.ok) throw new Error(`Reverse lookup returned HTTP ${response.status}.`)
      setReverse((await response.json()) as Reverse)
    } catch (exc) {
      setReverse(null)
      setReverseError(exc instanceof Error ? exc.message : "The reverse lookup did not finish.")
    } finally {
      setReverseLoading(false)
    }
  }

  const counted = (result?.reasons || []).filter((reason) => reason.code && reason.code !== "incomplete")

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 py-8 sm:px-6 sm:py-12">
      <header className="flex flex-col gap-3">
        <p className="text-sm font-medium tracking-wide text-primary">MoolTrace</p>
        <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
          Trace your AI&apos;s answer to its root, and see if that root is flagged.
        </h1>
        <p className="text-base leading-7 text-muted-foreground">
          Evidence viewer for the pre-merge check. Paste a draft or a cited URL. Pass, warn, or
          block comes back with every graph path, each hop&apos;s sentence, and the Cypher that
          decided it. CI over JSONL fixtures is the product workflow.
        </p>
      </header>

      <Tabs defaultValue="check">
        <TabsList>
          <TabsTrigger value="check">Pre-ship check</TabsTrigger>
          <TabsTrigger value="reverse">What rests on this</TabsTrigger>
        </TabsList>

        <TabsContent value="check" className="flex flex-col gap-4 pt-4">
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((preset) => (
              <Button
                key={preset.id}
                type="button"
                variant="outline"
                disabled={loading}
                onClick={() => applyPreset(preset.id)}
              >
                {preset.label}
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
                  {loading ? "Checking citation paths…" : "Check before shipping"}
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
                  Choose a preset or paste a draft. A warn or a block shows the deciding sentence,
                  the graph path, and the Cypher that produced them.
                </CardDescription>
              </CardHeader>
            </Card>
          ) : null}

          {loading && !result ? (
            <p className="text-sm text-muted-foreground">Checking citation paths…</p>
          ) : null}

          {result ? (
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={decisionVariant(result.decision)}>{result.decision}</Badge>
                  <span className="text-xs text-muted-foreground">
                    {result.independent_source_count ?? 0} independent source
                    {(result.independent_source_count ?? 0) === 1 ? "" : "s"} at weight ≥{" "}
                    {result.weight_floor ?? 0.5}
                    {result.elapsed_ms != null ? ` · ${result.elapsed_ms} ms` : ""}
                  </span>
                </div>
                <CardTitle className="text-xl leading-snug">{result.summary}</CardTitle>
                {result.pitch ? <CardDescription>{result.pitch}</CardDescription> : null}
              </CardHeader>
              <CardContent className="flex flex-col gap-5">
                {counted.length === 0 ? (
                  <p className="text-sm leading-6 text-muted-foreground">{result.limits}</p>
                ) : null}
                {counted.map((reason, index) => (
                  <article key={`${reason.notice_doi}-${reason.root_doi}-${index}`} className="flex flex-col gap-3">
                    {index > 0 ? <Separator /> : null}
                    <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                      <span>{reason.label || reason.notice_type || reason.code}</span>
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
                      <p className="text-xs text-muted-foreground">
                        {reason.hops_evidence.length} judged hop
                        {reason.hops_evidence.length === 1 ? "" : "s"}
                        {reason.path_score != null ? ` · path score ${reason.path_score}` : ""}
                      </p>
                    ) : null}
                  </article>
                ))}
                {(result.discounted || []).length > 0 ? (
                  <p className="text-sm text-muted-foreground">
                    {result.discounted?.length} citation path
                    {result.discounted?.length === 1 ? "" : "s"} reached a notice only as background
                    or a dispute, so {result.discounted?.length === 1 ? "it does" : "they do"} not
                    change this check.
                  </p>
                ) : null}
                {result.context_notes && result.context_notes.length > 0 ? (
                  <p className="text-xs text-muted-foreground">{result.context_notes.join(" ")}</p>
                ) : null}
                {(result.remediation_clusters?.clusters || []).length > 0 ? (
                  <p className="text-xs text-muted-foreground">
                    WCC remediation clusters: {result.remediation_clusters?.clusters?.length}. This
                    groups review work. It is not the verdict.
                  </p>
                ) : null}
                {result.cypher ? (
                  <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs leading-5">{result.cypher}</pre>
                ) : null}
                {result.remediation_clusters?.call ? (
                  <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs leading-5">
                    {result.remediation_clusters.call}
                  </pre>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </TabsContent>

        <TabsContent value="reverse" className="flex flex-col gap-4 pt-4">
          <Card>
            <CardHeader>
              <CardTitle>What already rests on a flagged study</CardTitle>
              <CardDescription>
                Reverse lookup on the Expression of Concern for Khan 2003, or paste another DOI.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 sm:flex-row">
              <input
                value={reverseDoi}
                onChange={(event) => setReverseDoi(event.target.value)}
                className="h-9 min-w-0 flex-1 rounded-lg border border-input bg-card px-3 text-sm"
              />
              <Button type="button" disabled={reverseLoading || !reverseDoi.trim()} onClick={() => void runReverse()}>
                {reverseLoading ? "Looking up…" : "Look up"}
              </Button>
            </CardContent>
          </Card>
          {reverseError ? (
            <Card>
              <CardHeader>
                <CardTitle>The lookup did not finish</CardTitle>
                <CardDescription>{reverseError}</CardDescription>
              </CardHeader>
            </Card>
          ) : null}
          {!reverse && !reverseError && !reverseLoading ? (
            <Card>
              <CardHeader>
                <CardTitle>No reverse lookup yet</CardTitle>
                <CardDescription>
                  This asks the persistent graph which drafts already cite the flagged study.
                </CardDescription>
              </CardHeader>
            </Card>
          ) : null}
          {reverse ? (
            <Card>
              <CardHeader>
                <CardTitle>
                  {reverse.answer_count ?? 0} draft{(reverse.answer_count ?? 0) === 1 ? "" : "s"},{" "}
                  {reverse.source_count ?? 0} source{(reverse.source_count ?? 0) === 1 ? "" : "s"}
                </CardTitle>
                <CardDescription>
                  {reverse.notice_type || "notice"} {reverse.notice_doi} on {reverse.root_doi}
                  {reverse.elapsed_ms != null ? ` · ${reverse.elapsed_ms} ms` : ""}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {reverse.root_title ? <p className="text-sm">{reverse.root_title}</p> : null}
                {(reverse.engines || []).length > 0 ? (
                  <p className="text-sm text-muted-foreground">{reverse.engines?.join(", ")}</p>
                ) : (
                  <p className="text-sm text-muted-foreground">No drafts in this graph cite it yet.</p>
                )}
                {reverse.cypher ? (
                  <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs leading-5">{reverse.cypher}</pre>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </TabsContent>
      </Tabs>

      <footer className="text-xs leading-5 text-muted-foreground">
        An Expression of Concern is not a retraction. Khan 2003 carries an Expression of Concern;
        the 2020 Lancet hydroxychloroquine registry analysis was retracted. OpenAlex can still mark
        Khan as not retracted. This demo does not say a food or a medicine works or does not work.
        Citation-context sentences may include{" "}
        <a className="underline" href="https://www.semanticscholar.org/">
          Semantic Scholar
        </a>{" "}
        data.
      </footer>
    </main>
  )
}
