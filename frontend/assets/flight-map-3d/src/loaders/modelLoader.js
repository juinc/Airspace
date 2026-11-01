const cache = new Map();
let loaderPromise;

function getLoader() {
  if (!loaderPromise) {
    loaderPromise = import('three/examples/jsm/loaders/GLTFLoader.js')
      .then(({ GLTFLoader }) => new GLTFLoader());
  }
  return loaderPromise;
}

export function loadModel(path) {
  if (cache.has(path)) {
    return cache.get(path);
  }

  const promise = getLoader()
    .then(loader => new Promise((resolve, reject) => {
      loader.load(
        path,
        gltf => resolve(gltf.scene),
        undefined,
        error => {
          console.error(`Error loading model at ${path}:`, error);
          reject(error);
        },
      );
    }))
    .catch(error => {
      cache.delete(path);
      throw error;
    });

  cache.set(path, promise);
  return promise;
}