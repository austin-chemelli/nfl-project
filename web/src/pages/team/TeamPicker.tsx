import { useLocation, useNavigate } from 'react-router'
import { teamInfo } from '../../lib/teams'

/** Move between teams and stay on the same tab. */
export function TeamPicker({ code, codes }: { code: string; codes: string[] }) {
  const navigate = useNavigate()
  const { search } = useLocation()
  const sorted = [...codes].sort((a, b) => teamInfo(a).name.localeCompare(teamInfo(b).name))
  return (
    <label className="flex items-center gap-2 text-[13px] text-ink-3">
      Team
      <select
        value={code}
        onChange={(e) => navigate(`/team/${e.target.value}${search}`)}
        className="max-w-full rounded-md border border-line bg-surface-1 px-2 py-1 text-[13px] text-ink"
      >
        {sorted.map((c) => (
          <option key={c} value={c}>{teamInfo(c).name}</option>
        ))}
      </select>
    </label>
  )
}
