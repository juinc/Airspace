import * as THREE from 'three';

/**
 * PERFORMANCE renderer: no post-processing chain at all.
 *
 * The old EffectComposer + UnrealBloomPass cost 5-6 fullscreen passes per
 * frame on top of the main render. Route glow comes from the additive
 * glow-tube meshes in flightCurve.js, so bloom was nearly invisible
 * luxury. Direct render, native antialias, DPR capped at 1.25.
 *
 * Interface kept identical to the old composer-based renderer, so main.js
 * does not change: { renderer, domElement, setSize(w, h), render() }.
 */
export function createRenderer(container, scene, camera) {
    const isMobile = window.matchMedia('(max-width: 760px), (pointer: coarse)').matches;
    const maxPixelRatio = isMobile ? 1 : 1.25;
    const renderer = new THREE.WebGLRenderer({
        antialias: !isMobile,
        alpha: false,
        powerPreference: 'high-performance',
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, maxPixelRatio));
    renderer.setSize(container.clientWidth || window.innerWidth, container.clientHeight || window.innerHeight);

    // Shadows OFF: a 2048x VSM shadow map re-renders the whole scene a
    // second time per frame. On a dark night scene it was invisible.
    renderer.shadowMap.enabled = false;

    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);

    return {
        renderer,
        domElement: renderer.domElement,

        setSize(width, height) {
            renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, maxPixelRatio));
            renderer.setSize(width, height);
        },

        render() {
            renderer.render(scene, camera);
        },

        getInfo() {
            return {
                calls: renderer.info.render.calls,
                triangles: renderer.info.render.triangles,
                geometries: renderer.info.memory.geometries,
                textures: renderer.info.memory.textures,
                pixelRatio: renderer.getPixelRatio(),
            };
        },
    };
}