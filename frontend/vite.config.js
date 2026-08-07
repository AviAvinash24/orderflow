import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/auth': 'http://localhost:8000',
      '/products': 'http://localhost:8000',
      '/orders': 'http://localhost:8000',
      '/webhooks': 'http://localhost:8000',
      '/me': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
