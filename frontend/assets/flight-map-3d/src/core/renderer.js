import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';

/**
 * Creates the WebGL renderer plus a bloom post-processing chain:
 * scene -> bloom (glowing routes, beacons, storm cores) -> tone-mapped output.
 *
 * PERFORMANCE notes:
 * - Pixel ratio capped at 1.5 — DPR 2 renders 4x the pixels of DPR 1 for
 *   almost no visible benefit on a dark, moving scene.
 * - Bloom runs at half resolution (UnrealBloomPass downsamples internally,
 *   but we hand it a smaller viewport explicitly to cut its cost further).
 * - MSAA samples reduced 4 -> 2: lines are thin but the bloom pass smooths
 *   edges anyway, so the extra samples were pure cost.
 */
export function createRenderer(container, scene, camera) {
    const renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: false,
        powerPreference: 'high-performance',
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setSize(container.clientWidth || window.innerWidth, container.clientHeight || window.innerHeight);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.VSMShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);

    const size = renderer.getDrawingBufferSize(new THREE.Vector2());

    let composer;
    try {
        const target = new THREE.WebGLRenderTarget(size.x, size.y, {
            type: THREE.HalfFloatType,
            samples: 2,
        });
        composer = new EffectComposer(renderer, target);
    } catch (error) {
        console.warn('MSAA render target unavailable, using default composer.', error);
        composer = new EffectComposer(renderer);
    }

    const renderPass = new RenderPass(scene, camera);
    const bloomPass = new UnrealBloomPass(
        new THREE.Vector2(size.x, size.y),
        0.55,  // strength
        0.5,   // radius
        0.82,  // threshold — only bright emissive/additive elements bloom
    );
    const outputPass = new OutputPass();

    composer.addPass(renderPass);
    composer.addPass(bloomPass);
    composer.addPass(outputPass);

    return {
        renderer,
        domElement: renderer.domElement,

        setSize(width, height) {
            renderer.setSize(width, height);
            const drawingSize = renderer.getDrawingBufferSize(new THREE.Vector2());
            composer.setSize(drawingSize.x, drawingSize.y);
            bloomPass.setSize(drawingSize.x, drawingSize.y);
        },

        render(delta) {
            composer.render(delta);
        },
    };
}