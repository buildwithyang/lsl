import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import { inspectAttr } from 'kimi-plugin-inspect-react'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [inspectAttr(), react()],
  server: {
    host: '0.0.0.0',
    allowedHosts: ['dev.buildwithyang.com'],
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://dev.buildwithyang.com:8000',
        changeOrigin: true,
        rewrite: (urlPath) => urlPath.replace(/^\/api/, ''),
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
