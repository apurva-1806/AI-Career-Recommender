import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development, /api requests are proxied to the FastAPI server so the browser
// talks to a single origin. Set VITE_API_URL to call a different backend directly.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000', changeOrigin: true },
    },
  },
})
