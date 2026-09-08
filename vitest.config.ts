import { defineConfig } from 'vitest/config';

// Story Engine tests are pure TypeScript (no DOM, no React), so we run them in
// a plain Node environment without the app's Vite/PWA/Tailwind plugins.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.{test,spec}.ts'],
  },
});
