import * as THREE from 'three';

/**
 * Executive scene atmosphere: deep-navy gradient sky and gentle depth fog.
 *
 * PERFORMANCE: the old version added a hemisphere + directional light on
 * top of lights.js — redundant, and every light is per-fragment cost on
 * every cloud. Lighting lives entirely in lights.js now.
 */
export function applyExecutiveEnvironment(scene) {
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
}