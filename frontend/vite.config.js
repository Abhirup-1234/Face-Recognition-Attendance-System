import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],

  base: '/',

  build: {
    outDir: resolve(import.meta.dirname, 'dist'),
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        // Vite 8 / Rolldown requires manualChunks as a function, not an object
        manualChunks(id) {
          if (id.includes('socket.io-client') || id.includes('engine.io-client')) {
            return 'socket'
          }
          if (id.includes('node_modules')) {
            return 'vendor'
          }
        },
      },
    },
  },

  server: {
    proxy: {
      '/api':      'http://127.0.0.1:5000',
      '/stream':   'http://127.0.0.1:5000',
      '/snapshot': 'http://127.0.0.1:5000',
      '/reports':  'http://127.0.0.1:5000',
      '/login':    'http://127.0.0.1:5000',
      '/logout':   'http://127.0.0.1:5000',
    },
  },
})
