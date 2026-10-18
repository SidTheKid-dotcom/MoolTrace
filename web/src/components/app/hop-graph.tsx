"use client"

import { Ban, CircleAlert, CircleCheck, FileText } from "lucide-react"
import { Fragment } from "react"
import { Thread } from "@/components/board/board"
import type { Check, Reason } from "@/lib/api"
import { cleanTitle, flagKind, flagLabel, pageName, pageTitle, relianceWord, workName } from "@/lib/naming"
import { decidingReason } from "@/lib/path-diagram"
import { cn } from "@/lib/utils"

type ExploredRow = {
  source_url?: string | null
  source_title?: string | null
  works?: { doi?: string | null; title?: string | null; year?: number | null; first_author?: string | null }[]
  reliances?: (string | null)[]
}

type Node = {
  key: string
  kind: string
  name: string
  full: string
  via: string
  relianceInto?: string | null
  flag?: string
  flagType?: ReturnType<typeof flagKind>
  onPath: boolean
}

/** Columns: the cited page, then one column per hop up to the selected depth. Built from every
 *  RESTS_ON chain the check walked, so 1, 2 and 3 hops draw different graphs. */
export function buildColumns(check: Check, depth: number, fallbackUrl?: string): Node[][] {
  const explored = ((check as unknown as { explored?: ExploredRow[] }).explored || []) as ExploredRow[]
  const deciding = decidingReason(check.reasons || []) as (Reason & { steps?: { doi?: string | null }[] }) | null
  const pathDois = new Set((deciding?.steps || []).map((step) => (step.doi || "").toLowerCase()).filter(Boolean))
  const flagged = new Map<string, Reason>()
  for (const reason of check.reasons || []) {
    if (reason.notice_doi && reason.root_doi) flagged.set(reason.root_doi.toLowerCase(), reason)
  }
  const first = explored[0]
  const pageUrl = first?.source_url || fallbackUrl || ""
  const columns: Node[][] = [
    [
      {
        key: "page",
        kind: pageUrl.startsWith("urn:") ? "Draft" : "Page",
        name: pageName(pageUrl, first?.source_title),
        full: pageTitle(first?.source_title) || pageUrl,
        via: "",
        onPath: !!deciding,
      },
    ],
  ]
  for (let hop = 1; hop <= depth; hop++) {
    const seen = new Map<string, Node>()
    for (const row of explored) {
      const works = row.works || []
      if (works.length !== hop) continue
      const work = works[hop - 1]
      const doi = (work.doi || "").toLowerCase()
      if (!doi || seen.has(doi)) continue
      const relianceInto = (row.reliances || [])[hop - 1]
      const named = workName(work, relianceInto)
      const reason = flagged.get(doi)
      seen.set(doi, {
        key: doi,
        kind: named.kind,
        name: named.name,
        full: cleanTitle(work.title) || work.doi || "",
        via: relianceWord(relianceInto),
        relianceInto,
        flag: reason ? flagLabel(reason.notice_type, reason.notice_date, doi) : undefined,
        flagType: reason ? flagKind(cochraneType(reason.notice_type, doi)) : undefined,
        onPath: pathDois.has(doi),
      })
    }
    columns.push(Array.from(seen.values()))
  }
  return columns
}

function cochraneType(type: string | null | undefined, doi: string): string {
  return doi.startsWith("10.1002/14651858.") && (type || "").toLowerCase().includes("retract") ? "withdrawal" : type || ""
}

