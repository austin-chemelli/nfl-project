import fs from 'node:fs'
import path from 'node:path'
import { expect, it } from 'vitest'
import { Meta } from './contract'

// The bucket can hold a meta.json published by an older image (before tendency labels existed);
// the site must still load.
it('accepts meta.json without the tendency labels', () => {
  const meta = JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, '../test/fixtures/site/meta.json'), 'utf8'))
  delete meta.tendency_metrics
  delete meta.tendency_situations
  const parsed = Meta.parse(meta)
  expect(parsed.tendency_metrics).toEqual({})
})
