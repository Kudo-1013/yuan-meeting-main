import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'node:path'
import { visualizer } from 'rollup-plugin-visualizer'

// vite-plugin-compression 是 CJS 模块，需要 default 取值
import viteCompression from 'vite-plugin-compression'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // @ts-expect-error CJS 默认导出类型不匹配
    viteCompression({
      verbose: true,
      disable: false,
      threshold: 10240,
      algorithm: 'gzip',
      ext: '.gz',
    }),
    visualizer({
      open: false,
      filename: 'dist/stats.html',
      gzipSize: true,
      brotliSize: true,
    }),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  build: {
    // modulePreload：预加载关键 chunk，提升路由切换速度
    modulePreload: {
      polyfill: true,
      // 只预加载首屏关键 chunk
      resolveDependencies: (_, deps) =>
        deps.filter(
          (dep) =>
            dep.includes('react-vendor') ||
            dep.includes('ui-vendor') ||
            dep.includes('state-vendor'),
        ),
    },
    // CSS 代码分割
    cssCodeSplit: true,
    // 分包策略：将 vendor 库拆分，优化首屏加载
    rollupOptions: {
      output: {
        codeSplitting: {
          includeDependenciesRecursively: false,
          groups: [
            {
              name: 'markdown-vendor',
              test: /node_modules[\\/](?:react-markdown|remark-[^\\/]+|rehype-[^\\/]+|highlight\.js)[\\/]/,
              priority: 30,
            },
            {
              name: 'react-vendor',
              test: /node_modules[\\/](?:react|react-dom|react-router|react-router-dom|scheduler)[\\/]/,
              priority: 25,
            },
            {
              name: 'ui-vendor',
              test: /node_modules[\\/](?:lucide-react|class-variance-authority|clsx|tailwind-merge)[\\/]/,
              priority: 20,
            },
            {
              name: 'state-vendor',
              test: /node_modules[\\/](?:zustand|@tanstack[\\/][^\\/]+)[\\/]/,
              priority: 20,
            },
            {
              name: 'chart-vendor',
              test: /node_modules[\\/](?:recharts|d3-[^\\/]+)[\\/]/,
              priority: 20,
            },
            {
              name: 'form-vendor',
              test: /node_modules[\\/](?:react-hook-form|zod|@hookform[\\/][^\\/]+)[\\/]/,
              priority: 20,
            },
          ],
        },
      },
    },
    // chunk 大小警告阈值
    chunkSizeWarningLimit: 500,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8787',
        changeOrigin: true,
      },
    },
  },
})
