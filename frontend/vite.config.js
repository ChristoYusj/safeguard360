import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The dev server always proxies /api and /ws to the backend so a fresh clone
// works with the documented `python main.py` + `npm run dev` pair. Override the
// targets with VITE_DEV_BACKEND_HTTP_ORIGIN / VITE_DEV_BACKEND_WS_ORIGIN in the
// root .env when the backend runs elsewhere.
const DEFAULT_HTTP_ORIGIN = "http://127.0.0.1:8000";
const DEFAULT_WS_ORIGIN = "ws://127.0.0.1:8000";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  const httpProxyTarget = env.VITE_DEV_BACKEND_HTTP_ORIGIN || DEFAULT_HTTP_ORIGIN;
  const wsProxyTarget = env.VITE_DEV_BACKEND_WS_ORIGIN || DEFAULT_WS_ORIGIN;

  return {
    envDir: "..",
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: httpProxyTarget,
          changeOrigin: true,
        },
        "/ws": {
          target: wsProxyTarget,
          ws: true,
        },
      },
    },
  };
});
