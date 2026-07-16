import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  root: './beezlebub/frontend',
  build: {
    outDir: '../dist',
    rollupOptions: {
      input: './nexus_ai/src/main.tsx',
    },
  },

})
