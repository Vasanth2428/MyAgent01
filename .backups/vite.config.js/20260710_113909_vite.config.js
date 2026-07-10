import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  root: './nexus_ai/src',
  build: {
    outDir: '../dist',
  },

})
