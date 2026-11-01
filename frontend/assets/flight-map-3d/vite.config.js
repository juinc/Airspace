import { defineConfig } from 'vite';

export default defineConfig({
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
