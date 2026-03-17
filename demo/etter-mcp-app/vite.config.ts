import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

const tileProxyPort = process.env.PORT ?? "3002";

export default defineConfig({
  plugins: [viteSingleFile()],
  define: {
    __TILE_PROXY_PORT__: JSON.stringify(tileProxyPort),
  },
  build: {
    outDir: "dist",
    rollupOptions: {
      input: process.env.INPUT,
    },
  },
});
