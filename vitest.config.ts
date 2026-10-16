import { fileURLToPath, URL } from 'node:url'
import { configDefaults, defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'happy-dom',
    globals: true,
    clearMocks: true,     // resets call history before each test
    restoreMocks: false,  // do NOT unstub vi.stubGlobal between tests
    setupFiles: ['./src/__tests__/setup.ts'],
    // Agent worktrees live under .claude/ — never collect their copies of the suite.
    exclude: [...configDefaults.exclude, '.claude/**'],
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
