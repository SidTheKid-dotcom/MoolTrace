"use client"

import { useMemo, useState } from "react"
import { cn } from "@/lib/utils"
import {
  buildPathGraph,
  hopTrailLine,
  type PathEdge,
  type PathNode,
  type PathReason,
} from "@/lib/path-diagram"

const NODE_W = 148
const NODE_H = 78
const GAP = 52
const PAD_X = 8
const PAD_Y = 24

function wrap(text: string, width = 19, maxLines = 2): string[] {
  const words = text.replace(/\s+/g, " ").trim().split(" ")
  const lines: string[] = []
  let current = ""
  for (const word of words) {
    const next = current ? `${current} ${word}` : word
    if (next.length > width && current) {
      lines.push(current)
      current = word
      if (lines.length === maxLines) break
    } else {
      current = next
    }
  }
  if (lines.length < maxLines && current) lines.push(current)
  if (lines.length === maxLines && words.join(" ").length > lines.join(" ").length) {
    const last = lines[maxLines - 1]
    lines[maxLines - 1] = last.length >= width ? `${last.slice(0, width - 1)}…` : last
  }
  return lines
}

function nodeFill(node: PathNode): string {
  if (node.kind === "Notice") {
    const label = node.label.toLowerCase()
    if (label.includes("retract") || label.includes("withdraw") || label.includes("removal")) {
      return "fill-destructive/15 stroke-destructive"
    }
    return "fill-secondary stroke-primary"
  }
  if (node.kind === "Source") return "fill-muted stroke-border"
  return "fill-card stroke-border"
}

function incoming(edges: PathEdge[], nodeId: string): PathEdge | undefined {
  return edges.find((edge) => edge.to === nodeId)
}

export function PathDiagram({ reason }: { reason: PathReason }) {
  const graph = useMemo(() => buildPathGraph(reason), [reason])
  const [selectedId, setSelectedId] = useState(() => graph.nodes.at(-1)?.id || graph.nodes[0]?.id || "")
  const selected = graph.nodes.find((node) => node.id === selectedId) || graph.nodes.at(-1)
  const inbound = selected ? incoming(graph.edges, selected.id) : undefined
  const width = PAD_X * 2 + graph.nodes.length * NODE_W + Math.max(0, graph.nodes.length - 1) * GAP
  const height = PAD_Y * 2 + NODE_H

  if (graph.nodes.length === 0) return null

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs font-medium tracking-wide text-muted-foreground">Deciding path</p>
      <div className="w-full">
        <svg
          role="img"
          aria-label="Citation path from the cited page to the publisher notice"
          viewBox={`0 0 ${width} ${height}`}
          className="h-auto w-full"
          preserveAspectRatio="xMidYMid meet"
        >
          {graph.edges.map((edge) => {
            const fromIndex = graph.nodes.findIndex((node) => node.id === edge.from)
            const toIndex = graph.nodes.findIndex((node) => node.id === edge.to)
            const x1 = PAD_X + fromIndex * (NODE_W + GAP) + NODE_W
            const x2 = PAD_X + toIndex * (NODE_W + GAP)
            const y = PAD_Y + NODE_H / 2
            const mid = (x1 + x2) / 2
            return (
              <g key={`${edge.from}-${edge.to}`}>
                <line x1={x1} y1={y} x2={x2} y2={y} className="stroke-border" strokeWidth={1.5} />
                <polygon
                  points={`${x2},${y} ${x2 - 7},${y - 4} ${x2 - 7},${y + 4}`}
                  className="fill-border"
                />
                <text
                  x={mid}
                  y={y - 8}
                  textAnchor="middle"
                  className="fill-muted-foreground"
                  style={{ fontSize: 10 }}
                >
                  {edge.label}
                  {edge.weight != null ? ` ${edge.weight}` : ""}
                </text>
              </g>
            )
          })}
          {graph.nodes.map((node, index) => {
            const x = PAD_X + index * (NODE_W + GAP)
            const y = PAD_Y
            const titleLines = wrap(node.label)
            const selectedNode = node.id === selected?.id
            return (
              <g
                key={node.id}
                transform={`translate(${x} ${y})`}
                role="button"
                tabIndex={0}
                aria-pressed={selectedNode}
                aria-label={`${node.kind}: ${node.title}`}
                className="cursor-pointer"
                onClick={() => setSelectedId(node.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault()
                    setSelectedId(node.id)
                  }
                }}
              >
                <rect
                  width={NODE_W}
                  height={NODE_H}
                  rx={10}
                  className={cn(
                    nodeFill(node),
                    selectedNode ? "stroke-ring stroke-2" : "stroke-1",
                  )}
                />
                <text x={12} y={16} className="fill-muted-foreground" style={{ fontSize: 9 }}>
                  {node.kind}
                </text>
                {titleLines.map((line, lineIndex) => (
                  <text
                    key={line}
                    x={12}
                    y={34 + lineIndex * 14}
                    className="fill-foreground"
                    style={{ fontSize: 11 }}
                  >
                    {line}
                  </text>
                ))}
                {node.sublabel ? (
                  <text
                    x={12}
                    y={NODE_H - 12}
                    className="fill-muted-foreground"
                    style={{ fontSize: 9 }}
                  >
                    {wrap(node.sublabel, 24, 1)[0]}
                  </text>
                ) : null}
              </g>
            )
          })}
        </svg>
      </div>
      {selected ? (
        <div className="rounded-md bg-muted px-3 py-2 text-sm">
          <p className="text-xs text-muted-foreground">
            {selected.kind}
            {inbound ? ` · ${inbound.label}` : ""}
            {inbound?.weight != null ? ` · weight ${inbound.weight}` : ""}
            {inbound?.evidence_from ? ` · ${inbound.evidence_from}` : ""}
          </p>
          <p className="mt-1 leading-6">{selected.title}</p>
          {selected.doi ? <p className="break-all text-xs text-muted-foreground">{selected.doi}</p> : null}
          {selected.url && !selected.doi ? (
            <p className="break-all text-xs text-muted-foreground">{selected.url}</p>
          ) : null}
          {inbound && hopTrailLine(inbound) ? (
            <p className="mt-1 break-all font-mono text-[11px] leading-5 text-muted-foreground">
              {hopTrailLine(inbound)}
            </p>
          ) : null}
          {inbound?.sentence ? <p className="mt-2 leading-6">{inbound.sentence}</p> : null}
        </div>
      ) : null}
    </div>
  )
}
