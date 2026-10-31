import * as THREE from 'three';

export function createCamera(targetY = 0) {
    const camera = new THREE.PerspectiveCamera(
        45,
        window.innerWidth / window.innerHeight,
        0.1,
        5000
    );

    camera.position.set(0, targetY + 300, 400);
    camera.lookAt(0, targetY, 0);

    return camera;
}