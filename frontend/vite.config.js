import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],

  // Base URL — Flask serves SPA from root
  base: '/',

  build: {
    // Output goes into frontend/dist/ — served by Flask
    outDir: path.resolve(__dirname, 'dist'),
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          socket: ['socket.io-client'],
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
