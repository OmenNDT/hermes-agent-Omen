import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Loopback only, in dev as in production. The Coach backend refuses any
// non-loopback Host or Origin, so binding wider here would only produce a
// dev server whose requests the backend rejects.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: {
    host: "127.0.0.1",
    port: 5175,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
