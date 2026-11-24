import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import vuetify from "vite-plugin-vuetify";

export default defineConfig({
  plugins: [vue(), vuetify({ autoImport: true })],
  server: {
    port: 3000,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/market.json": "http://127.0.0.1:8000",
      "/market-md5.json": "http://127.0.0.1:8000",
      "/plugin-assets": "http://127.0.0.1:8000",
    },
  },
  preview: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/market.json": "http://127.0.0.1:8000",
      "/market-md5.json": "http://127.0.0.1:8000",
      "/plugin-assets": "http://127.0.0.1:8000",
    },
  },
});

