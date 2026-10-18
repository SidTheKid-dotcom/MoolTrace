"use client"

import { useState } from "react"
import { runAgent, type AgentResult } from "@/lib/api"
import { pageName, relianceWord } from "@/lib/naming"
import { ISHIDA_2004_DOI } from "@/lib/presets"

export function AlertTab() {
  const [doi, setDoi] = useState(ISHIDA_2004_DOI)
  const [result, setResult] = useState<AgentResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  async function go() {
    setBusy(true)
    setError("")
    try {
      setResult(await runAgent({ action: "retraction_landed", doi: doi.trim(), depth: 2 }))
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The lookup did not finish.")
    } finally {
      setBusy(false)
    }
  }

  // One card per cited page: answers that cite the same page get the same fix, so they are counted on one card.
  const groups = new Map<string, { name: string; urls: string[]; count: number; path: string; rewrite: string; decision: string; recheck: string }>()
  for (const item of result?.affected_answers || []) {
    const key = (item.urls || []).join(" ") || item.answer_id || ""
    const found = groups.get(key)
    if (found) {
      found.count += item.count || 1
      continue
    }
    groups.set(key, {
      name: (item.urls || []).length ? (item.urls || []).map((url) => pageName(url)).join(", ") : "A pasted draft",
      urls: item.urls || [],
      count: item.count || 1,
      path: (item.path || "").split(" × ").map(relianceWord).join(" → "),
      rewrite: item.rewrite || "",
      decision: item.decision || "",
      recheck: (item as { recheck?: { decision?: string } }).recheck?.decision || "",
    })
  }
  const cards = Array.from(groups.values())
  const total = cards.reduce((sum, card) => sum + card.count, 0)
  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-ink-2">A paper was just retracted. Which answers already shipped rest on it?</p>
      <form
        className="flex items-center gap-2 rounded-2xl border border-hair bg-card-paper p-2 pl-5 shadow-[0_10px_30px_-18px_rgba(22,19,15,.35)]"
        onSubmit={(event) => {
          event.preventDefault()
          if (doi.trim()) void go()
        }}
      >
        <input
          value={doi}
          onChange={(event) => setDoi(event.target.value)}
          className="h-10 min-w-0 flex-1 bg-transparent font-mono text-sm outline-none"
          aria-label="Retracted paper DOI"
        />
        <button
          type="submit"
          disabled={!doi.trim() || busy}
          className="h-12 shrink-0 rounded-xl bg-ink px-4 text-[14px] font-semibold text-cream active:scale-95 disabled:opacity-40 sm:px-5 sm:text-[15px]"
        >
          {busy ? "Searching…" : "Find affected answers"}
        </button>
      </form>
      {error ? <p className="text-sm text-rx">{error}</p> : null}
      {result ? (
        <section className="flex flex-col gap-3" data-testid="alert-result">
          <h2 className="font-display text-[40px] leading-none" data-testid="alert-count">
            {cards.length} cited page{cards.length === 1 ? "" : "s"} rest{cards.length === 1 ? "s" : ""} on this paper
          </h2>
          <p className="text-[15px] text-ink-2">
            {total} stored answer{total === 1 ? "" : "s"} cite {cards.length === 1 ? "it" : "them"}. Each gets the same graph-checked fix.
          </p>
          {cards.map((card) => (
            <div key={card.urls.join(" ") || card.name} className="rounded-[20px] border border-hair bg-card-paper p-5 text-sm" data-testid="alert-card">
              <p className="font-display text-[24px] leading-tight">Answers citing {card.name}</p>
              <p className="mt-1 text-[13px] text-ink-2">
                {card.count} stored answer{card.count === 1 ? "" : "s"} · {card.decision === "block" ? "Don't ship" : card.decision === "warn" ? "Review" : card.decision}
                {card.path ? ` · path: page → ${card.path}` : ""}
              </p>
              {card.rewrite ? (
                <>
                  <p className="font-label mt-3 text-[10.5px] text-ink-2">Fix{card.recheck ? ` · checked again: ${card.recheck === "pass" ? "clear" : card.recheck}` : ""}</p>
                  <p className="mt-1 rounded-lg bg-clear-soft p-2 leading-6 text-ink">{card.rewrite}</p>
                </>
              ) : null}
            </div>
          ))}
          <p className="text-[11.5px] text-ink-2">
            The graph is walked backwards from the notice. {result.note}
          </p>
        </section>
      ) : null}
    </div>
  )
}
