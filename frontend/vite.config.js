import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "ENV_BACKEND_HTTP_ORIGIN",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://ENV_BACKEND_ORIGIN",
        ws: true,
      },
    },
  },
});
