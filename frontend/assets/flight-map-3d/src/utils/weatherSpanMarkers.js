import * as THREE from 'three';

/**
 * Renders weather clusters as instanced cloud puffs — one puff per grid cell,
 * mixed across the kit's shape variants so clusters never look copy-pasted.
 *
 * Seamlessness & realism:
 * - Instances overlap their cell bounds horizontally AND vertically, so
 *   neighbouring cells and stacked layers fuse into one continuous deck.
 * - Per-instance color = weather darkness (category-derived, blurred across
 *   all six neighbors), so light cloud gradually darkens into rain cells.
 * - Cells spawn with a staggered ease-out-back pop sweeping along the
 *   corridor.
 * - Storm clusters carry a lightning core that idles dim and fires random
 *   bright flashes, like a real charged cell.
 *
 * PERFORMANCE: after the spawn sweep completes, cloud instance matrices are
 * written ONE final time and then frozen — no per-frame matrix churn for
 * thousands of instances. Only the (few) lightning cores keep animating.
 */

// How dark each category renders before neighbor blur (0 = white, 1 = slate).
const CATEGORY_DARKNESS = { low: 0.0, moderate: 0.06, elevated: 0.42, high: 0.78 };
const DARK_CLOUD = new THREE.Color(0x39445a);

const SPAWN_DURATION = 0.9;

export function createWeatherSpanMarkers(clusters, weatherMeshKit, options = {}) {
    const {
        cellStepX = 20,
        cellStepZ = 20,
        layerHeight = 30,
    } = options;

    const group = new THREE.Group();
    if (!Array.isArray(clusters) || clusters.length === 0) return group;
    if (!weatherMeshKit) return group;

    const dummy = new THREE.Object3D();
    const cloudAnimated = [];
    const lightningAnimated = [];

    // --- Collect every cell with its cluster category ---------------------
    const allCells = [];
    clusters.forEach(cluster => {
        (cluster.cells || []).forEach(cell => {
            allCells.push({ x: cell.x, y: cell.y, z: cell.z, category: cluster.category });
        });
    });

    // --- Darkness field with neighbor blur --------------------------------
    // Averaging each cell's darkness with its six neighbors turns hard
    // category boundaries into smooth gradients across the cloud field.
    const darkness = buildDarknessField(allCells, cellStepX, cellStepZ, layerHeight);

    // Corridor bounds drive the spawn sweep direction.
    let minX = Infinity;
    let maxX = -Infinity;
    allCells.forEach(cell => {
        if (cell.x < minX) minX = cell.x;
        if (cell.x > maxX) maxX = cell.x;
    });
    const corridorSpan = Math.max(1e-6, maxX - minX);

    const byCategory = {};
    clusters.forEach(cluster => {
        if (!byCategory[cluster.category]) byCategory[cluster.category] = [];
        byCategory[cluster.category].push(cluster);
    });

    Object.entries(byCategory).forEach(([category, categoryClusters]) => {
        const parts = weatherMeshKit[category] || [];
        if (parts.length === 0) return; // 'low' / unknown categories render nothing

        // Distribute cells across shape variants via a stable position hash.
        const variantStates = parts.map(() => []);
        categoryClusters.forEach(cluster => {
            (cluster.cells || []).forEach(cell => {
                const hash = Math.abs(Math.round(cell.x * 3.7 + cell.z * 5.3 + cell.y * 2.1));
                variantStates[hash % parts.length].push(makeCellState(cell, cluster.category));
            });
        });

        variantStates.forEach((states, variantIndex) => {
            if (states.length === 0) return;
            const part = parts[variantIndex];
            const mesh = new THREE.InstancedMesh(part.geometry, part.material, states.length);
            mesh.castShadow = false; // transparent materials cast blobby shadows — skip
            mesh.frustumCulled = false; // instances span the whole corridor
            states.forEach((s, i) => {
                writeInstance(dummy, mesh, i, s, 0, 0);
                mesh.setColorAt(i, s.color); // weather tint per cell
            });
            mesh.instanceMatrix.needsUpdate = true;
            if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
            group.add(mesh);
            cloudAnimated.push({ mesh, states });
        });

        // Lightning core per high-exposure cluster — idles dim, flashes bright.
        if (parts[0].glow) {
            const glow = new THREE.InstancedMesh(parts[0].glow.geometry, parts[0].glow.material, categoryClusters.length);
            glow.frustumCulled = false;
            glow.renderOrder = 1;
            const gStates = categoryClusters.map((cluster, i) => ({
                x: cluster.x,
                y: cluster.yCenter,
                z: cluster.z,
                base: Math.min(cluster.width, cluster.depth) * 0.5,
                nextFlash: 1.5 + Math.random() * 5,
                flashT: -1,
                phase: i * 1.7,
            }));
            glow.instanceMatrix.needsUpdate = true;
            group.add(glow);
            lightningAnimated.push({ mesh: glow, states: gStates });
        }
    });

    function makeCellState(cell, category) {
        const key = `${cell.x.toFixed(2)}|${cell.y.toFixed(2)}|${cell.z.toFixed(2)}`;
        const darknessValue = darkness.get(key) ?? CATEGORY_DARKNESS[category] ?? 0.25;

        // Weather tint: white for light cloud, deepening slate for rain/storm.
        const color = new THREE.Color(1, 1, 1).lerp(DARK_CLOUD, darknessValue);
        color.multiplyScalar(0.94 + Math.random() * 0.12); // subtle organic variance

        return {
            x: cell.x + (Math.random() - 0.5) * cellStepX * 0.12,
            y: cell.y,
            z: cell.z + (Math.random() - 0.5) * cellStepZ * 0.12,
            // Overlap cell bounds so neighbours always touch and fuse.
            sx: cellStepX * (1.14 + Math.random() * 0.18),
            sy: layerHeight * (1.04 + Math.random() * 0.16),
            sz: cellStepZ * (1.14 + Math.random() * 0.18),
            rotY: Math.random() * Math.PI * 2,
            phase: Math.random() * Math.PI * 2,
            bob: layerHeight * 0.02 + 0.3,
            // Spawn sweeps along the corridor with a little jitter.
            delay: ((cell.x - minX) / corridorSpan) * 1.4 + Math.random() * 0.35,
            color,
        };
    }

    // Last moment any cloud instance is still animating its spawn.
    let spawnEnd = 0;
    cloudAnimated.forEach(({ states }) => states.forEach(s => {
        spawnEnd = Math.max(spawnEnd, s.delay + SPAWN_DURATION);
    }));

    let time = 0;
    let cloudsFrozen = false;

    group.userData.update = delta => {
        time += delta;

        // Clouds: animate only during the spawn sweep, then write the final
        // matrices once and stop touching them. This is the difference between
        // ~4500 matrix writes per frame and zero.
        if (!cloudsFrozen) {
            const spawning = time < spawnEnd;
            const frameTime = spawning ? time : spawnEnd;
            cloudAnimated.forEach(({ mesh, states }) => {
                states.forEach((s, i) => {
                    const spawn = THREE.MathUtils.clamp(
                        (frameTime - s.delay) / SPAWN_DURATION, 0, 1,
                    );
                    writeInstance(dummy, mesh, i, s, frameTime, easeOutBack(spawn));
                });
                mesh.instanceMatrix.needsUpdate = true;
            });
            if (!spawning) cloudsFrozen = true;
        }

        // Lightning: few instances, cheap — keep it alive every frame.
        lightningAnimated.forEach(({ mesh, states }) => {
            const spawn = easeOutBack(THREE.MathUtils.clamp(time / 1.5, 0, 1));
            states.forEach((s, i) => {
                // Random lightning: mostly a dim ember, occasional bright flash.
                if (s.flashT < 0 && time > s.nextFlash) {
                    s.flashT = 0;
                    s.nextFlash = time + 2.5 + Math.random() * 6;
                }
                let scale;
                if (s.flashT >= 0) {
                    s.flashT += delta;
                    const f = s.flashT / 0.22;
                    if (f >= 1) {
                        s.flashT = -1;
                        scale = s.base * 0.15;
                    } else {
                        scale = s.base * (0.15 + Math.sin(f * Math.PI) * 2.2);
                    }
                } else {
                    scale = s.base * 0.15;
                }
                dummy.position.set(s.x, s.y, s.z);
                dummy.scale.setScalar(Math.max(1e-5, scale * spawn));
                dummy.rotation.set(0, 0, 0);
                dummy.updateMatrix();
                mesh.setMatrixAt(i, dummy.matrix);
            });
            mesh.instanceMatrix.needsUpdate = true;
        });
    };

    return group;
}

