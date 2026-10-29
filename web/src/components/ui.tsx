/** Small shared building blocks. Pages compose these; keep page-specific UI in the page. */
import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { colorVar, SHORT } from '../lib/models'
import { pct } from '../lib/format'
import { Help } from './Help'

export function Page({ title, lede, children }: { title: string; lede?: ReactNode; children: ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {lede && <p className="mt-1 max-w-3xl text-ink-2">{lede}</p>}
      <div className="mt-6 flex flex-col gap-8">{children}</div>
    </div>
  )
}

export function Section({ title, help, aside, children }: { title: string; help?: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">
          <Help text={help}>{title}</Help>
        </h2>
        {aside}
      </div>
      {children}
    </section>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-lg border border-line bg-surface-1 p-4 ${className}`}>{children}</div>
}

/** A single number with a label; `sub` is the comparison that gives it meaning. */
export function StatTile({ label, value, sub, help }: { label: string; value: ReactNode; sub?: ReactNode; help?: string }) {
  return (
    <Card>
      <div className="text-[13px] text-ink-3">
        <Help text={help}>{label}</Help>
      </div>
      <div className="tabular mt-1 text-2xl font-semibold">{value}</div>
      {sub && <div className="mt-1 text-[13px] text-ink-2">{sub}</div>}
    </Card>
  )
}

export function Swatch({ modelId, size = 10 }: { modelId: string; size?: number }) {
  return <span aria-hidden className="inline-block shrink-0 rounded-full" style={{ width: size, height: size, background: colorVar(modelId) }} />
}

export function ModelBadge({ modelId, label }: { modelId: string; label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <Swatch modelId={modelId} />
      {label ?? SHORT[modelId] ?? modelId}
    </span>
  )
}

const STATUS: Record<string, { text: string; cls: string; help: string }> = {
  locked: { text: 'Locked', cls: 'border-[var(--good)] text-[var(--good)]', help: 'Committed to the public repo before kickoff; this is the scored pick.' },
  backfill: { text: 'Backfill', cls: 'border-line text-ink-3', help: 'Computed after the fact with data as of a synthetic lock; not part of the live record.' },
  preview: { text: 'Preview', cls: 'border-[var(--warning)] text-ink-2', help: 'Current estimate, not yet locked. It can still change.' },
}
export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { text: status, cls: 'border-line text-ink-3', help: '' }
  return (
    <span title={s.help} className={`inline-block rounded border px-1.5 py-px text-[11px] font-medium uppercase tracking-wide ${s.cls}`}>
      {s.text}
    </span>
  )
}

/** Favored team and its probability: "GB 64%". */
export function ProbCell({ pHome, home, away }: { pHome: number | null | undefined; home: string; away: string }) {
  if (pHome == null) return <span className="text-ink-3">–</span>
  const homeFav = pHome >= 0.5
  return (
    <span className="tabular whitespace-nowrap">
      <span className="font-medium">{homeFav ? home : away}</span> {pct(homeFav ? pHome : 1 - pHome)}
    </span>
  )
}

export function Loading({ what = 'data' }: { what?: string }) {
  return <div className="py-12 text-center text-ink-3" role="status">Loading {what}…</div>
}

export function ErrorBox({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error)
  return (
    <div role="alert" className="rounded-lg border border-[var(--critical)] bg-surface-1 p-4 text-ink-2">
      <div className="font-medium text-ink">Couldn't load this page's data.</div>
      <div className="mt-1 text-[13px]">{msg}</div>
    </div>
  )
}

/** Render children once a query has data; loading and error states are uniform across pages. */
export function Loaded<T>({ q, what, children }: { q: UseQueryResult<T>; what?: string; children: (data: T) => ReactNode }) {
  if (q.isPending) return <Loading what={what} />
  if (q.isError) return <ErrorBox error={q.error} />
  return <>{children(q.data)}</>
}

/** Horizontal scroll wrapper so wide tables never widen the page on phones. */
export function TableScroll({ children }: { children: ReactNode }) {
  return <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">{children}</div>
}

export const th = 'border-b border-line px-2 py-1.5 text-left text-[12px] font-medium uppercase tracking-wide text-ink-3'
export const td = 'border-b border-line px-2 py-1.5 align-top'

/** Segmented control for 2–5 mutually exclusive views. */
export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line bg-surface-1 p-0.5 text-[13px]">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`rounded px-2.5 py-1 ${o.value === value ? 'bg-surface-2 font-medium text-ink' : 'text-ink-2 hover:text-ink'}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** "Show the numbers": a disclosure holding the table behind a chart. */
export function DataTable({ summary = 'Show the numbers', children }: { summary?: string; children: ReactNode }) {
  return (
    <details className="mt-3 text-[13px]">
      <summary className="cursor-pointer text-ink-2 hover:text-ink">{summary}</summary>
      <div className="mt-2">
        <TableScroll>{children}</TableScroll>
      </div>
    </details>
  )
}
