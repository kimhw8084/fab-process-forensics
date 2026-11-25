import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: resolve(here, "../reference-host"),
  base: "/reference/",
  esbuild: { jsx: "automatic" },
  resolve: {
    dedupe: ["react", "react-dom"],
    alias: [
      { find: /^react$/, replacement: resolve(here, "node_modules/react/index.js") },
      { find: /^react\/(.*)$/, replacement: `${resolve(here, "node_modules/react")}/$1` },
      { find: /^react-dom$/, replacement: resolve(here, "node_modules/react-dom/index.js") },
      { find: /^react-dom\/(.*)$/, replacement: `${resolve(here, "node_modules/react-dom")}/$1` },
    ],
  },
  build: {
    outDir: resolve(here, "../reference-host/dist"),
    emptyOutDir: true,
    sourcemap: false,
    target: "es2022",
  },
});
