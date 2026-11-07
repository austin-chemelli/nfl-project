import type { ReactNode } from 'react'

/** A section of a team tab: a quiet heading, at most one line, then the content. */
export function Block({ title, line, children }: { title: string; line?: ReactNode; children: ReactNode }) {
  return (
    <section aria-label={title} className="flex min-w-0 flex-col gap-2">
      <h3 className="text-[15px] font-medium text-ink">{title}</h3>
      {line && <p className="m-0 text-ink-2">{line}</p>}
      {children}
    </section>
  )
}
