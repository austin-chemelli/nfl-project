/**
 * Save the sliders as the reader's approach ("You"), rename it, make it the default line, share it,
 * or remove it (ADR 0034). One saved approach per browser.
 */
import { useState } from 'react'
import { Link } from 'react-router'
import { Card } from '../../components/ui'
import type { CustomMeta, DiyMatrix } from '../../data/contract'
import { encodeWeights, normalize, type GroupWeights } from '../../diy'
import { calibrate, capLive, LIVE_CAP, LIVE_ONLY, youWeights } from '../../you/line'
import { clearSaved, DEFAULT_NAME, NAME_MAX, saveApproach, setDefault, updateSaved, useSaved } from '../../you/store'

const same = (a: GroupWeights, b: GroupWeights) => {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  for (const k of keys) if ((a[k] ?? 0) !== (b[k] ?? 0)) return false
  return true
}

export function SavePanel({ points, matrix, custom, onLoad }: {
  points: GroupWeights
  matrix: DiyMatrix
  custom: CustomMeta | null
  onLoad: (p: GroupWeights) => void
}) {
  const saved = useSaved()
  const [name, setName] = useState(saved?.name ?? DEFAULT_NAME)
  const [copied, setCopied] = useState(false)
  const live = custom?.live_only ?? LIVE_ONLY
  const [cappedPoints, liveCapped] = capLive(points, live)
  const total = normalize(cappedPoints).total
  const key = (matrix as { key?: string }).key
  const canSave = custom != null && total > 0 && key === custom.key
  const dirty = saved != null && !same(saved.points, points)

  const save = () => {
    if (!custom || !canSave) return
    const calib = { key: custom.key, ...calibrate(youWeights(points, live), matrix, custom.trained_through + 1) }
    saveApproach({ name, points, registry: custom.registry_version, groups: custom.groups, calib })
  }
  const share = async () => {
    const url = `${window.location.origin}/build?w=${encodeWeights(points)}`
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      window.prompt('Copy this link', url)
    }
  }

  return (
    <Card>
      <h2 className="text-lg font-semibold">Your approach</h2>
      <p className="text-[13px] text-ink-2">
        Save these weights and they appear as a line of their own beside the approaches on the slate, every game, the tracker and the recap. Kept in this browser only.
      </p>
      <label className="mt-3 flex flex-col gap-1 text-[13px] text-ink-2">
        Name
        <input
          value={name}
          maxLength={NAME_MAX}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => saved && updateSaved({ name })}
          className="rounded-md border border-line bg-surface-1 px-2 py-1 text-[14px] text-ink"
        />
      </label>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!canSave || (saved != null && !dirty && saved.name === name)}
          onClick={save}
          className="rounded-md border border-line bg-accent/15 px-3 py-1.5 text-[14px] font-medium hover:bg-accent/25 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saved ? 'Update my approach' : 'Save as my approach'}
        </button>
        <button type="button" onClick={share} disabled={total === 0} className="rounded-md border border-line bg-surface-1 px-3 py-1.5 text-[14px] hover:bg-surface-2 disabled:opacity-50">
          {copied ? 'Link copied' : 'Copy a link to these weights'}
        </button>
      </div>
      {liveCapped && (
        <p className="mt-2 text-[13px] text-ink-3">
          Your saved line holds Market behavior and Buzz to {Math.round(LIVE_CAP * 100)}% of its budget together: they have no history, so the rest of your weights set how confident the line is.
        </p>
      )}
      {total === 0 && Object.values(points).some((v) => v !== 0) && (
        <p className="mt-2 text-[13px] text-ink-3">A line needs some weight on a group with history before it can be saved.</p>
      )}
      {!canSave && total > 0 && <p className="mt-2 text-[13px] text-ink-3">Saving needs this season's data; try again after the next update.</p>}
      {saved && (
        <div className="mt-4 flex flex-col gap-2 border-t border-line pt-3 text-[14px]">
          <p className="m-0 text-ink-2">
            Saved {new Date(saved.saved_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            {dirty ? '. The sliders differ from it: update to keep these.' : '.'}
            {dirty && (
              <>
                {' '}
                <button type="button" onClick={() => onLoad(saved.points)} className="text-accent underline-offset-2 hover:underline">Back to the saved weights</button>
              </>
            )}
          </p>
          <label className="inline-flex items-start gap-2">
            <input type="checkbox" checked={saved.is_default} onChange={(e) => setDefault(e.target.checked)} className="mt-1" />
            <span>
              Make it my default: pages lead with your line instead of the Student's (the pick on the slate, each game's summary, the tracker). A bar at the top says so, with a way back.
            </span>
          </label>
          <p className="m-0 text-[13px] text-ink-3">
            See it on <Link to="/">this week's slate</Link> and the <Link to="/tracker?tab=you">tracker</Link>.{' '}
            <button type="button" onClick={() => window.confirm('Remove your saved approach from this browser?') && clearSaved()} className="text-ink-3 underline-offset-2 hover:text-ink hover:underline">
              Remove it
            </button>
          </p>
        </div>
      )}
    </Card>
  )
}
