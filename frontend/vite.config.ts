import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
  ],
  server: {
    proxy: {
      // Inference service — strip the /api prefix before forwarding
      '/api': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      // Event producer — forward /events directly (no prefix strip needed)
      '/events': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})
