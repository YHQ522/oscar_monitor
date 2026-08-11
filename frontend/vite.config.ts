import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发时把 /api 代理到 FastAPI 后端
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5080',
        changeOrigin: true,
        // SSE：禁止代理层缓冲流式响应
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['Cache-Control'] = 'no-cache'
            proxyRes.headers['X-Accel-Buffering'] = 'no'
          })
        },
      },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // 大依赖独立分包，利用浏览器缓存
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom', 'zustand'],
          'vendor-antd': ['antd', '@ant-design/icons'],
          'vendor-charts': ['recharts'],
        },
      },
    },
  },
})
