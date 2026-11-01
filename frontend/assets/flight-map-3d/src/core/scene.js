import * as THREE from 'three';

export function createScene() {
    const scene = new THREE.Scene();

    // Deep navy vertical gradient background
    const topColor = new THREE.Color(0x0a1628);
    const bottomColor = new THREE.Color(0x050a12);
    const canvas = document.createElement('canvas');
    canvas.width = 2;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 512);
    gradient.addColorStop(0, `#${topColor.getHexString()}`);
    gradient.addColorStop(1, `#${bottomColor.getHexString()}`);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 2, 512);
    
    const bgTexture = new THREE.CanvasTexture(canvas);
    bgTexture.colorSpace = THREE.SRGBColorSpace;
    scene.background = bgTexture;
    
    // Atmospheric fog — clouds and map fade gracefully with distance
    scene.fog = new THREE.Fog(0x0a1420, 600, 2600);
    
    return scene;
}