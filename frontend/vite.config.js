import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite';
import { resolve } from 'pathe';
const root = process.cwd();

const USE_PROXY = process.env.USE_PROXY === 'true'
// Site reached through Caddy on the Mac (see frappe.local route)
const FRAPPE_URL = process.env.FRAPPE_URL || 'https://frappe.local'

// `vite build --mode guest` builds the guest ordering page (www/order.html) on its own:
// js/guest.js, next to restaurant.js (the POS bundle is built first and empties the folder).
export default defineConfig(({ command, mode }) => ({
  resolve: {
    extensions: ['.js', '.jsx', '.ts', '.tsx', '.d.ts'],
    dedupe: ['react', 'react-dom'],
    alias: {
      '@': resolve(root, './src'),
      "@c": resolve(root, './src/components'),
    }
  },
  plugins: [
    tailwindcss(),
    react()
  ],
  server: {
    port: 5173,
    proxy: USE_PROXY ? {
      '/api': { target: FRAPPE_URL, changeOrigin: true, secure: false },
      '/assets': { target: FRAPPE_URL, changeOrigin: true, secure: false },
      '/files': { target: FRAPPE_URL, changeOrigin: true, secure: false },
      '/socket.io': { target: FRAPPE_URL, changeOrigin: true, secure: false, ws: true },
    } : {}
  },
  // Built files are served by Frappe from /assets/renpos/dist/
  base: command === 'build' ? '/assets/renpos/dist/' : '/',
  build: {
    rollupOptions: {
      // the entry is the script itself (no index.html in the build output)
      input: resolve(root, mode === 'guest' ? './src/guest/main.jsx' : './src/main.jsx'),
      output: {
        // Classic script wrapped in an IIFE: Frappe evaluates it with
        // frappe.require, so it must not leak top-level vars into window.
        format: 'iife',
        entryFileNames: mode === 'guest' ? 'js/guest.js' : 'js/restaurant.js',
        chunkFileNames: 'js/[name].js',
        assetFileNames: 'css/[name].[ext]'
      }
    },
    outDir: '../renpos/public/dist',
    emptyOutDir: mode !== 'guest'
  }
}))
