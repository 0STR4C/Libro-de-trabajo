import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig } from 'vite';

const projectRoot = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  base: '/static/frontend/',
  build: {
    outDir: resolve(projectRoot, 'app/static/frontend'),
    emptyOutDir: true,
    assetsInlineLimit: 0,
    cssCodeSplit: false,
    sourcemap: false,
    rollupOptions: {
      input: resolve(projectRoot, 'frontend/main.jsx'),
      preserveEntrySignatures: 'strict',
      output: {
        entryFileNames: 'prime-react.js',
        assetFileNames: (assetInfo) =>
          assetInfo.name?.endsWith('.css')
            ? 'prime-react.css'
            : 'assets/[name]-[hash][extname]'
      }
    }
  }
});
