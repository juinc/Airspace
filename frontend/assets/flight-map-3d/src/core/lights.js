import * as THREE from 'three';

/**
 * PERFORMANCE lighting: four shadowless lights total. The old rig had a
 * 2048x VSM shadow-casting sun plus a fifth fill light — every extra
 * light is a per-fragment cost on all 500 cloud instances, and shadows
 * were disabled at the renderer anyway.
 */
export function createLights(scene) {
    // Cool sky fill from above, dark bounce from below.
    const hemisphere = new THREE.HemisphereLight(0x9fc4ff, 0x0c1420, 0.85);
    scene.add(hemisphere);

    const ambient = new THREE.AmbientLight(0x2a3b4d, 0.45);
    scene.add(ambient);

    // Main "sun" — slightly warm, moody intensity. No shadow casting.
    const sun = new THREE.DirectionalLight(0xfff2df, 1.2);
    sun.position.set(300, 500, 200);
    scene.add(sun);

    // Cyan rim light from behind for the tech aesthetic.
    const rim = new THREE.DirectionalLight(0x4dd8ff, 0.4);
    rim.position.set(-200, 150, -400);
    scene.add(rim);

    return { sun, hemisphere, ambient, rim };
}