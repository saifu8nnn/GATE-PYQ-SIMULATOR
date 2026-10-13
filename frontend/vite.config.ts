import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Offline local app: no CDN, no externals. Base "./" so the built bundle
// works from file paths or any static server without configuration.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
