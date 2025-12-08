import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  build: {
    outDir: 'dist-electron',
    emptyOutDir: false,
    rollupOptions: {
      input: {
        preload: resolve(__dirname, 'src/preload/index.ts'),
      },
      output: {
        entryFileNames: '[name]/index.js',
        format: 'cjs',
      },
      external: ['electron'],
    },
  },
})

