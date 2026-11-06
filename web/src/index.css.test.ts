import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8') // vitest runs from web/
const TOKENS = ['--dur-fast', '--dur-base', '--dur-slow', '--dur-draw', '--stagger']

/** The body of the first `{ ... }` block opened by `header`, with nesting balanced. */
function block(header: string): string {
  const start = css.indexOf(header)
  expect(start).toBeGreaterThanOrEqual(0)
  let depth = 0
  for (let i = css.indexOf('{', start); i < css.length; i++) {
    if (css[i] === '{') depth++
    else if (css[i] === '}' && --depth === 0) return css.slice(css.indexOf('{', start) + 1, i)
  }
  throw new Error('unbalanced')
}

describe('motion tokens', () => {
  it('defines every token and the easings', () => {
    for (const t of [...TOKENS, '--ease-out', '--ease-in-out']) expect(css).toMatch(new RegExp(`^\\s*${t}:`, 'm'))
  })

  it('reduced motion zeroes every duration and the stagger, and disables view transitions', () => {
    const rm = block('@media (prefers-reduced-motion: reduce)')
    for (const t of TOKENS) expect(rm).toMatch(new RegExp(`${t}:\\s*0ms`))
    expect(rm).toMatch(/::view-transition-group\(\*\)[^{]*\{\s*animation:\s*none/)
  })

  it('the pinned strip slides in on a token, so reduced motion shows it at once', () => {
    expect(css).toMatch(/\.pin-in\s*\{\s*animation:\s*pin-in var\(--dur-base\)/)
  })

  it('no animation or transition declaration uses a literal time', () => {
    const decl = /(?:^|[;{\s])((?:animation|transition)[\w-]*)\s*:([^;}]*)/g
    let found = 0
    for (const m of css.matchAll(decl)) {
      found++
      expect(m[2], `${m[1]}: ${m[2]}`).not.toMatch(/\d*\.?\d+m?s\b/)
    }
    expect(found).toBeGreaterThan(5)
  })
})
