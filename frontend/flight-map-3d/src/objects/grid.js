import * as THREE from 'three';
import { createMiniCubeGeometry, createMiniCubeMaterial } from './miniCube.js';
import { createGridBoundary } from './gridBoundary.js';
import { getCubePosition } from '../utils/gridMath.js';

export function createGridSystem(gridConfig) {
  const group = new THREE.Group();

  group.add(createMiniCubesInstanced(gridConfig));
  group.add(createGridBoundary(gridConfig));

  return group;
}

function createMiniCubesInstanced(gridConfig) {
  const { size } = gridConfig;
  const total = size * size * size;

  const geometry = createMiniCubeGeometry(gridConfig.cubeSize);
  const material = createMiniCubeMaterial();
  const instancedMesh = new THREE.InstancedMesh(geometry, material, total);

  const dummy = new THREE.Object3D();
  let index = 0;

  for (let x = 0; x < size; x++) {
    for (let y = 0; y < size; y++) {
      for (let z = 0; z < size; z++) {
        const pos = getCubePosition({ x, y, z }, gridConfig);
        dummy.position.set(pos.x, pos.y, pos.z);
        dummy.updateMatrix();
        instancedMesh.setMatrixAt(index, dummy.matrix);
        index++;
      }
    }
  }

  instancedMesh.instanceMatrix.needsUpdate = true;
  return instancedMesh;
}