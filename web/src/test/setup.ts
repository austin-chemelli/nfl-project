import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// Without vitest globals, Testing Library can't register its own cleanup.
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
