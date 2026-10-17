"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { AgentTab } from "@/components/app/agent-tab"
import { AlertTab } from "@/components/app/alert-tab"
import { CheckTab } from "@/components/app/check-tab"
import type { Input } from "@/lib/api"
import { EXAMPLES, MCP_URL, REPO_URL } from "@/lib/presets"
import { cn } from "@/lib/utils"

const TABS = [
  { id: "check", label: "Check" },
  { id: "agent", label: "Agent" },
  { id: "alert", label: "Retraction alert" },
] as const
type TabId = (typeof TABS)[number]["id"]

export function AppShell() {
  const [tab, setTab] = useState<TabId>("check")
  const [initial, setInitial] = useState<{ input: Input } | undefined>(undefined)

  function applyQuery() {
    const params = new URLSearchParams(window.location.search)
    const wanted = params.get("tab") as TabId | null
    if (wanted && TABS.some((item) => item.id === wanted)) setTab(wanted)
    const depth = Number(params.get("depth")) || undefined
    const url = params.get("url")
    const preset = EXAMPLES.find((item) => item.id === (params.get("preset") || "harvard-vitamin-d"))
    if (url) {
      setInitial({ input: { text: "", urls: [url], engine: "nutrition-coach", depth: depth || 2 } })
    } else if (preset && (!wanted || wanted === "check")) {
      setInitial({ input: { text: preset.text, urls: preset.urls, engine: preset.engine, depth: depth || preset.depth } })
    }
  }

  // Read the URL once on mount (?tab=, ?preset=, ?url=, ?depth=).
  useEffect(() => {
    void Promise.resolve().then(applyQuery)
  }, [])

  function select(id: TabId) {
    setTab(id)
    const params = new URLSearchParams(window.location.search)
    params.set("tab", id)
    window.history.replaceState(null, "", `?${params.toString()}`)
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-6 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/" className="font-semibold tracking-tight">
          MoolTrace <span className="font-normal text-muted-foreground">· check the roots</span>
        </Link>
        <nav className="flex rounded-xl bg-muted p-1 text-sm" role="tablist">
          {TABS.map((item) => (
            <button
              key={item.id}
              role="tab"
              aria-selected={tab === item.id}
              onClick={() => select(item.id)}
              className={cn(
                "rounded-lg px-3 py-1.5 font-medium text-muted-foreground transition",
                tab === item.id && "bg-card text-foreground shadow-sm",
              )}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      <main>
        <div hidden={tab !== "check"}>
          <CheckTab initial={initial} />
        </div>
        <div hidden={tab !== "agent"}>
          <AgentTab />
        </div>
        <div hidden={tab !== "alert"}>
          <AlertTab />
        </div>
      </main>

      <footer className="mt-auto flex flex-wrap gap-x-4 gap-y-1 border-t pt-4 text-[11.5px] text-muted-foreground">
        <span>Not medical advice. An Expression of Concern is not a retraction. Clear ≠ medically correct.</span>
        <a className="underline" href={REPO_URL}>Code</a>
        <span title={MCP_URL}>MCP: /mcp</span>
        <Link className="underline" href="/classic">Classic view</Link>
      </footer>
    </div>
  )
}
