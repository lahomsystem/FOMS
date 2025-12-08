import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  base: '/wdplanner/app/',
  server: {
    port: 5173,
    host: '0.0.0.0', // 모든 네트워크 인터페이스에서 접근 가능
    strictPort: false, // 포트가 사용 중이면 다른 포트 사용
  },
  build: {
    outDir: 'dist',
  },
  optimizeDeps: {
    include: ['@babylonjs/core'],
    force: true, // 캐시 무시하고 강제로 재최적화
  },
})