function buildDarknessField(cells, stepX, stepZ, layerHeight) {
    const keyOf = c => `${c.x.toFixed(2)}|${c.y.toFixed(2)}|${c.z.toFixed(2)}`;
    const raw = new Map();
    cells.forEach(c => raw.set(keyOf(c), CATEGORY_DARKNESS[c.category] ?? 0.25));

    const blurred = new Map();
    cells.forEach(c => {
        let sum = raw.get(keyOf(c));
        let count = 1;
        const neighbors = [
            { x: c.x + stepX, y: c.y, z: c.z },
            { x: c.x - stepX, y: c.y, z: c.z },
            { x: c.x, y: c.y, z: c.z + stepZ },
            { x: c.x, y: c.y, z: c.z - stepZ },
            { x: c.x, y: c.y + layerHeight, z: c.z },
            { x: c.x, y: c.y - layerHeight, z: c.z },
        ];
        neighbors.forEach(n => {
            const v = raw.get(keyOf(n));
            if (v != null) {
                sum += v;
                count += 1;
            }
        });
        blurred.set(keyOf(c), sum / count);
    });
    return blurred;
}

function writeInstance(dummy, mesh, index, s, time, spawnScale) {
    dummy.position.set(
        s.x + Math.sin(time * 0.3 + s.phase) * s.sx * 0.015,
        s.y + Math.sin(time * 0.7 + s.phase) * s.bob * spawnScale,
        s.z + Math.cos(time * 0.25 + s.phase) * s.sz * 0.015,
    );
    dummy.scale.set(
        Math.max(1e-5, s.sx * spawnScale),
        Math.max(1e-5, s.sy * spawnScale),
        Math.max(1e-5, s.sz * spawnScale),
    );
    dummy.rotation.set(0, s.rotY + Math.sin(time * 0.15 + s.phase) * 0.04, 0);
    dummy.updateMatrix();
    mesh.setMatrixAt(index, dummy.matrix);
}

function easeOutBack(t) {
    const c1 = 1.70158;
    const c3 = c1 + 1;
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
}