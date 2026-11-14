import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In production FastAPI (port 8000) serves frontend/dist at "/", so the app
// always calls relative URLs like "/health". In dev, Vite proxies them.
const BACKEND = "http://localhost:8000";
const API_PREFIXES = ["/health", "/letters", "/proposals", "/account", "/audit"];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    proxy: Object.fromEntries(API_PREFIXES.map((prefix) => [prefix, BACKEND])),
  },
});
