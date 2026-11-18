import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// In development `npm run dev` proxies /api to a locally running backend (uvicorn on :8000).
// In production nginx serves the build and proxies /api (see nginx/default.conf.template).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 127.0.0.1, not localhost: Node resolves localhost to ::1 first, uvicorn listens on IPv4.
      '/api': { target: process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000' },
    },
  },
  build: {
    chunkSizeWarningLimit: 1500,
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
