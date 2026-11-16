import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The console is served by the Python control plane at /, so assets are rooted
// at /assets. `npm run dev` proxies the API to the published control port.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // Cloudscape is one large stylesheet and one large script by design; the
    // default 500 kB warning would fire on every build and tell us nothing.
    chunkSizeWarningLimit: 1500,
    // Vendor code changes far less often than the console's own pages. Naming
    // those chunks gives each of them a hash that survives a page edit, so one
    // changed component does not invalidate the whole 2 MB bundle in every
    // browser's cache.
    rollupOptions: {
      output: {
        /**
         * Rolldown (Vite 8) takes the function form, which is also what Rollup
         * accepts, so this stays portable if the bundler changes again.
         */
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('@cloudscape-design')) return 'cloudscape'
          if (id.includes('/react') || id.includes('/scheduler/')) return 'react'
          return 'vendor'
        },
      },
    },
  },
  test: {
    // One test tree for the whole repository: `tests/web` for the console,
    // `tests/s3` for the Python side. This config stays in `web/` because that is
    // where the dependencies are installed, and `tests/node_modules` points back
    // here so the suite resolves them from outside the package.
    root: fileURLToPath(new URL('..', import.meta.url)),
    include: ['tests/web/**/*.test.{js,jsx}'],
    environment: 'jsdom',
    setupFiles: [fileURLToPath(new URL('../tests/web/setup.js', import.meta.url))],
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:4570',
      '/login': 'http://127.0.0.1:4570',
      '/logout': 'http://127.0.0.1:4570',
      '/health': 'http://127.0.0.1:4570',
    },
  },
})
