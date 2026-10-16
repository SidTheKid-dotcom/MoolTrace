export type PathStep = {
  kind?: string
  doi?: string | null
  title?: string | null
  url?: string | null
  year?: number | null
}

export type PathHop = {
  weight?: number | null
  reliance?: string | null
  sentence?: string | null
  evidence_from?: string | null
}

export type PathReason = {
  notice_doi?: string | null
  notice_type?: string | null
  notice_label?: string | null
  sentence?: string | null
  steps?: PathStep[]
  hops_evidence?: PathHop[]
  sp_cost?: number | null
}

export type PathNode = {
  id: string
  kind: "Source" | "Work" | "Notice"
  label: string
  sublabel: string
  title: string
  doi?: string | null
  url?: string | null
}

export type PathEdge = {
  from: string
  to: string
  label: string
  weight?: number | null
  sentence?: string | null
  evidence_from?: string | null
}

export type PathGraph = {
  nodes: PathNode[]
  edges: PathEdge[]
}

export function noticeLabel(noticeType: string | null | undefined, fallback?: string | null): string {
  const raw = (noticeType || fallback || "notice").trim()
  if (raw === "expression_of_concern") return "Expression of Concern"
  if (raw === "retraction") return "Retraction"
  if (raw === "withdrawal") return "Withdrawal"
  if (raw === "removal") return "Removal"
  return raw.replaceAll("_", " ")
}

export function hostLabel(url: string | null | undefined): string {
  const raw = (url || "").trim()
  if (!raw) return ""
  if (raw.startsWith("urn:mooltrace:paste:")) return "draft"
  try {
    return new URL(raw).hostname.replace(/^www\./, "")
  } catch {
    return raw
  }
}

function clip(text: string, max: number): string {
  const clean = text.replace(/\s+/g, " ").trim()
  if (clean.length <= max) return clean
  return `${clean.slice(0, max - 1).trimEnd()}…`
}

function stepNode(step: PathStep, index: number): PathNode {
  const kind: PathNode["kind"] = step.kind === "Source" || (!step.doi && step.url) ? "Source" : "Work"
  const title = (step.title || "").trim()
  if (kind === "Source") {
    const host = hostLabel(step.url) || "source"
    return {
      id: `n${index}`,
      kind,
      label: host,
      sublabel: clip(title, 42) || clip(step.url || "", 36),
      title: title || step.url || host,
      url: step.url,
    }
  }
  const doi = (step.doi || "").trim()
  return {
    id: `n${index}`,
    kind,
    label: clip(title, 36) || doi || "work",
    sublabel: [step.year ? String(step.year) : "", doi].filter(Boolean).join(" · "),
    title: title || doi || "work",
    doi,
    url: step.url,
  }
}

export function buildPathGraph(reason: PathReason): PathGraph {
  const steps = reason.steps || []
  const hops = reason.hops_evidence || []
  const nodes = steps.map((step, index) => stepNode(step, index))
  const edges: PathEdge[] = []
  for (let index = 0; index < nodes.length - 1; index += 1) {
    const hop = hops[index] || {}
    edges.push({
      from: nodes[index].id,
      to: nodes[index + 1].id,
      label: (hop.reliance || "RESTS_ON").replaceAll("_", " "),
      weight: hop.weight,
      sentence: hop.sentence,
      evidence_from: hop.evidence_from,
    })
  }
  if (reason.notice_doi || reason.notice_type) {
    const notice: PathNode = {
      id: "notice",
      kind: "Notice",
      label: noticeLabel(reason.notice_type, reason.notice_label),
      sublabel: (reason.notice_doi || "").trim(),
      title: noticeLabel(reason.notice_type, reason.notice_label),
      doi: reason.notice_doi,
    }
    nodes.push(notice)
    const last = nodes[nodes.length - 2]
    if (last) {
      edges.push({
        from: last.id,
        to: notice.id,
        label: "FLAGS",
        sentence: reason.sentence,
      })
    }
  }
  return { nodes, edges }
}

export function decidingReason<T extends PathReason>(reasons: T[]): T | null {
  const withPath = reasons.filter((reason) => (reason.steps || []).length > 0)
  const withNotice = withPath.filter((reason) => reason.notice_doi || reason.notice_type)
  const pool = withNotice.length ? withNotice : withPath
  if (!pool.length) return null
  return [...pool].sort((a, b) => {
    const left = a.sp_cost
    const right = b.sp_cost
    if (left == null && right == null) return 0
    if (left == null) return 1
    if (right == null) return -1
    return left - right
  })[0]
}
