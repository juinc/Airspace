import * as THREE from 'three';
import { planeModelConfig } from '../data/modelConfig.js';
import { loadModel } from '../loaders/modelLoader.js';

const modelPath = `${import.meta.env.BASE_URL}${planeModelConfig.path.replace(/^\/+/, '')}`;

// Must mirror grid/coordinates.py exactly.
const VERTICAL_EXAGGERATION = 6;
const PHASE_VS_THRESHOLD_M_PER_MIN = 40;
const GROUND_ALTITUDE_KM = 0.12;

export async function createPlaneTemplate() {
    const model = await loadModel(modelPath);
    model.scale.setScalar(planeModelConfig.scale);
    return model;
}

export function instantiatePlane(template) {
    const plane = new THREE.Group();
    const model = template.clone(true);

    model.rotation.y += planeModelConfig.rotationOffsetY;
    model.traverse(object => {
        if (!object.isMesh) return;
        object.renderOrder = 10000;
        // IMPORTANT: clone() shares materials with the cached template.
        // Without cloning here, per-instance tweaks (depthTest) would corrupt
        // the template for every future scenario — and disposal of a previous
        // scene would destroy the cached materials entirely.
        const cloneMaterial = material => {
            const clone = material.clone();
            clone.depthTest = false;
            clone.depthWrite = false;
            return clone;
        };
        object.material = Array.isArray(object.material)
            ? object.material.map(cloneMaterial)
            : cloneMaterial(object.material);
    });
    plane.add(model);

    // Engine glow so the aircraft always reads against dark clouds.
    const engineLight = new THREE.PointLight(0x9fd8ff, 2.2, 90, 1.6);
    engineLight.position.set(0, 2, 0);
    plane.add(engineLight);

    return plane;
}

// ---------------------------------------------------------------------------
// Contrail — additive vertex-colored trail that fades behind the aircraft
// ---------------------------------------------------------------------------

const CONTRAIL_POINTS = 140;
const CONTRAIL_MIN_ALTITUDE = 10; // no trail on the runway / during low taxi

export function createContrail() {
    const positions = new Float32Array(CONTRAIL_POINTS * 3);
    const colors = new Float32Array(CONTRAIL_POINTS * 3);

    // Head bright, tail fades to black — with AdditiveBlending, black is
    // fully transparent, so no alpha channel is needed.
    for (let i = 0; i < CONTRAIL_POINTS; i++) {
        const fade = Math.pow(1 - i / CONTRAIL_POINTS, 1.7);
        colors[i * 3] = 0.62 * fade;
        colors[i * 3 + 1] = 0.85 * fade;
        colors[i * 3 + 2] = 1.0 * fade;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        depthTest: false,
    });

    const line = new THREE.Line(geometry, material);
    line.frustumCulled = false;
    line.renderOrder = 9;
    line.visible = false; // hidden until the aircraft is airborne

    const positionAttribute = geometry.attributes.position;

    return {
        line,

        push(point, altitude) {
            if (altitude < CONTRAIL_MIN_ALTITUDE) {
                // Below threshold: keep the trail parked at the current head
                // so it doesn't smear across the runway, and hide it.
                line.visible = false;
                positions[0] = point.x;
                positions[1] = point.y;
                positions[2] = point.z;
                positionAttribute.needsUpdate = true;
                return;
            }
            line.visible = true;
            // Shift the whole trail back by one vertex, write the new head.
            positions.copyWithin(3, 0, (CONTRAIL_POINTS - 1) * 3);
            positions[0] = point.x;
            positions[1] = point.y;
            positions[2] = point.z;
            positionAttribute.needsUpdate = true;
        },

        reset(point) {
            for (let i = 0; i < CONTRAIL_POINTS; i++) {
                positions[i * 3] = point.x;
                positions[i * 3 + 1] = point.y;
                positions[i * 3 + 2] = point.z;
            }
            positionAttribute.needsUpdate = true;
            line.visible = false;
        },
    };
}

