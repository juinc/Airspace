import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const loader = new GLTFLoader();
const cache = new Map();

export function loadModel(path) {
  if (cache.has(path)) {
    return cache.get(path);
  }

  const promise = new Promise((resolve, reject) => {
    loader.load(
      path,
      (gltf) => {
        console.log(`Model loaded from: ${path}`);
        resolve(gltf.scene);
      },
      (progress) => {
        console.log(`Loading ${path}:`, progress.loaded, '/', progress.total);
      },
      (error) => {
        console.error(`Error loading model at ${path}:`, error);
        reject(error);
      }
    );
  });

  cache.set(path, promise);
  return promise;
}