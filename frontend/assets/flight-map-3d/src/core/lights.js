import * as THREE from 'three';

export function createLights(scene) {
    // Cool sky fill from above, dark bounce from below.
    const hemisphere = new THREE.HemisphereLight(0x9fc4ff, 0x0c1420, 0.85);
    scene.add(hemisphere);

    const ambient = new THREE.AmbientLight(0x2a3b4d, 0.45);
    scene.add(ambient);

    // Main "sun" — slightly warm, moody intensity.
    const sun = new THREE.DirectionalLight(0xfff2df, 1.5);
    sun.position.set(300, 500, 200);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    const s = 500;
    sun.shadow.camera.left = -s;
    sun.shadow.camera.right = s;
    sun.shadow.camera.top = s;
    sun.shadow.camera.bottom = -s;
    sun.shadow.camera.far = 2000;
    sun.shadow.bias = -0.0005;
    scene.add(sun);

    // Cyan rim light from behind for the tech aesthetic.
    const rim = new THREE.DirectionalLight(0x4dd8ff, 0.4);
    rim.position.set(-200, 150, -400);
    scene.add(rim);

    // Soft frontal fill so cloud faces facing the camera never go pitch black.
    const fill = new THREE.DirectionalLight(0x88aaff, 0.22);
    fill.position.set(120, 220, 520);
    scene.add(fill);

    return { sun, hemisphere, ambient, rim, fill };
}