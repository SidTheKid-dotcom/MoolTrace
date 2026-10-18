"use client"

/* eslint-disable @next/next/no-img-element */
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react"
import { cn } from "@/lib/utils"

export type Tone = "neutral" | "red" | "amber" | "green"

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-ink",
  red: "text-rx",
  amber: "text-amber-x",
  green: "text-clear",
}

export function Pin({ color = "blue", className }: { color?: "blue" | "red"; className?: string }) {
  return (
    <img
      src={color === "red" ? "/img/pin-red.webp" : "/img/pin-blue.webp"}
      alt=""
      aria-hidden
      width={18}
      height={18}
      className={cn("pointer-events-none absolute -top-2 left-1/2 size-[18px] -translate-x-1/2 drop-shadow-[0_2px_2px_rgba(0,0,0,.35)]", className)}
    />
  )
}

export function Stamp({
  children,
  tone = "red",
  className,
  delay = 0,
  animate = true,
}: {
  children: ReactNode
  tone?: Tone
  className?: string
  delay?: number
  animate?: boolean
}) {
  return (
    <span
      className={cn("stamp whitespace-nowrap text-[13px]", TONE_TEXT[tone], animate && "stamp-in", className)}
      style={animate ? { animationDelay: `${delay}ms` } : undefined}
    >
      {children}
    </span>
  )
}

export function IndexCard({
  label,
  title,
  tone = "neutral",
  pin = "blue",
  stamp,
  stampDelay = 0,
  className,
  style,
  children,
  onClick,
  title_attr,
  size = "md",
}: {
  size?: "md" | "lg"
  label: string
  title: ReactNode
  tone?: Tone
  pin?: "blue" | "red" | null
  stamp?: ReactNode
  stampDelay?: number
  className?: string
  style?: CSSProperties
  children?: ReactNode
  onClick?: () => void
  title_attr?: string
}) {
  const Tag = onClick ? "button" : "div"
  return (
    <Tag
      type={onClick ? "button" : undefined}
      onClick={onClick}
      title={title_attr}
      style={style}
      className={cn(
        "paper-texture index-card relative block w-full rounded-[6px] px-4 pb-4 pt-4 text-left text-ink transition",
        onClick && "cursor-pointer hover:-translate-y-0.5 hover:shadow-lg focus-visible:outline-2 focus-visible:outline-ink",
        tone === "red" && "ring-1 ring-rx/25",
        tone === "amber" && "ring-1 ring-amber-x/25",
        className,
      )}
    >
      {pin ? <Pin color={pin} /> : null}
      <p className="font-label truncate text-[10.5px] text-ink-2">{label}</p>
      <div className={cn("font-display mt-1.5 line-clamp-2 leading-[1.1]", size === "lg" ? "text-[27px]" : "text-[21px]")}>{title}</div>
      {children}
      <div aria-hidden className="mt-3 flex flex-col gap-1.5">
        <span className="h-[5px] w-[82%] rounded-full bg-ink/10" />
        <span className="h-[5px] w-[64%] rounded-full bg-ink/10" />
      </div>
      {stamp ? (
        <span className="absolute -bottom-2 right-2">
          <Stamp tone={tone === "neutral" ? "red" : tone} delay={stampDelay}>
            {stamp}
          </Stamp>
        </span>
      ) : null}
    </Tag>
  )
}

