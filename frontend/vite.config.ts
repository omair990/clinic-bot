import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The SPA is served under /admin by FastAPI in production. In dev, proxy /api to the
// local FastAPI server so the cookie session works same-origin.
export default defineConfig({
  base: "/admin/",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
