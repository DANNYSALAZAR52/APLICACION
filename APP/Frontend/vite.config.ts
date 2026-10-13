import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// El backend corre en 127.0.0.1:8000. El proxy mantiene el mismo origen en desarrollo, por lo
// que la cookie de refresh (HttpOnly, SameSite=Strict) viaja sin configuración CORS adicional.
const api = { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } }

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5173, proxy: api },
  preview: { host: '127.0.0.1', port: 4173, proxy: api },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
