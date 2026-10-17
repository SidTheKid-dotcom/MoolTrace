"use client"

import Link from "next/link"
import { useEffect } from "react"
import { FIELD_SCAN } from "@/lib/field-scan"
import { MCP_URL, REPO_URL } from "@/lib/presets"

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border bg-card p-4">
      <p className="text-xs font-medium text-muted-foreground">
        {n} · {title}
      </p>
      {children}
    </div>
  )
}

export function Landing() {
  // Old links (/?preset=…) open the app directly.
  useEffect(() => {
    if (window.location.search.includes("preset=") || window.location.search.includes("url=")) {
      window.location.replace(`/app${window.location.search}`)
    }
  }, [])

  const flagged = FIELD_SCAN.filter((page) => page.flag)
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-16 px-5 py-6 sm:px-8">
      <header className="flex items-center justify-between">
        <span className="font-semibold tracking-tight">MoolTrace</span>
        <div className="flex items-center gap-4 text-sm">
          <a href={REPO_URL} className="text-muted-foreground hover:text-foreground">GitHub</a>
          <Link href="/app" className="rounded-xl bg-foreground px-4 py-2 font-medium text-background">
            Open the demo
          </Link>
        </div>
      </header>

      <section className="flex flex-col gap-6">
        <h1 className="max-w-3xl text-4xl font-semibold leading-[1.08] tracking-tight sm:text-5xl">
          Is your AI&apos;s answer resting on <span className="text-red-700">retracted research</span>?
        </h1>
        <p className="max-w-2xl text-lg text-muted-foreground">
          Health answers cite pages. Pages cite reviews. Reviews cite trials. MoolTrace follows every link and stops the
          answer if a trial underneath was retracted.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link href="/app?preset=harvard-vitamin-d" className="rounded-xl bg-foreground px-5 py-3 font-medium text-background">
            See it catch one →
          </Link>
          <Link href="/app?tab=agent" className="rounded-xl border px-5 py-3 font-medium">
            Try the agent
          </Link>
        </div>
      </section>

      <section className="flex flex-col gap-4" data-testid="field-scan">
        <h2 className="text-2xl font-semibold tracking-tight">
          <span className="text-red-700">{flagged.length} of {FIELD_SCAN.length}</span> Harvard nutrition pages rest on
          withdrawn or retracted research.
        </h2>
        <p className="-mt-2 text-muted-foreground">A citation checker passes all {FIELD_SCAN.length}.</p>
        <div className="grid grid-cols-7 gap-1.5 sm:grid-cols-[repeat(35,minmax(0,1fr))]">
          {FIELD_SCAN.map((page) => (
            <Link
              key={page.url}
              href={`/app?url=${encodeURIComponent(page.url)}`}
              title={`${page.name}${page.flag ? " — rests on withdrawn or retracted research" : ""}`}
              className={
                page.flag
                  ? "h-8 rounded-md bg-red-600 transition hover:scale-110"
                  : "h-8 rounded-md bg-muted transition hover:bg-zinc-300"
              }
            />
          ))}
        </div>
        <p className="text-sm text-muted-foreground">
          {flagged.map((page, index) => (
            <span key={page.url}>
              {index > 0 ? " · " : ""}
              <Link className="font-medium text-red-700 underline-offset-2 hover:underline" href={`/app?url=${encodeURIComponent(page.url)}`}>
                {page.name}
              </Link>
            </span>
          ))}
          {" "}· every page linked from Harvard&apos;s Vitamins &amp; Minerals index, checked 17 Oct 2026, each hit verified by hand.
        </p>
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        <Step n={1} title="Paste an answer">
          <div className="rounded-xl border px-3 py-2 text-sm text-muted-foreground">
            “Vitamin D prevents fractures — <span className="text-foreground">Harvard</span>”
          </div>
        </Step>
        <Step n={2} title="Follow the citations">
          <div className="flex items-center gap-1 text-xs">
            <span className="rounded-lg border px-2 py-1">Page</span>→<span className="rounded-lg border px-2 py-1">Review</span>→
            <span className="rounded-lg border border-red-200 bg-red-50 px-2 py-1 text-red-700">Retracted trial</span>
          </div>
        </Step>
        <Step n={3} title="Ship the fix">
          <div className="text-sm leading-6">
            <span className="text-red-800 line-through decoration-red-400">cites Harvard</span>{" "}
            <span className="bg-emerald-50 text-emerald-900">source removed: retracted 2025</span>
          </div>
        </Step>
      </section>

      <section className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-5">
          <p className="text-sm text-muted-foreground">Checking the answer&apos;s own citations</p>
          <p className="mt-1 text-xl font-semibold">✓ Looks fine</p>
        </div>
        <div className="rounded-2xl border border-red-200 bg-red-50/60 p-5">
          <p className="text-sm text-muted-foreground">Walking the citation graph 2 hops deep</p>
          <p className="mt-1 text-xl font-semibold text-red-700">✕ Don&apos;t ship</p>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Built for agents and pipelines</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl border bg-card p-4 text-sm">
            <p className="font-medium">Agents call it</p>
            <p className="mt-1 break-all font-mono text-[11px] text-muted-foreground">{MCP_URL}</p>
          </div>
          <div className="rounded-2xl border bg-card p-4 text-sm">
            <p className="font-medium">CI blocks the PR</p>
            <p className="mt-1 font-mono text-[11px] text-muted-foreground">clear 0 · review 2 · don&apos;t ship 1</p>
          </div>
          <div className="rounded-2xl border bg-card p-4 text-sm">
            <p className="font-medium">Retractions arrive later</p>
            <p className="mt-1 text-muted-foreground">Find every shipped answer that rests on the paper.</p>
          </div>
        </div>
      </section>

      <footer className="flex flex-wrap gap-x-4 gap-y-1 border-t pt-4 text-[11.5px] text-muted-foreground">
        <span>FalkorDB graph · WeMakeDevs × FalkorDB Graph Hacks, Track 01</span>
        <span>Not medical advice. An Expression of Concern is not a retraction.</span>
        <a className="underline" href={REPO_URL}>Code</a>
      </footer>
    </div>
  )
}
