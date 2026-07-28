import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, proxy the backend API (farm/webapp/server.py on :8000) so the app can
// call same-origin /api/* with no CORS. Override the target with API_PROXY.
// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: process.env.API_PROXY ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
