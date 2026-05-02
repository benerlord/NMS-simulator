import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backend = process.env.VITE_BACKEND ?? 'https://localhost:8080'
const backendIsHttps = backend.startsWith('https://')

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/admin/api': {
        target: backend,
        changeOrigin: true,
        secure: !backendIsHttps,
      },
      '/admin/ws': {
        target: backend,
        changeOrigin: true,
        ws: true,
        secure: !backendIsHttps,
      },
    },
  },
})
