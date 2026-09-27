import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backendTarget = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: backendTarget, changeOrigin: true },
      '/health': { target: backendTarget, changeOrigin: true },
    },
  },
  preview: {
    port: 4173,
    strictPort: true,
    proxy: {
      '/api': { target: backendTarget, changeOrigin: true },
      '/health': { target: backendTarget, changeOrigin: true },
    },
  },
})
