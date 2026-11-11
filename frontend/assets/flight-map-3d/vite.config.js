import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
  },
  build: {
    target: 'es2020',
    minify: 'oxc',
    cssMinify: true,
    reportCompressedSize: true,
    rolldownOptions: {
      output: {
        codeSplitting: {
          minSize: 20000,
          groups: [{
            name: 'three-vendor',
            test: /node_modules[\\/]three[\\/]build[\\/]three\.module\.js$/,
          }],
        },
      },
    },
  },
});
