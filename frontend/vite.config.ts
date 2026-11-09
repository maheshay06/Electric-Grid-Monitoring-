import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Stage 4+ will proxy /api and /ws to the FastAPI backend (default http://localhost:8000).
// Override when port 8000 is taken:  set API_TARGET=http://localhost:8010
const API_TARGET = process.env.API_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': API_TARGET,
      '/ws': { target: API_TARGET.replace(/^http/, 'ws'), ws: true },
    },
  },
});
