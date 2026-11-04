import type { ReactNode } from 'react'

/** Caveats and method notes, collapsed: one per page or tab (ADR 0017 text budget). */
export function FinePrint({ children, label = 'Fine print' }: { children: ReactNode; label?: string }) {
  return (
    <details className="mt-6 text-[13px] text-ink-2">
      <summary className="cursor-pointer text-ink-3 hover:text-ink">{label}</summary>
      <div className="mt-2 flex max-w-3xl flex-col gap-2">{children}</div>
    </details>
  )
}
