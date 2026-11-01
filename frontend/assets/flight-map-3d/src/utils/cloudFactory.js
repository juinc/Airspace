import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

let cachedKitPromise = null;

/**
 * Procedural weather kit. Returns:
 * { low: [], moderate: [part x2], elevated: [part x2], high: [part x2] }
 *
 * PERFORMANCE: puffs are 10x7-segment spheres (was 16x12), 3-4 satellites
 * (was 5-6), 8-11 rain streaks (was 14-19), and 2 variants per category
 * (was 3). ~4x fewer vertices per instance — with 500 instances that is
 * the difference between a smooth load and a multi-second freeze.
 *
 * Realism strategy — color is split into two cooperating layers:
 *
 * 1. GEOMETRY vertex colors (baked here): volumetric shading. Bright tops
 *    fading to blue-gray undersides, with dark tapered rain streaks hanging
 *    below the base for rain-bearing categories.
 *
 * 2. INSTANCE colors (set in weatherSpanMarkers.js): the weather itself.
 *    A per-cell darkness value derived from the exposure category and
 *    blurred across neighboring cells.
 *
 * Seamlessness: every puff is clamped onto a shared flat base plane and the
 * variants include wide low "filler" puffs, so overlapping cell instances
 * fuse into one continuous cloud mass with no visible cell boundaries.
 */
export function loadWeatherMeshKit() {
    if (cachedKitPromise) return cachedKitPromise;
    cachedKitPromise = buildProceduralKit();
    return cachedKitPromise;
}

async function buildProceduralKit() {
    return {
        low: [],
        moderate: [
            makeCloudPart({ seed: 101, topColor: 0xf7fafd, bottomColor: 0x9fb3c9, opacity: 0.97 }),
            makeCloudPart({ seed: 133, topColor: 0xf2f7fc, bottomColor: 0x9fb3c9, opacity: 0.97 }),
        ],
        elevated: [
            makeCloudPart({ seed: 202, topColor: 0xdfe8f1, bottomColor: 0x71859d, opacity: 0.98, rain: true }),
            makeCloudPart({ seed: 234, topColor: 0xd8e2ec, bottomColor: 0x71859d, opacity: 0.98, rain: true }),
        ],
        high: [
            makeCloudPart({ seed: 303, topColor: 0xbfcdda, bottomColor: 0x556176, opacity: 0.985, rain: true, lightning: true }),
            makeCloudPart({ seed: 335, topColor: 0xb6c3d3, bottomColor: 0x556176, opacity: 0.985, rain: true, lightning: true }),
        ],
    };
}

const CLOUD_BASE_Y = -0.22;
const RAIN_COLOR = 0x4e6379;

function makeCloudPart(config) {
    const rng = seededRandom(config.seed);
    const geometries = [];

    // Central dome — the visual anchor of the cell.
    geometries.push(makePuff(rng, 0.24 + rng() * 0.05, 0, 0.05 + rng() * 0.04, 0));

    // Satellite domes around the center — the cauliflower silhouette.
    const satellites = 3 + Math.floor(rng() * 2);
    for (let i = 0; i < satellites; i++) {
        const angle = (i / satellites) * Math.PI * 2 + rng() * 0.9;
        const dist = 0.13 + rng() * 0.21;
        geometries.push(makePuff(
            rng,
            0.09 + rng() * 0.08,
            Math.cos(angle) * dist,
            -0.02 + (rng() - 0.5) * 0.10,
            Math.sin(angle) * dist * 0.85,
        ));
    }

    // Wide, flat fillers hugging the base plane — guarantee that
    // neighbouring cell instances overlap edge-to-edge and fuse.
    for (let i = 0; i < 2; i++) {
        const angle = rng() * Math.PI * 2;
        const dist = 0.30 + rng() * 0.12;
        geometries.push(makePuff(
            rng,
            0.09 + rng() * 0.05,
            Math.cos(angle) * dist,
            CLOUD_BASE_Y + 0.02 + rng() * 0.05,
            Math.sin(angle) * dist * 0.85,
        ));
    }

    // Tapered rain streaks hanging below the cloud base.
    if (config.rain) {
        const streakCount = 8 + Math.floor(rng() * 4);
        for (let i = 0; i < streakCount; i++) {
            const height = 0.16 + rng() * 0.10;
            const streak = new THREE.CylinderGeometry(0.005, 0.012, height, 3, 1);
            const angle = rng() * Math.PI * 2;
            const dist = 0.05 + rng() * 0.32;
            streak.translate(
                Math.cos(angle) * dist,
                CLOUD_BASE_Y - 0.05 - rng() * 0.12 - height / 2,
                Math.sin(angle) * dist * 0.85,
            );
            geometries.push(streak);
        }
    }

    const body = mergeGeometries(geometries, false);
    geometries.forEach(g => g.dispose());

    if (!body) {
        console.error('cloudFactory: mergeGeometries returned null — falling back to single puff');
        const fallback = makePuff(rng, 0.28, 0, 0.05, 0);
        fallback.computeVertexNormals();
        applyCloudVertexColors(fallback, config);
        fallback.userData.shared = true;
        const fallbackMaterial = cloudMaterial(config);
        return { geometry: fallback, material: fallbackMaterial, matrix: new THREE.Matrix4() };
    }

    body.computeVertexNormals();
    applyCloudVertexColors(body, config);
    body.userData.shared = true;

    const material = cloudMaterial(config);
    const part = { geometry: body, material, matrix: new THREE.Matrix4() };

    if (config.lightning) {
        // Soft additive core — the charged heart of a storm cell. Flickers
        // with random lightning flashes (driven in weatherSpanMarkers.js).
        const glow = new THREE.SphereGeometry(0.3, 10, 8);
        const glowMat = new THREE.MeshBasicMaterial({
            color: 0x9fd8ff,
            transparent: true,
            opacity: 0.3,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        });
        glowMat.userData.shared = true;
        glow.userData.shared = true;
        part.glow = { geometry: glow, material: glowMat, matrix: new THREE.Matrix4() };
    }

    return part;
}

