import type { PathReason } from "@/lib/path-diagram"

export type Reason = PathReason & {
  code?: string
  root_doi?: string | null
  notice_date?: string | null
  hops_evidence?: {
    weight?: number | null
    reliance?: string | null
    sentence?: string | null
    source_url?: string | null
    fetched_at?: string | null
  }[]
}

export type Check = {
  decision: "pass" | "warn" | "block"
  exit_code?: number
  summary: string
  reasons: Reason[]
  coverage?: string
  limits?: string
  algorithm?: { strength?: number | null; explanation?: string; cypher?: string } | null
  impact?: { summary?: string; counted_answer_count?: number; root_doi?: string | null } | null
  why_graph?: {
    cypher?: string
    without_graph?: { line?: string; notice_count?: number }
    with_graph?: { line?: string; depth?: number }
  } | null
}

export type Rewrite = { rewritten?: boolean; before?: string; text?: string; recheck?: Check }

export type AgentStep = {
  guard?: boolean
  tool?: string
  args?: Record<string, unknown>
  ms?: number
  ok?: boolean
  summary?: {
    verdict?: string | null
    exit_code?: number | null
    path?: string | null
    error?: string | null
    rows?: number | null
    chain?: { doi?: string | null; url?: string | null; title?: string | null; year?: number | null; first_author?: string | null; reliance?: string | null; notice_type?: string | null; notice_date?: string | null }[]
  }
}

export type AgentResult = {
  action?: string
  label?: string
  model?: string
  fallback_reason?: string | null
  steps?: AgentStep[]
  shipped?: string
  shipped_verdict?: { verdict?: string | null; exit_code?: number | null }
  without_mooltrace?: { text?: string; note?: string; source?: string }
  agent_note?: string
  budget?: { spent_usd?: number; limit_usd?: number }
  elapsed_ms?: number
  disclosure?: string
  cited_urls?: { url?: string; ok?: boolean; status?: string }[]
  doi?: string
  note?: string
  affected_answers?: {
    answer_id?: string
    count?: number
    urls?: string[]
    decision?: string
    path?: string
    rewrite?: string
  }[]
}

export type Input = { text: string; urls: string[]; engine: string; depth: number }

export const LIVE_HOSTS = [
  "nutritionsource.hsph.harvard.edu",
  "healthline.com",
  "webmd.com",
  "medicalnewstoday.com",
  "verywellhealth.com",
  "everydayhealth.com",
  "pubmed.ncbi.nlm.nih.gov",
  "doi.org",
]

const URL_RE = /https?:\/\/[^\s)]+/g

/** One box takes an answer, URLs, or DOIs; URLs become cited sources, the rest is the draft. */
export function parseInput(raw: string, depth: number): Input {
  const urls = Array.from(new Set((raw.match(URL_RE) || []).map((u) => u.replace(/[.,;]+$/, ""))))
  const prose = raw.replace(URL_RE, "").replace(/\s+/g, " ").trim()
  return { text: prose ? raw.trim() : "", urls, engine: "nutrition-coach", depth }
}

async function post<T>(path: string, body: unknown, timeoutMs: number): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  })
  if (!response.ok) {
    const detail = await response.text()
    if (response.status === 429) throw new Error("Busy or rate-limited. Try again in a minute.")
    if (response.status === 504) throw new Error("That page took too long. Try an example.")
    if (response.status === 400 && /allow/i.test(detail)) {
      throw new Error("Live checks run on Harvard Nutrition Source, Healthline, WebMD, PubMed and a few others.")
    }
    throw new Error(`Something went wrong (HTTP ${response.status}).`)
  }
  return (await response.json()) as T
}

export const checkAnswer = (input: Input) => post<Check>("/nw/check-answer", input, 130_000)
export const rewriteAnswer = (input: Input) => post<Rewrite>("/nw/rewrite", input, 130_000)
export const runAgent = (body: Record<string, unknown>) => post<AgentResult>("/nw/agent", body, 120_000)

export type Verdict = "block" | "warn" | "pass" | "empty"

/** Plain-language verdict. "Not in the graph" is its own state, never "safe". */
export function verdictOf(check: Check): Verdict {
  if (check.decision === "pass") return "pass"
  if (check.decision === "block") return "block"
  const counted = (check.reasons || []).some((r) => r.notice_doi)
  return counted ? "warn" : "empty"
}

export const VERDICT_COPY: Record<Verdict, { title: string; icon: string; tone: string }> = {
  block: { title: "Don't ship", icon: "✕", tone: "bad" },
  warn: { title: "Review before shipping", icon: "!", tone: "warn" },
  pass: { title: "Clear", icon: "✓", tone: "ok" },
  empty: { title: "Not in the graph", icon: "?", tone: "warn" },
}

export function noticeWord(type: string | null | undefined): string {
  const t = (type || "").toLowerCase()
  if (t.includes("concern")) return "Expression of Concern"
  if (t.includes("withdraw")) return "Withdrawn"
  if (t.includes("retract")) return "Retracted"
  return "Flagged"
}

export function monthYear(date: string | null | undefined): string {
  if (!date) return ""
  const d = new Date(date.length === 7 ? `${date}-01` : date)
  if (Number.isNaN(d.getTime())) return ""
  return d.toLocaleDateString("en-GB", { month: "short", year: "numeric" })
}