function NodeCard({ node, hop, compact }: { node: Node; hop: number; compact?: boolean }) {
  const concern = node.flagType === "concern"
  const hot = !!node.flag
  return (
    <div
      title={`${node.kind} · ${node.name}${node.full && node.full !== node.name ? `\n${node.full}` : ""}${node.flag ? `\n${node.flag}` : ""}`}
      className={cn(
        "paper-texture index-card relative flex w-full flex-col rounded-[6px] px-3.5 pb-3 pt-3 text-left text-ink",
        compact ? "h-[118px]" : "h-[132px]",
        hot && (concern ? "ring-1 ring-amber-x/40" : "ring-1 ring-rx/40"),
      )}
      data-testid="hop-node"
    >
      <p className="font-label text-[10.5px] text-ink-2">
        {hop === 0 ? node.kind : `${node.kind} · hop ${hop}`}
      </p>
      <p className={cn("font-display mt-1 line-clamp-2 leading-[1.08]", compact ? "text-[19px]" : "text-[21px]")}>{node.name}</p>
      {node.full && node.full !== node.name && !compact ? (
        <p className="mt-0.5 line-clamp-1 text-[12px] text-ink-2">{node.full}</p>
      ) : null}
      {node.flag ? (
        <p className={cn("mt-auto flex items-start gap-1.5 text-[12.5px] font-semibold leading-tight", concern ? "text-amber-x" : "text-rx")}>
          {concern ? <CircleAlert className="mt-px size-3.5 shrink-0" aria-hidden /> : <Ban className="mt-px size-3.5 shrink-0" aria-hidden />}
          <span>{node.flag}</span>
        </p>
      ) : hop > 0 ? (
        <p className="mt-auto flex items-center gap-1.5 text-[12px] text-clear">
          <CircleCheck className="size-3.5 shrink-0" aria-hidden /> No notice
        </p>
      ) : (
        <p className="mt-auto flex items-center gap-1.5 text-[12px] text-ink-2">
          <FileText className="size-3.5 shrink-0" aria-hidden /> Cited by the answer
        </p>
      )}
    </div>
  )
}

function EmptyHop({ hop, compact }: { hop: number; compact?: boolean }) {
  return (
    <div
      className={cn(
        "flex w-full flex-col justify-center rounded-[6px] border-2 border-dashed border-ink/15 px-3.5 text-left",
        compact ? "h-[118px]" : "h-[132px]",
      )}
      data-testid="hop-empty"
    >
      <p className="font-label text-[10.5px] text-ink-2">Hop {hop}</p>
      <p className="mt-1 text-[13.5px] leading-snug text-ink-2">Nothing further in the graph at this hop.</p>
    </div>
  )
}

export function HopGraph({ check, depth, url, compact = false, animate = true, onOpen }: { check: Check; depth: number; url?: string; compact?: boolean; animate?: boolean; onOpen?: () => void }) {
  const columns = buildColumns(check, depth, url)
  const Wrapper = onOpen ? "button" : "div"
  return (
    <Wrapper
      type={onOpen ? "button" : undefined}
      onClick={onOpen}
      aria-label={onOpen ? "Open the evidence for this path" : undefined}
      className={cn("block w-full text-left", onOpen && "cursor-pointer rounded-xl focus-visible:outline-2 focus-visible:outline-ink")}
      data-testid="hop-graph"
      data-depth={depth}
    >
      <div className="flex flex-col items-stretch md:flex-row md:items-center">
        {columns.map((column, index) => {
          const dense = compact || columns.length > 3
          const via = column.length === 1 ? column[0].via : column.length ? "cites" : ""
          const hot = column.some((node) => node.flag && node.onPath)
          const concern = column.some((node) => node.flagType === "concern")
          return (
            <Fragment key={index}>
              {index > 0 ? (
                <>
                  <Thread vertical className="md:hidden" tone={hot ? (concern ? "amber" : "red") : "neutral"} label={via} animate={false} />
                  <Thread
                    tone={hot ? (concern ? "amber" : "red") : "neutral"}
                    label={via}
                    animate={false}
                    className={cn("hidden md:flex", compact ? "!w-16 lg:!w-20" : "!w-20 lg:!w-24")}
                  />
                </>
              ) : null}
              <div className={cn("flex min-w-0 flex-col gap-2 md:flex-1", animate && "rise")} style={animate ? { animationDelay: `${index * 120}ms` } : undefined}>
                {column.length ? column.map((node) => <NodeCard key={node.key} node={node} hop={index} compact={dense} />) : <EmptyHop hop={index} compact={dense} />}
              </div>
            </Fragment>
          )
        })}
      </div>
    </Wrapper>
  )
}
