import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  root: '.',
  publicDir: 'public',
  build: { outDir: 'dist/client' },
  server: {
    port: 5173,
    proxy: { '/api': process.env.API_URL ?? 'http://localhost:4000' },
  },
  test: {
    include: ['tests/**/*.test.ts', 'tests/**/*.test.tsx'],
    environment: 'node',
    testTimeout: 30000,
  },
} as any);
