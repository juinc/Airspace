import * as THREE from 'three';

export function createCamera() {
    const camera = new THREE.PerspectiveCamera(
        45,
        (window.innerWidth || 1) / (window.innerHeight || 1),
        0.5,
        6000,
    );

    // High opening position — the intro glide sweeps down into the corridor.
    camera.position.set(-260, 430, 660);
    camera.lookAt(0, 0, 0);

    return camera;
}