import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  const httpProxyTarget = env.VITE_DEV_BACKEND_HTTP_ORIGIN;
  const wsProxyTarget = env.VITE_DEV_BACKEND_WS_ORIGIN;

  return {
    envDir: "..",
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        ...(httpProxyTarget
          ? {
              "/api": {
                target: httpProxyTarget,
                changeOrigin: true,
              },
            }
          : {}),
        ...(wsProxyTarget
          ? {
              "/ws": {
                target: wsProxyTarget,
                ws: true,
              },
            }
          : {}),
      },
    },
  };
});
