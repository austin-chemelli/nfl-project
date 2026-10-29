/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import fs from 'node:fs'
import path from 'node:path'

// In `npm run dev` with no VITE_DATA_URL, serve the laptop's data/marts/site (and public/predictions)
// at the same paths the public bucket uses, so the app runs against local data with no cloud.
function localData(): Plugin {
  const dataRoot = process.env.NFL_DATA_ROOT ?? path.resolve(__dirname, '../data')
  const repoRoot = path.resolve(__dirname, '..')
  return {
    name: 'nfl-local-data',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/data', (req, res, next) => {
        const url = decodeURIComponent((req.url ?? '/').split('?')[0])
        // Only these two folders, after normalizing (blocks ../ and encoded traversal).
        const roots: [string, string][] = [
          ['/site/', path.join(dataRoot, 'marts', 'site')],
          ['/predictions/', path.join(repoRoot, 'public', 'predictions')],
        ]
        const hit = roots.find(([prefix]) => url.startsWith(prefix))
        const file = hit ? path.join(hit[1], url.slice(hit[0].length)) : null
        if (!hit || !file || !file.startsWith(hit[1] + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return next()
        res.setHeader('Content-Type', 'application/json')
        res.setHeader('Cache-Control', 'no-cache')
        fs.createReadStream(file).on('error', next).pipe(res)
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), localData()],
  build: { sourcemap: true, chunkSizeWarningLimit: 900 },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
