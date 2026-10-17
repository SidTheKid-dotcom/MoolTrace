"use client"

import { useState } from "react"
import { runAgent, type AgentResult } from "@/lib/api"
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

  const answers = result?.affected_answers || []
  const total = answers.reduce((sum, item) => sum + (item.count || 1), 0)
  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-muted-foreground">A paper was just retracted. Which answers already shipped rest on it?</p>
      <form
        className="flex items-center gap-2 rounded-2xl border bg-card p-2 pl-4 shadow-sm"
        onSubmit={(event) => {
          event.preventDefault()
          if (doi.trim()) void go()
        }}
      >
        <input
          value={doi}
          onChange={(event) => setDoi(event.target.value)}
          className="h-10 flex-1 bg-transparent font-mono text-sm outline-none"
          aria-label="Retracted paper DOI"
        />
        <button
          type="submit"
          disabled={!doi.trim() || busy}
          className="h-10 rounded-xl bg-foreground px-4 text-sm font-medium text-background disabled:opacity-40"
        >
          {busy ? "Searching…" : "Find affected answers"}
        </button>
      </form>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {result ? (
        <section className="flex flex-col gap-3" data-testid="alert-result">
          <h2 className="text-xl font-semibold tracking-tight">
            {total} shipped answer{total === 1 ? "" : "s"} rest on this paper
          </h2>
          {answers.map((item, index) => (
            <div key={`${item.answer_id}-${index}`} className="rounded-2xl border bg-card p-4 text-sm">
              <p className="text-xs text-muted-foreground">
                {item.count && item.count > 1 ? `${item.count} answers · ` : ""}
                {(item.urls || []).join(" ") || "answer"} · {item.path}
              </p>
              {item.rewrite ? <p className="mt-2 rounded-lg bg-emerald-50 p-2 leading-6 text-emerald-900">{item.rewrite}</p> : null}
            </div>
          ))}
          <p className="text-[11.5px] text-muted-foreground">
            The graph is walked backwards from the notice. {result.note}
          </p>
        </section>
      ) : null}
    </div>
  )
}