/** A sagging twine thread between two cards. Draws itself in. */
export function Thread({
  tone = "neutral",
  label,
  vertical = false,
  delay = 0,
  className,
}: {
  tone?: "neutral" | "red" | "amber"
  label?: string
  vertical?: boolean
  delay?: number
  className?: string
}) {
  const stroke = tone === "red" ? "#d4351c" : tone === "amber" ? "#b7791f" : "#a99c84"
  const d = vertical ? "M10 0 C 16 20, 16 40, 10 60" : "M0 8 C 30 22, 70 22, 100 8"
  return (
    <div className={cn("relative flex shrink-0 items-center justify-center", vertical ? "h-14 w-full" : "w-20 lg:w-28", className)}>
      {label ? (
        <span
          className={cn(
            "absolute z-10 whitespace-nowrap font-mono text-[11px]",
            vertical ? "left-[calc(50%+14px)] top-1/2 -translate-y-1/2" : "-top-6 left-1/2 -translate-x-1/2",
            tone === "red" ? "text-rx" : tone === "amber" ? "text-amber-x" : "text-ink-2",
          )}
        >
          {label}
        </span>
      ) : null}
      <svg
        viewBox={vertical ? "0 0 20 60" : "0 0 100 30"}
        preserveAspectRatio="none"
        className={cn(vertical ? "h-full w-5" : "h-6 w-full")}
        aria-hidden
      >
        <path
          d={d}
          fill="none"
          stroke={stroke}
          strokeWidth={tone === "neutral" ? 1.6 : 2.4}
          strokeLinecap="round"
          pathLength={1}
          className="draw"
          style={{ animationDelay: `${delay}ms` }}
        />
      </svg>
    </div>
  )
}

/** Brass magnifier (Blender render) with a quote inside a semi-translucent lens.
 *  It drifts gently toward the pointer when the pointer comes near (off under reduced motion). */
export function Magnifier({ quote, size = 132, className }: { quote: string; size?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [offset, setOffset] = useState({ x: 0, y: 0, r: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
    let frame = 0
    const onMove = (event: PointerEvent) => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const r = el.getBoundingClientRect()
        const cx = r.left + r.width * 0.34
        const cy = r.top + r.height * 0.34
        const dx = event.clientX - cx
        const dy = event.clientY - cy
        const dist = Math.hypot(dx, dy)
        const reach = size * 1.9
        if (dist > reach) {
          setOffset({ x: 0, y: 0, r: 0 })
          return
        }
        const pull = (1 - dist / reach) * 0.16
        setOffset({ x: dx * pull, y: dy * pull, r: Math.max(-6, Math.min(6, dx * 0.03)) })
      })
    }
    const reset = () => setOffset({ x: 0, y: 0, r: 0 })
    window.addEventListener("pointermove", onMove, { passive: true })
    document.addEventListener("pointerleave", reset)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener("pointermove", onMove)
      document.removeEventListener("pointerleave", reset)
    }
  }, [size])
  return (
    <div
      ref={ref}
      className={cn("glide pointer-events-none relative", className)}
      style={{ width: size, height: size, animationDelay: "700ms" }}
      aria-label={`Evidence: ${quote}`}
      role="img"
    >
      <div
        className="absolute inset-0 transition-transform duration-300 ease-out"
        style={{ transform: `translate(${offset.x}px, ${offset.y}px) rotate(${offset.r}deg)` }}
      >
        <span
          aria-hidden
          className="absolute rounded-full backdrop-blur-[1.5px]"
          style={{
            left: "4%",
            top: "4%",
            width: "60%",
            height: "60%",
            background:
              "radial-gradient(circle at 38% 32%, rgba(255,253,247,.78) 0%, rgba(246,239,224,.62) 55%, rgba(226,214,190,.5) 100%)",
            boxShadow: "inset 0 0 18px rgba(255,255,255,.35), inset 0 -6px 14px rgba(120,96,60,.18)",
          }}
        />
        <img src="/img/magnifier.webp" alt="" className="absolute inset-0 size-full drop-shadow-[0_10px_14px_rgba(0,0,0,.35)]" />
        <span
          className="font-display absolute grid place-items-center text-center italic leading-tight text-ink [text-shadow:0_0_6px_rgba(255,250,240,.9)]"
          style={{ left: "8%", top: "8%", width: "52%", height: "52%", fontSize: Math.max(12, size * 0.095), padding: size * 0.04 }}
        >
          {quote}
        </span>
      </div>
    </div>
  )
}

/** Fade-and-rise when scrolled into view. */
export function Reveal({ children, className, delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setShown(true)
          io.disconnect()
        }
      },
      { threshold: 0.15 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <div ref={ref} className={cn("reveal", shown && "is-in", className)} style={{ transitionDelay: `${delay}ms` }}>
      {shown ? children : <div className="invisible">{children}</div>}
    </div>
  )
}
