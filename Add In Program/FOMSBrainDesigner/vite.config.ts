import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/wdplanner-v2/app/',
  build: {
    outDir: resolve(__dirname, '../../static/designer'),
    emptyOutDir: true,
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      input: resolve(__dirname, 'index.html'),
      output: {
        manualChunks: {
          // Split Three.js + R3F into a separate chunk
          'vendor-three': ['three'],
          'vendor-r3f': ['@react-three/fiber', '@react-three/drei'],
          // React core
          'vendor-react': ['react', 'react-dom'],
          // Zustand state
          'vendor-zustand': ['zustand'],
        },
      },
    },
  },
})
