"use client"

import { buildPathGraph, decidingReason } from "@/lib/path-diagram"
import { monthYear, noticeWord, type Reason } from "@/lib/api"
import { cn } from "@/lib/utils"

const EDGE_WORDS: Record<string, string> = {
  mention: "cites",
  background: "mentions",
  "uses data or method": "uses its data",
  included: "includes",
  relies: "relies on",
  unverified: "cites",
}

const SITES: Record<string, string> = {
  "nutritionsource.hsph.harvard.edu": "Harvard Nutrition Source",
  "healthline.com": "Healthline",
  "webmd.com": "WebMD",
  "nhs.uk": "NHS",
  "medicalnewstoday.com": "Medical News Today",
  "verywellhealth.com": "Verywell Health",
  "everydayhealth.com": "Everyday Health",
}

function siteName(host: string): string {
  const bare = host.replace(/^www\./, "")
  return SITES[bare] || bare
}

/** The citation path as a row of cards: page → paper → paper → notice. */
export function Chain({ reasons }: { reasons: Reason[] }) {
  const deciding = decidingReason(reasons)
  if (!deciding) return null
  const graph = buildPathGraph(deciding)
  const notice = deciding as Reason
  const concern = noticeWord(notice.notice_type) === "Expression of Concern"
  const hot = concern ? "border-amber-200 bg-amber-50" : "border-red-200 bg-red-50"
  const hotText = concern ? "text-amber-800" : "text-red-700"
  const hotLine = concern ? "bg-amber-400" : "bg-red-400"
  const steps = (deciding.steps || []) as { first_author?: string | null; year?: number | null; title?: string | null }[]
  const workLabel = (index: number, fallback: string) => {
    const step = steps[index]
    if (step?.first_author) return `${step.first_author}${step.year ? ` ${step.year}` : ""}`
    return fallback.replace(/^RETRACTED:\s*/i, "")
  }
  return (
    <div className="flex flex-col items-stretch gap-1 sm:flex-row sm:items-center" data-testid="chain">
      {graph.nodes.map((node, index) => {
        const edge = graph.edges[index - 1]
        const isNotice = node.kind === "Notice"
        const flagged = isNotice || index === graph.nodes.length - 2
        const edgeWord = edge ? EDGE_WORDS[edge.label] ?? (edge.label === "FLAGS" ? "" : edge.label) : ""
        return (
          <div key={node.id} className="contents">
            {index > 0 ? (
              <div className="flex shrink-0 items-center justify-center px-1 sm:w-20 sm:flex-col">
                <span className="text-[11px] text-muted-foreground sm:order-1">{edgeWord}</span>
                <span
                  className={cn(
                    "mx-2 h-4 w-px sm:mx-0 sm:my-1 sm:h-px sm:w-full",
                    flagged ? hotLine : "bg-border",
                  )}
                />
              </div>
            ) : null}
            <div
              title={node.title}
              className={cn(
                "min-w-0 flex-1 rounded-xl border px-3 py-2.5",
                flagged ? hot : "border-border bg-card",
              )}
            >
              <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">
                {isNotice ? noticeWord(notice.notice_type) : node.kind === "Source" ? "Page" : "Paper"}
              </p>
              <p className={cn("line-clamp-2 text-sm font-medium leading-snug", flagged && hotText)}>
                {isNotice
                  ? monthYear(notice.notice_date) || node.label
                  : node.kind === "Source"
                    ? siteName(node.label)
                    : workLabel(index, node.label)}
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