/**
 * One cumulus puff: an indexed sphere displaced by POSITION-based noise.
 * Because the noise is a pure function of position, duplicated vertices
 * (sphere seams) displace identically — the surface stays seamless.
 */
function makePuff(rng, radius, x, y, z) {
    const geo = new THREE.SphereGeometry(radius, 10, 7);
    const pos = geo.attributes.position;
    const v = new THREE.Vector3();

    for (let i = 0; i < pos.count; i++) {
        v.fromBufferAttribute(pos, i);
        const n = 1 + vertexNoise(
            v.x * 4.5 + x * 9.0,
            v.y * 4.5 + y * 9.0,
            v.z * 4.5 + z * 9.0,
        ) * 0.09;
        pos.setXYZ(i, v.x * n, v.y * n * 0.8, v.z * n);
    }

    geo.translate(x, y, z);
    clampBase(geo, CLOUD_BASE_Y);
    return geo;
}

/**
 * Clamps every vertex onto the shared base plane. All instances sit on the
 * same plane, so where two cells overlap their bases merge into a single
 * flat cloud floor — the key to seamless fusion.
 */
function clampBase(geometry, baseY) {
    const pos = geometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
        if (pos.getY(i) < baseY) pos.setY(i, baseY);
    }
}

/**
 * Bakes the volumetric shading into vertex colors: bright tops fading to
 * blue-gray undersides. Rain streaks (below the base plane) get a darker,
 * wetter tint. Multiplied later by per-instance weather colors.
 */
function applyCloudVertexColors(geometry, config) {
    const pos = geometry.attributes.position;
    const colors = new Float32Array(pos.count * 3);
    const top = new THREE.Color(config.topColor);
    const bottom = new THREE.Color(config.bottomColor);
    const rain = new THREE.Color(RAIN_COLOR);
    const c = new THREE.Color();

    let maxY = CLOUD_BASE_Y;
    for (let i = 0; i < pos.count; i++) {
        if (pos.getY(i) > maxY) maxY = pos.getY(i);
    }
    const range = Math.max(1e-5, maxY - CLOUD_BASE_Y);

    for (let i = 0; i < pos.count; i++) {
        const y = pos.getY(i);
        if (y < CLOUD_BASE_Y - 0.005) {
            c.copy(rain); // rain streaks — dark, wet, blue-gray
        } else {
            const t = THREE.MathUtils.smoothstep(y, CLOUD_BASE_Y, CLOUD_BASE_Y + range);
            c.copy(bottom).lerp(top, t); // lit top, shaded underside
        }
        colors[i * 3] = c.r;
        colors[i * 3 + 1] = c.g;
        colors[i * 3 + 2] = c.b;
    }

    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
}

function cloudMaterial(config) {
    const material = new THREE.MeshStandardMaterial({
        vertexColors: true,
        color: 0xffffff, // white — instance colors carry the weather tint
        roughness: 0.96,
        metalness: 0,
        transparent: true,
        opacity: config.opacity,
        depthWrite: true, // overlapping instances occlude correctly -> solid mass
        emissive: 0x0c1219,
        emissiveIntensity: 0.4,
    });
    material.userData.shared = true;
    return material;
}

function vertexNoise(x, y, z) {
    return (
        Math.sin(x * 5.1 + y * 3.7) * 0.5 +
        Math.sin(y * 7.3 + z * 4.9) * 0.3 +
        Math.sin(z * 6.1 + x * 8.3) * 0.2
    );
}

function seededRandom(seed) {
    let s = seed;
    return () => {
        s = (s * 16807) % 2147483647;
        return (s - 1) / 2147483646;
    };
}