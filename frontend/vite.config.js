import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite';
import { resolve } from 'pathe';
const root = process.cwd();

const USE_PROXY = process.env.USE_PROXY === 'true'
// Site reached through Caddy on the Mac (see frappe.local route)
const FRAPPE_URL = process.env.FRAPPE_URL || 'https://frappe.local'

export default defineConfig(({ command }) => ({
  resolve: {
    extensions: ['.js', '.jsx', '.ts', '.tsx', '.d.ts'],
    dedupe: ['react', 'react-dom'],
    alias: {
      '@': resolve(root, './src'),
      "@c": resolve(root, './src/components'),
    }
  },
  define: {
    // build timestamp, logged at startup (RestaurantContext)
    __RM_BUILD__: JSON.stringify(new Date().toISOString()),
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
  // Built files are served by Frappe from /assets/restaurant_management/dist/
  base: command === 'build' ? '/assets/restaurant_management/dist/' : '/',
  build: {
    rollupOptions: {
      output: {
        // Classic script wrapped in an IIFE: Frappe evaluates it with
        // frappe.require, so it must not leak top-level vars into window.
        format: 'iife',
        entryFileNames: 'js/restaurant.js',
        chunkFileNames: 'js/[name].js',
        assetFileNames: 'css/[name].[ext]'
      }
    },
    outDir: '../restaurant_management/public/dist',
    emptyOutDir: true
  }
}))
