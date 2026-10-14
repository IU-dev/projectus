import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/static/frontend/',
  build: {
    outDir: 'static/frontend',
    emptyOutDir: true,
    rollupOptions: {
      input: 'frontend/main.js',
      output: { entryFileNames: 'app.js', assetFileNames: '[name][extname]' },
    },
  },
})
