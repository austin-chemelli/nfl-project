import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup, configure } from '@testing-library/react'

// Routes load lazily: on a busy machine the first import can outrun findBy*'s 1 s default, which failed
// whole page suites at random. Only a test that is failing waits this long.
configure({ asyncUtilTimeout: 5000 })

// Without vitest globals, Testing Library can't register its own cleanup.
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
