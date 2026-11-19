
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: { codeSplitting: { groups: [{ name: 'translations', test: /i18n[\\/]messages\.json/ }, { name: 'react', test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/ }] } },
    },
  },

  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        // QA/e2e runs a separate backend (VITE_API_TARGET); the default stays the dev server.
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
