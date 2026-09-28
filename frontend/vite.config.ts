import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  define: {
    // System language chosen by `uv run setup`; backend/.env is the single source.
    "import.meta.env.APP_LANGUAGE": JSON.stringify(
      loadEnv(mode, path.resolve(import.meta.dirname, "../backend"), "APP_LANGUAGE")
        .APP_LANGUAGE ?? "",
    ),
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
      "@pages": path.resolve(import.meta.dirname, "./src/pages"),
      "@layouts": path.resolve(import.meta.dirname, "./src/layouts"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true,
        rewriteWsOrigin: true,
      },
    },
  },
}));
