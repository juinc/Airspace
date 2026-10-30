import * as THREE from 'three';

export function createScene() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x6b7066); // grey-green, matches reference image
  return scene;
}