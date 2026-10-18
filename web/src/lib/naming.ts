// One naming scheme for every graph node, on the landing page, in the app and in the agent:
// "Page · Harvard vitamin D" → "Review · Cochrane 2014 (Avenell)" → "Trial · Ishida 2004".

export type NamedStep = {
  doi?: string | null
  url?: string | null
  title?: string | null
  year?: number | null
  first_author?: string | null
}

const COCHRANE = "10.1002/14651858."

const SITES: Record<string, string> = {
  "nutritionsource.hsph.harvard.edu": "Harvard",
  "healthline.com": "Healthline",
  "webmd.com": "WebMD",
  "nhs.uk": "NHS",
  "medicalnewstoday.com": "Medical News Today",
  "verywellhealth.com": "Verywell Health",
  "everydayhealth.com": "Everyday Health",
  "pubmed.ncbi.nlm.nih.gov": "PubMed",
}

// Short topic names for the pages the demo uses; other pages fall back to their <title>.
const PAGES: Record<string, string> = {
  "nutritionsource.hsph.harvard.edu/vitamin-d": "Harvard vitamin D",
  "nutritionsource.hsph.harvard.edu/zinc": "Harvard zinc",
  "healthline.com/nutrition/11-proven-benefits-of-olive-oil": "Healthline olive oil",
  "nhs.uk/live-well/best-way-to-wash-your-hands": "NHS hand washing",
}

export const RELIANCE_WORDS: Record<string, string> = {
  included: "includes",
  relies: "relies on",
  uses_data_or_method: "uses its data",
  "uses data or method": "uses its data",
  mention: "mentions",
  background: "mentions in passing",
  unverified: "cites (unverified)",
}

export function relianceWord(reliance: string | null | undefined): string {
  return RELIANCE_WORDS[reliance || ""] || "cites"
}

function host(url: string | null | undefined): string {
  try {
    return new URL(url || "").hostname.replace(/^www\./, "")
  } catch {
    return ""
  }
}

export function siteShort(url: string | null | undefined): string {
  const h = host(url)
  return SITES[h] || h || "Cited page"
}

/** The page's own <title>, without the site suffix ("How to wash your hands - NHS" → "How to wash your hands"). */
export function pageTitle(title: string | null | undefined): string {
  return (title || "").split(/\s[•|–—-]\s/)[0].trim()
}

export function pageName(url: string | null | undefined, title?: string | null): string {
  if ((url || "").startsWith("urn:mooltrace:paste:")) return "Your draft"
  const key = (url || "").replace(/^https?:\/\/(www\.)?/, "").replace(/\/+$/, "")
  if (PAGES[key]) return PAGES[key]
  const t = pageTitle(title)
  return t ? `${siteShort(url)} · ${t}` : siteShort(url)
}

export function cleanTitle(title: string | null | undefined): string {
  return (title || "").replace(/^(RETRACTED|WITHDRAWN|RETRACTION|WITHDRAWAL)\s*:\s*/i, "").trim()
}

/** "Review" | "Trial" | "Paper" and a short name. The hop into a work tells us how it was used. */
export function workName(step: NamedStep, relianceInto?: string | null): { kind: string; name: string } {
  const author = step.first_author || ""
  const year = step.year ? String(step.year) : ""
  const doi = (step.doi || "").toLowerCase()
  const title = cleanTitle(step.title)
  if (doi.startsWith(COCHRANE)) {
    return { kind: "Review", name: `Cochrane${year ? ` ${year}` : ""}${author ? ` (${author})` : ""}` }
  }
  const who = [author, year].filter(Boolean).join(" ") || title || step.doi || "Paper"
  if (/\b(systematic review|meta-analys|review)\b/i.test(title)) return { kind: "Review", name: who }
  if (relianceInto === "included" || relianceInto === "uses_data_or_method" || /\btrial\b/i.test(title)) {
    return { kind: "Trial", name: who }
  }
  return { kind: "Paper", name: who }
}

export function monthYear(date: string | null | undefined): string {
  if (!date) return ""
  const d = new Date(date.length === 7 ? `${date}-01` : date)
  if (Number.isNaN(d.getTime())) return ""
  return d.toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" })
}

export type FlagKind = "retracted" | "withdrawn" | "concern" | "flagged"

export function flagKind(type: string | null | undefined): FlagKind {
  const t = (type || "").toLowerCase()
  if (t.includes("concern")) return "concern"
  if (t.includes("withdraw") || t === "removal") return "withdrawn"
  if (t.includes("retract")) return "retracted"
  return "flagged"
}

/** "Retracted · May 2025", "Withdrawn by Cochrane · Apr 2015", "Expression of Concern · Aug 2025". Never calls a withdrawal a retraction. */
export function flagLabel(type: string | null | undefined, date: string | null | undefined, workDoi?: string | null): string {
  const kind = flagKind(type)
  const when = monthYear(date)
  const word =
    kind === "withdrawn"
      ? (workDoi || "").toLowerCase().startsWith(COCHRANE)
        ? "Withdrawn by Cochrane"
        : "Withdrawn"
      : kind === "retracted"
        ? "Retracted"
        : kind === "concern"
          ? "Expression of Concern"
          : "Publisher notice"
  return when ? `${word} · ${when}` : word
}
