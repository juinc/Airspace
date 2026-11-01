import * as THREE from 'three';

/**
 * Executive scene atmosphere: deep-navy gradient sky, gentle depth fog and
 * soft fill lighting. Purely additive — replaces no existing lights.
 */
export function applyExecutiveEnvironment(scene) {
    // Vertical gradient background (screen-space feel via large canvas).
    const canvas = document.createElement('canvas');
    canvas.width = 2;
    canvas.height = 512;
    const context = canvas.getContext('2d');
    const gradient = context.createLinearGradient(0, 0, 0, 512);
    gradient.addColorStop(0, '#101b2d');   // zenith
    gradient.addColorStop(0.55, '#0a1120');
    gradient.addColorStop(1, '#04070d');   // below horizon
    context.fillStyle = gradient;
    context.fillRect(0, 0, 2, 512);
    scene.background = new THREE.CanvasTexture(canvas);
    scene.background.colorSpace = THREE.SRGBColorSpace;

    // Depth fog tuned to the corridor scale (~600 km span, camera ~500 out).
    scene.fog = new THREE.Fog(0x0a1120, 1100, 3200);

    // Soft sky/ground bounce the original rig may not include.
    const hemi = new THREE.HemisphereLight(0x8fb7d9, 0x141c28, 0.38);
    scene.add(hemi);

    // Cool rim fill from the west so terrain reads with dimension.
    const fill = new THREE.DirectionalLight(0xcfe4ff, 0.28);
    fill.position.set(-400, 500, -250);
    scene.add(fill);
}