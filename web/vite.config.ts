import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// The MKC API has no CORS configuration, so in development the Vite dev
// server proxies /api/v1 and /healthz to the local API. For production
// static serving, set VITE_MKC_API_URL (or use the Settings base-URL field).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/healthz': 'http://127.0.0.1:8000',
      '/metrics': 'http://127.0.0.1:8000',
    },
  },
  preview: { port: 4173 },
})
