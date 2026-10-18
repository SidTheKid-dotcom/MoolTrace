"use client"

import { Fragment } from "react"
import { IndexCard, Magnifier, Thread, type Tone } from "@/components/board/board"
import { monthYear, noticeWord, type Reason } from "@/lib/api"
import { decidingReason } from "@/lib/path-diagram"
import { cn } from "@/lib/utils"

const SITES: Record<string, string> = {
  "nutritionsource.hsph.harvard.edu": "Harvard Nutrition Source",
  "healthline.com": "Healthline",
  "webmd.com": "WebMD",
  "nhs.uk": "NHS",
  "medicalnewstoday.com": "Medical News Today",
  "verywellhealth.com": "Verywell Health",
  "everydayhealth.com": "Everyday Health",
  "pubmed.ncbi.nlm.nih.gov": "PubMed",
}

const EDGE_WORDS: Record<string, string> = {
  mention: "cites",
  background: "mentions",
  uses_data_or_method: "uses its data",
  included: "includes",
  relies: "relies on",
  unverified: "cites",
}

type Step = { kind?: string; doi?: string | null; url?: string | null; title?: string | null; year?: number | null; first_author?: string | null }

export function siteName(url: string | null | undefined): string {
  try {
    const host = new URL(url || "").hostname.replace(/^www\./, "")
    return SITES[host] || host
  } catch {
    return "Cited page"
  }
}

function pageTitle(step: Step): string {
  const raw = (step.title || "").split(/\s[•|–-]\s/)[0].trim()
  return raw || "Cited page"
}

function paperTitle(step: Step): string {
  return (step.title || step.doi || "Paper").replace(/^RETRACTED:\s*/i, "").replace(/^WITHDRAWN:\s*/i, "")
}

/** A short, real quote from the hop sentence, or nothing. Never invented. */
export function evidenceQuote(sentence: string | null | undefined): string {
  const text = sentence || ""
  const match = text.match(/\b(an?\s+)?(included (?:trial|study|studies)|pooled (?:data|results)?|relied on|used data from)\b/i)
  return match ? match[0].trim() : ""
}

export type PathCard = {
  key: string
  label: string
  title: string
  tone: Tone
  pin: "blue" | "red"
  stamp?: string
  href?: string
}

/** Turns the deciding SPpaths row into page → paper(s) → notice cards, with typed threads between. */
export function pathCards(reasons: Reason[]): { cards: PathCard[]; edges: { word: string; tone: "neutral" | "red" | "amber" }[]; quote: string; quoteEdge: number } | null {
  const deciding = decidingReason(reasons) as (Reason & { steps?: Step[] }) | null
  if (!deciding) return null
  const steps = (deciding.steps || []) as Step[]
  const hops = deciding.hops_evidence || []
  const word = noticeWord(deciding.notice_type)
  const concern = word === "Expression of Concern"
  const hot: Tone = concern ? "amber" : "red"
  const cards: PathCard[] = steps.map((step, index) => {
    const isSource = step.kind === "Source" || (!step.doi && !!step.url)
    const last = index === steps.length - 1
    if (isSource) {
      return { key: `s${index}`, label: `Page · ${siteName(step.url)}`, title: pageTitle(step), tone: "neutral", pin: "blue", href: step.url || undefined }
    }
    const who = step.first_author ? `${step.first_author}${step.year ? ` ${step.year}` : ""}` : step.year ? String(step.year) : "Paper"
    return {
      key: `w${index}`,
      label: `Paper · ${who}`,
      title: paperTitle(step),
      tone: last && deciding.notice_doi ? hot : "neutral",
      pin: last && deciding.notice_doi ? "red" : "blue",
      href: step.doi ? `https://doi.org/${step.doi}` : undefined,
    }
  })
  if (deciding.notice_doi) {
    const when = monthYear(deciding.notice_date)
    cards.push({
      key: "notice",
      label: `${word}${when ? ` · ${when}` : ""}`,
      title: concern ? "Expression of Concern" : word === "Withdrawn" ? "Withdrawal notice" : "Retraction notice",
      tone: hot,
      pin: "red",
      stamp: concern ? "Concern" : `${word}${when ? ` ${when.slice(-4)}` : ""}`,
      href: `https://doi.org/${deciding.notice_doi}`,
    })
  }
  const edges = cards.slice(1).map((_, index) => {
    const hop = hops[index]
    const toNotice = index === cards.length - 2 && !!deciding.notice_doi
    const reliance = hop?.reliance || ""
    const intoFlagged = index >= cards.length - 3 && !!deciding.notice_doi
    return {
      word: toNotice ? "" : EDGE_WORDS[reliance] || "cites",
      tone: (intoFlagged ? (concern ? "amber" : "red") : "neutral") as "neutral" | "red" | "amber",
    }
  })
  let quote = ""
  let quoteEdge = -1
  hops.forEach((hop, index) => {
    const q = evidenceQuote(hop.sentence)
    if (q && !quote) {
      quote = q
      quoteEdge = index
    }
  })
  return { cards, edges, quote, quoteEdge }
}

export function EvidencePath({
  reasons,
  onOpen,
  compact = false,
}: {
  reasons: Reason[]
  onOpen?: () => void
  compact?: boolean
}) {
  const built = pathCards(reasons)
  if (!built) return null
  const { cards, edges, quote, quoteEdge } = built
  return (
    <div className="relative" data-testid="evidence-path">
      <div className="flex flex-col items-stretch md:flex-row md:items-center">
        {cards.map((card, index) => (
          <Fragment key={card.key}>
            {index > 0 ? (
              <>
                <Thread vertical className="md:hidden" tone={edges[index - 1].tone} label={edges[index - 1].word} delay={250 + index * 220} />
                <div className="relative hidden md:flex">
                  <Thread tone={edges[index - 1].tone} label={compact ? undefined : edges[index - 1].word} delay={250 + index * 220} className={compact ? "!w-8 lg:!w-10" : undefined} />
                  {quote && quoteEdge === index - 1 && !compact ? (
                    <Magnifier quote={quote} size={128} className="absolute left-1/2 top-1/2 z-20 -translate-x-[34%] -translate-y-[22%]" />
                  ) : null}
                </div>
              </>
            ) : null}
            <div className={cn("rise min-w-0 md:flex-1")} style={{ animationDelay: `${index * 160}ms` }}>
              <IndexCard
                label={card.label}
                title={card.title}
                tone={card.tone}
                pin={card.pin}
                stamp={card.stamp}
                stampDelay={600 + index * 200}
                onClick={onOpen}
                title_attr={card.title}
                className={compact ? "px-3 pb-3 pt-3" : undefined}
              />
            </div>
          </Fragment>
        ))}
      </div>
      {quote && !compact ? (
        <p className="font-display mt-3 text-center text-[17px] italic text-ink-2 md:hidden">“{quote}”</p>
      ) : null}
    </div>
  )
}
