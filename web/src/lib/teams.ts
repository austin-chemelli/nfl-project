/**
 * Team names and primary colors for the thin accent bar (ADR 0017; logos stay banned, ADR 0011).
 * Source: nflverse `teams_colors_logos` (`team_abbr`, `team_name`, `team_color`), fetched 2026-11-03.
 * Codes follow the site data (the Rams are "LA"); historical and alternate codes alias to the current franchise.
 */
export type TeamInfo = { name: string; color: string }

const TEAMS: Record<string, TeamInfo> = {
  ARI: { name: 'Arizona Cardinals', color: '#97233F' },
  ATL: { name: 'Atlanta Falcons', color: '#A71930' },
  BAL: { name: 'Baltimore Ravens', color: '#241773' },
  BUF: { name: 'Buffalo Bills', color: '#00338D' },
  CAR: { name: 'Carolina Panthers', color: '#0085CA' },
  CHI: { name: 'Chicago Bears', color: '#0B162A' },
  CIN: { name: 'Cincinnati Bengals', color: '#FB4F14' },
  CLE: { name: 'Cleveland Browns', color: '#FF3C00' },
  DAL: { name: 'Dallas Cowboys', color: '#002244' },
  DEN: { name: 'Denver Broncos', color: '#002244' },
  DET: { name: 'Detroit Lions', color: '#0076B6' },
  GB: { name: 'Green Bay Packers', color: '#203731' },
  HOU: { name: 'Houston Texans', color: '#03202F' },
  IND: { name: 'Indianapolis Colts', color: '#002C5F' },
  JAX: { name: 'Jacksonville Jaguars', color: '#006778' },
  KC: { name: 'Kansas City Chiefs', color: '#E31837' },
  LA: { name: 'Los Angeles Rams', color: '#003594' },
  LAC: { name: 'Los Angeles Chargers', color: '#007BC7' },
  LV: { name: 'Las Vegas Raiders', color: '#000000' },
  MIA: { name: 'Miami Dolphins', color: '#008E97' },
  MIN: { name: 'Minnesota Vikings', color: '#4F2683' },
  NE: { name: 'New England Patriots', color: '#002244' },
  NO: { name: 'New Orleans Saints', color: '#D3BC8D' },
  NYG: { name: 'New York Giants', color: '#0B2265' },
  NYJ: { name: 'New York Jets', color: '#003F2D' },
  PHI: { name: 'Philadelphia Eagles', color: '#004C54' },
  PIT: { name: 'Pittsburgh Steelers', color: '#000000' },
  SEA: { name: 'Seattle Seahawks', color: '#002244' },
  SF: { name: 'San Francisco 49ers', color: '#AA0000' },
  TB: { name: 'Tampa Bay Buccaneers', color: '#A71930' },
  TEN: { name: 'Tennessee Titans', color: '#4495D2' },
  WAS: { name: 'Washington Commanders', color: '#5A1414' },
}

const ALIAS: Record<string, string> = { LAR: 'LA', STL: 'LA', SD: 'LAC', OAK: 'LV', WSH: 'WAS', JAC: 'JAX' }

const FALLBACK: TeamInfo = { name: '', color: '#8a8984' }

/** The site's code for a franchise, whichever era's code it was given. */
export function canonicalTeam(code: string): string {
  const k = code.toUpperCase()
  return ALIAS[k] ?? k
}

/** Every franchise's current code. */
export const TEAM_CODES = Object.keys(TEAMS)

/** Whether a code, of any era, is a franchise. */
export const isTeam = (code: string) => canonicalTeam(code) in TEAMS

export function teamInfo(code: string | null | undefined): TeamInfo {
  if (!code) return { ...FALLBACK, name: 'Unknown' }
  const k = code.toUpperCase()
  return TEAMS[k] ?? TEAMS[ALIAS[k]] ?? { ...FALLBACK, name: code }
}

/**
 * Swap the two teams' full names for their codes in pipeline-written text ("Baltimore Ravens' offense" ->
 * "BAL's offense"). The page header already names the teams; spelled out four times a sentence they
 * made the retro's headlines the wordiest text on the page (ADR 0017 amendment 2026-11-08, rule 6).
 */
export function withCodes(text: string, codes: string[]): string {
  return codes.reduce((t, code) => {
    const name = teamInfo(code).name
    if (!name || name === code) return t
    return t.split(`${name}'s`).join(`${code}'s`).split(`${name}'`).join(`${code}'s`).split(name).join(code)
  }, text)
}
