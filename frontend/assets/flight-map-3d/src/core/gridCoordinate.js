import * as THREE from 'three';
import { gridConfig } from '../data/gridConfig.js';
import { getCubePosition } from '../utils/gridMath.js';

export class gridCoordinate {
  constructor(x, y, z) {
    this.x = x;
    this.y = y;
    this.z = z;
  }

  isValid(config = gridConfig) {
    const { size } = config;
    return [this.x, this.y, this.z].every(v => v >= 0 && v <= size - 1);
  }

  toWorldPosition(config = gridConfig) {
    const pos = getCubePosition({ x: this.x, y: this.y, z: this.z }, config);
    return new THREE.Vector3(pos.x, pos.y, pos.z);
  }

  equals(other) {
    return this.x === other.x && this.y === other.y && this.z === other.z;
  }

  toString() {
    return `(${this.x}, ${this.y}, ${this.z})`;
  }
}