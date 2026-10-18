"use client"

import type { Check } from "@/lib/api"

/** The real query that decided the verdict, trimmed to the algo.SPpaths call, with the full text one click away. */
export function CypherPanel({ check, open = false }: { check: Check; open?: boolean }) {
  const full = check.why_graph?.cypher || check.algorithm?.cypher || (check as unknown as { cypher?: string }).cypher || ""
  if (!full) return null
  const lines = full.split("\n")
  const start = lines.findIndex((line) => line.includes("algo.SPpaths"))
  const call = start >= 0 ? lines.slice(Math.max(0, start - 3), start + 2).join("\n") : lines.slice(0, 5).join("\n")
  return (
    <div className="rounded-xl border border-hair bg-paper/70 p-4" data-testid="cypher-panel">
      <p className="font-label text-[10.5px] text-ink-2">The query that decided this · FalkorDB algo.SPpaths</p>
      <pre className="mt-2 overflow-x-auto whitespace-pre font-mono text-[11.5px] leading-[1.55] text-ink">{call.trim()}</pre>
      <details className="mt-2" open={open}>
        <summary className="cursor-pointer text-[12.5px] text-ink-2 underline underline-offset-2">Full query</summary>
        <pre className="mt-2 overflow-x-auto whitespace-pre font-mono text-[11px] leading-[1.55] text-ink">{full}</pre>
      </details>
    </div>
  )
}
