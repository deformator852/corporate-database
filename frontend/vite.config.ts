/// <reference types="vitest/config" />
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import tailwindcss from "@tailwindcss/vite";

function backendEnv(mode: string) {
  return loadEnv(mode, path.resolve(import.meta.dirname, "../backend"), "APP_LANGUAGE");
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  define: {
    // Default and enabled languages chosen by `uv run install`; backend/.env is
    // the single source.
    "import.meta.env.APP_LANGUAGE": JSON.stringify(backendEnv(mode).APP_LANGUAGE ?? ""),
    "import.meta.env.APP_LANGUAGES": JSON.stringify(backendEnv(mode).APP_LANGUAGES ?? ""),
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
      "@pages": path.resolve(import.meta.dirname, "./src/pages"),
      "@layouts": path.resolve(import.meta.dirname, "./src/layouts"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    restoreMocks: true,
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
