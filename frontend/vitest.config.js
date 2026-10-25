import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  test: {
    environment: 'jsdom',
    // Reuse one jsdom environment per worker instead of one per test file; the
    // default pool rebuilds it for all 50 files, which is half the suite's time.
    pool: 'vmThreads',
    globals: true,
    setupFiles: ['src/test-setup.js'],
    include: ['src/**/*.{test,spec}.js'],
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      reportsDirectory: './coverage',
      include: ['src/**/*.{js,vue}'],
      exclude: ['src/main.js', 'src/**/*.{test,spec}.js', 'src/__tests__/**']
    }
  }
})
