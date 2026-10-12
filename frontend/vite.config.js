import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

const API_TARGET = process.env.AGENTIC_API || 'http://127.0.0.1:8600'

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg', 'maskable.svg'],
      manifest: {
        name: 'Agentic',
        short_name: 'Agentic',
        description: 'Track work as tasks and collaborate with LLM coding agents.',
        theme_color: '#0f1115',
        background_color: '#0f1115',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        icons: [
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: 'maskable.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'maskable' }
        ]
      },
      workbox: {
        navigateFallbackDenylist: [/^\/api/],
        // Take over as soon as an update is available so fixed JS isn't served
        // from a stale precache.
        clientsClaim: true,
        skipWaiting: true,
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/api'),
            handler: 'NetworkOnly'
          }
        ]
      },
      devOptions: { enabled: false }
    })
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  server: {
    host: true, // bind 0.0.0.0 so the dev server is reachable remotely
    // Allow the local hostname and the Shopify dev environment's
    // `<project>.<owner>.dev.internal` (service and hydroxy proxy) hostnames.
    allowedHosts: ['squirtle', '.dev.internal'],
    port: 5173,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        // Keep SSE streams flowing through the dev proxy.
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            if ((proxyRes.headers['content-type'] || '').includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache'
            }
          })
        }
      }
    }
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
    sourcemap: false
  }
})