// ---------------------------------------------------------------------------
// Animator — position, heading, banking, contrail, live flight state
// ---------------------------------------------------------------------------

export function createPlaneAnimator(planeMesh, curve, speed = 0.035, initialProgress = 0, contrail = null) {
    let t = initialProgress;
    let roll = 0;
    const pos = new THREE.Vector3();
    const ahead = new THREE.Vector3();
    const prevAhead = new THREE.Vector3();
    const prevPos = new THREE.Vector3();
    let hasPrev = false;

    // Smoothed live state for the HUD — all metric.
    let vsSmoothed = 0;
    let gsSmoothed = 0;
    const state = {
        progress: t,
        altitude_km: 0,
        vertical_speed_m_per_s: 0,
        ground_speed_kmh: 0,
        phase: 'CRUISE',
        position: pos, // read-only reference — do not mutate
    };

    const PHASE_VS_THRESHOLD_M_PER_S = 0.7;  // ~42 m/min — above this counts as climb/descent
    const GROUND_ALTITUDE_KM = 0.12;

    function update(delta) {
        const previousT = t;
        t += delta * speed;
        let wrapped = false;
        if (t > 1) {
            t = 0; // loop back to start of route
            wrapped = true;
        }

        curve.getPointAt(t, pos);
        curve.getPointAt(Math.min(t + 0.012, 1), ahead);

        planeMesh.position.copy(pos);
        planeMesh.lookAt(ahead);

        // Bank into turns: roll proportional to horizontal turn rate.
        if (hasPrev) {
            const dx = ahead.x - prevAhead.x;
            const dz = ahead.z - prevAhead.z;
            const dHoriz = Math.hypot(dx, dz);
            if (dHoriz > 1e-6) {
                const cross = dx * (pos.z - prevAhead.z) - dz * (pos.x - prevAhead.x);
                const targetRoll = THREE.MathUtils.clamp((cross / dHoriz) * 2.2, -0.6, 0.6);
                roll += (targetRoll - roll) * Math.min(1, delta * 4); // smooth
                planeMesh.rotateZ(roll);
            }
        }
        prevAhead.copy(ahead);

        // Live state: vertical + ground speed from position deltas.
        if (hasPrev && delta > 1e-6 && !wrapped) {
            const deltaAltM = ((pos.y - prevPos.y) / VERTICAL_EXAGGERATION) * 1000;
            const deltaHorizKm = Math.hypot(pos.x - prevPos.x, pos.z - prevPos.z);
            const vs = deltaAltM / delta;            // m per second
            const gs = deltaHorizKm / (delta / 3600); // km per hour
            const smoothing = Math.min(1, delta * 6);
            vsSmoothed += (vs - vsSmoothed) * smoothing;
            gsSmoothed += (gs - gsSmoothed) * smoothing;
        }
        prevPos.copy(pos);
        hasPrev = true;

        state.progress = t;
        state.altitude_km = pos.y / VERTICAL_EXAGGERATION;
        state.vertical_speed_m_per_s = vsSmoothed;
        state.ground_speed_kmh = gsSmoothed;
        if (state.altitude_km < GROUND_ALTITUDE_KM) {
            state.phase = t < 0.5 ? 'TAKEOFF' : 'LANDED';
        } else if (vsSmoothed > PHASE_VS_THRESHOLD_M_PER_S) {
            state.phase = 'CLIMB';
        } else if (vsSmoothed < -PHASE_VS_THRESHOLD_M_PER_S) {
            state.phase = 'DESCENT';
        } else {
            state.phase = 'CRUISE';
        }

        if (contrail) {
            if (wrapped || previousT === 0) contrail.reset(pos);
            else contrail.push(pos, pos.y);
        }
    }

    update.getProgress = () => t;
    update.getState = () => state;
    return update;
}