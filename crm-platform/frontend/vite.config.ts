import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В dev-режиме проксируем /api на Django (localhost:8000) — без проблем с CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
