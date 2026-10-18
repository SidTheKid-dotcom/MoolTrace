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
    <div className="min-h-full flex-1 bg-paper text-ink">
      <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-8 px-5 py-6 sm:px-8">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-hair pb-4">
          <Link href="/" className="font-mono text-[22px] tracking-tight text-ink">
            mooltrace
          </Link>
          <nav className="flex gap-6 text-[16px]" role="tablist">
            {TABS.map((item) => (
              <button
                key={item.id}
                role="tab"
                aria-selected={tab === item.id}
                onClick={() => select(item.id)}
                className={cn(
                  "relative pb-2 text-ink-2 transition hover:text-ink",
                  tab === item.id && "font-semibold text-ink after:absolute after:inset-x-0 after:-bottom-[17px] after:h-[2px] after:bg-ink",
                )}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <Link href="/" className="hidden text-[14px] text-ink-2 hover:text-ink sm:block">
            How it works
          </Link>
        </header>

        <main>
          <h1 className="sr-only">
            MoolTrace pre-ship check · {TABS.find((item) => item.id === tab)?.label}
          </h1>
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

        <footer className="mt-10 flex flex-wrap gap-x-5 gap-y-1 border-t border-hair pt-4 text-[12px] text-ink-2">
          <span>Not medical advice. An Expression of Concern is not a retraction. Clear is not a medical-accuracy check.</span>
          <a className="underline underline-offset-2" href={REPO_URL}>Code</a>
          <span title={MCP_URL} className="font-mono">MCP · /mcp</span>
        </footer>
      </div>
    </div>
  )
}
