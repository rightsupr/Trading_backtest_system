import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  return {
    plugins: [react()],
    server: {
      port: Number(env.FRONTEND_PORT || 5173),
      strictPort: true,
      proxy: Object.fromEntries(
        ["/api", "/docs", "/openapi.json"].map((path) => [
          path,
          `http://127.0.0.1:${env.API_PORT || 8000}`,
        ]),
      ),
    },
  };
});
