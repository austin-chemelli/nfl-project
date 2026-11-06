import { scaleLinear } from 'd3-scale'

/** Game time on x, shared by `WpChart` and `PossessionStrip` so a drive sits under its stretch of the curve. */
export const WP_MARGIN = { l: 8, r: 10 }

export const timeScale = (width: number, endT: number) =>
  scaleLinear().domain([0, Math.max(1, endT)]).range([WP_MARGIN.l, width - WP_MARGIN.r])
