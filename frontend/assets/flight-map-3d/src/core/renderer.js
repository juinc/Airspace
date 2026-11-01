import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';

/**
 * Creates the WebGL renderer plus a bloom post-processing chain:
 * scene -> bloom (glowing routes, beacons, storm cores) -> tone-mapped output.
 * Uses an MSAA render target so lines and cloud edges stay crisp.
 */
export function createRenderer(container, scene, camera) {
    const renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: false,
        powerPreference: 'high-performance',
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
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
            samples: 4, // MSAA — silently ignored on unsupported GPUs
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
            composer.setSize(width, height);
            bloomPass.setSize(width, height);
        },

        render(delta) {
            composer.render(delta);
        },
    };
}