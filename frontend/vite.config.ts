import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// The SPA is served under /admin by FastAPI in production. In dev, proxy /api to the
// local FastAPI server so the cookie session works same-origin.
export default defineConfig({
  base: "/admin/",
  plugins: [
    react(),
    // Service worker (Workbox) for offline/app-like reliability. Scope is /admin/ (the base),
    // so it manages the app shell only and never intercepts /api or /api/stream (SSE) — live
    // data always hits the network. Uses our existing public/manifest.webmanifest.
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: "auto",
      manifest: false,
      includeAssets: ["icon-192.png", "icon-512.png", "icon-maskable-512.png",
                      "apple-touch-icon.png", "favicon.png", "manifest.webmanifest"],
      workbox: {
        globPatterns: ["**/*.{js,css,html,png,svg,woff,woff2}"],
        navigateFallback: "/admin/index.html",
        navigateFallbackDenylist: [/^\/api/, /^\/webhook/],
        cleanupOutdatedCaches: true,
        clientsClaim: true,
      },
      devOptions: { enabled: false },   // SW only in production builds
    }),
  ],
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
      "@emotion/cache",
      "stylis",
      "stylis-plugin-rtl",
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
