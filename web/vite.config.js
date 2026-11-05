import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The console is served by the Python control plane at /, so assets are rooted
// at /assets. `npm run dev` proxies the API to the published control port.
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true },
  test: {
    environment: 'jsdom',
    setupFiles: ['./test/setup.js'],
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
