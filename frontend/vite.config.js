import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],

  // Base URL — Flask serves SPA from root
  base: '/',

  build: {
    // Output goes into frontend/dist/ — served by Flask
    outDir: resolve(import.meta.dirname, 'dist'),
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        // Refactored to Function syntax for Vite 8 / Rolldown compatibility
        manualChunks(id) {
          if (id.includes('node_modules')) {
            // Group Socket.io separately
            if (id.includes('socket.io-client')) {
              return 'socket';
            }
            // Group React core libraries
            if (
              id.includes('react') || 
              id.includes('react-dom') || 
              id.includes('react-router-dom')
            ) {
              return 'vendor';
            }
          }
        },
      },
    },
  },

  server: {
    // Dev mode: proxy API calls to Flask on 5000
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