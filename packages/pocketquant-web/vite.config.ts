import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'

export default defineConfig({
  plugins: [TanStackRouterVite({ quoteStyle: 'single' }), react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:41921',
        changeOrigin: true,
        // SSE streams require no buffering — pass headers through immediately
        headers: { Connection: 'keep-alive' },
      },
    },
  },
})
