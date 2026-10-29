import { useState } from 'react'
import { DotWhisker } from '../../charts'
import { Card, Section } from '../../components/ui'
import { Help } from '../../components/Help'
import type { Hypotheses } from '../../data/contract'
import { filterFeatures, groupLabel, pp, sortFeatures, UNGROUPED, VERDICTS, VERDICT_COLOR, VERDICT_NOTE, verdictCounts, type Feature } from './helpers'

const SELECT = 'rounded-md border border-line bg-surface-1 px-2 py-1 text-[13px] text-ink'

function VerdictBadge({ verdict }: { verdict: string }) {
  return (
    <span title={VERDICT_NOTE[verdict]} className="inline-flex items-center gap-1.5 rounded border border-line px-1.5 py-px text-[11px] font-medium uppercase tracking-wide text-ink-2">
      <span aria-hidden className="inline-block h-2 w-2 rounded-full" style={{ background: VERDICT_COLOR[verdict] ?? 'var(--border)' }} />
      {verdict}
    </span>
  )
}

function FeatureCard({ f, group }: { f: Feature; group: string }) {
  return (
    <Card className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-medium">
          <Help text={f.description}>{f.label}</Help>
          <span className="ml-2 text-[13px] font-normal text-ink-3">{group}</span>
        </div>
        <VerdictBadge verdict={f.verdict} />
      </div>
      <p className="text-ink-2">{f.sentence}</p>
      <div className="tabular text-[13px] text-ink-2">
        After the others {pp(f.effect_pp)} pts (90% range {pp(f.effect_lo_pp)} to {pp(f.effect_hi_pp)}); on its own {pp(f.marginal_pp)} pts.
      </div>
      <div className="text-[13px] text-ink-3">{f.coverage}</div>
      <div className="text-[13px] text-ink-3">
        Personas that lean on it: {f.personas.length ? f.personas.map((p) => p.name).join(', ') : '–'}
      </div>
    </Card>
  )
}

export function Effects({ h, groupName }: { h: Hypotheses; groupName: (id: string) => string | undefined }) {
  const [group, setGroup] = useState('')
  const [verdict, setVerdict] = useState('')
  const feats = h.features
  const groups = [...new Set(feats.map((f) => groupLabel(f, groupName)))].sort((a, b) => Number(a === UNGROUPED) - Number(b === UNGROUPED) || a.localeCompare(b))
  const shown = sortFeatures(filterFeatures(feats, groupName, group, verdict), groupName)
  const counts = verdictCounts(feats)

  return (
    <Section
      title="Effect of each feature"
      help="Change in the home team's win probability, in points, when the feature is one standard deviation better for the home side than the away side, at a pick'em game."
    >
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-[13px] text-ink-3">
          Group
          <select className={SELECT} value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="">All groups</option>
            {groups.map((g) => <option key={g}>{g}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[13px] text-ink-3">
          Verdict
          <select className={SELECT} value={verdict} onChange={(e) => setVerdict(e.target.value)}>
            <option value="">All verdicts</option>
            {VERDICTS.map((v) => <option key={v}>{v}</option>)}
          </select>
        </label>
        <p className="text-[13px] text-ink-3">
          {feats.length} features: {VERDICTS.map((v) => `${counts[v]} ${v}`).join(', ')}. Showing {shown.length}.
        </p>
      </div>
      {shown.length === 0 ? (
        <p className="text-ink-2">No features match these filters.</p>
      ) : (
        <>
          <Card>
            <DotWhisker
              rows={shown.map((f) => ({
                key: f.feature,
                label: `${groupLabel(f, groupName)} · ${f.label}`,
                value: f.effect_pp,
                lo: f.effect_lo_pp,
                hi: f.effect_hi_pp,
                color: VERDICT_COLOR[f.verdict],
                title: `${f.label}: ${pp(f.effect_pp)} pts (90% range ${pp(f.effect_lo_pp)} to ${pp(f.effect_hi_pp)}), ${f.verdict}. ${f.description ?? ''}`,
              }))}
              format={(v) => pp(v, 1)}
              refLabel="No effect"
              leftLabel="favors the away side"
              rightLabel="favors the home side"
              labelWidth={250}
            />
            <p className="mt-2 text-[13px] text-ink-3">
              Points of win probability per +1 SD edge, with the 90% range. Rows are grouped by feature group, largest effect first. Blue = matters, gray = weak, pale = no evidence; the verdict is written out in the list below.
            </p>
          </Card>
          <ul className="mt-4 grid gap-3 md:grid-cols-2">
            {shown.map((f) => (
              <li key={f.feature}>
                <FeatureCard f={f} group={groupLabel(f, groupName)} />
              </li>
            ))}
          </ul>
        </>
      )}
    </Section>
  )
}
