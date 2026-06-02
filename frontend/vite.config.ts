import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The SPA is served under /admin by FastAPI in production. In dev, proxy /api to the
// local FastAPI server so the cookie session works same-origin.
export default defineConfig({
  base: "/admin/",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  // Crawl all source up front and pre-bundle the heavy deps (especially the many individual
  // @mui/icons-material deep imports) in the first optimize pass. Without this, Vite keeps
  // discovering new icon imports as you navigate and re-optimizes mid-session, which serves a
  // stale chunk and surfaces as "504 (Outdated Optimize Dep)" until a manual reload.
  optimizeDeps: {
    entries: ["index.html", "src/**/*.{ts,tsx}"],
    include: [
      "@mui/material",
      "@mui/material/styles",
      "@mui/icons-material",
      "@mui/x-charts",
      "@mui/x-data-grid",
      "@emotion/react",
      "@emotion/styled",
      "@tanstack/react-query",
      "notistack",
      "react",
      "react-dom",
      "react-dom/client",
      "react-router-dom",
    ],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
