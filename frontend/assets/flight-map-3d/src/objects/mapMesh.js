import * as THREE from 'three';

export const mapModelConfig = {
    flipNorthSouth: true,
};

export function getMapPlaneY() {
    return 0;
}

let groundGlowTextureCache = null;
function groundGlowTexture() {
    if (groundGlowTextureCache) return groundGlowTextureCache;
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 128;
    const context = canvas.getContext('2d');
    const gradient = context.createRadialGradient(64, 64, 4, 64, 64, 64);
    gradient.addColorStop(0, 'rgba(255,255,255,1)');
    gradient.addColorStop(0.4, 'rgba(255,255,255,0.35)');
    gradient.addColorStop(1, 'rgba(255,255,255,0)');
    context.fillStyle = gradient;
    context.fillRect(0, 0, 128, 128);
    const texture = new THREE.CanvasTexture(canvas);
    groundGlowTextureCache = texture;
    return texture;
}

export function createMapMesh(model, grid, mapBounds) {
    const sceneBounds = getMapBounds(grid, mapBounds);
    const modelBounds = new THREE.Box3().setFromObject(model);
    const modelSize = modelBounds.getSize(new THREE.Vector3());
    if (modelSize.x <= 0 || modelSize.y <= 0 || modelSize.z <= 0) {
        throw new Error('Romania map model has no usable extent.');
    }

    const scaleX = (sceneBounds.max_x - sceneBounds.min_x) / modelSize.x;
    const scaleZ = (sceneBounds.max_z - sceneBounds.min_z) / modelSize.z;
    model.scale.x *= scaleX;
    model.scale.y *= (scaleX + scaleZ);
    model.scale.z *= scaleZ;

    // Mirror north-south if the GLB was authored with north along -Z.
    // Negative scale flips triangle winding, so materials are forced to
    // DoubleSide to keep every face visible.
    if (mapModelConfig.flipNorthSouth) {
        model.scale.z *= -1;
    }

    model.updateWorldMatrix(true, true);

    const fittedBounds = new THREE.Box3().setFromObject(model);
    const center = fittedBounds.getCenter(new THREE.Vector3());
    model.position.x += (sceneBounds.min_x + sceneBounds.max_x) / 2 - center.x;
    model.position.z += (sceneBounds.min_z + sceneBounds.max_z) / 2 - center.z;
    model.position.y += getMapPlaneY() - fittedBounds.max.y;

    model.traverse(object => {
        if (object.isMesh) {
            object.castShadow = true;
            object.receiveShadow = true;
            if (mapModelConfig.flipNorthSouth) {
                const materials = Array.isArray(object.material) ? object.material : [object.material];
                materials.forEach(material => { material.side = THREE.DoubleSide; });
            }
        }
    });

    // Wrap the map in a group so the pedestal decorations live in world
    // space (unaffected by the model's fitted scale).
    const sceneObject = new THREE.Group();
    sceneObject.add(model);

    const fitted = new THREE.Box3().setFromObject(model);
    const fittedCenter = fitted.getCenter(new THREE.Vector3());
    const fittedSize = fitted.getSize(new THREE.Vector3());
    const span = Math.max(fittedSize.x, fittedSize.z);

    // Soft glow disc under the country — grounds the map in the scene.
    const glow = new THREE.Mesh(
        new THREE.CircleGeometry(span * 0.75, 48),
        new THREE.MeshBasicMaterial({
            map: groundGlowTexture(),
            color: 0x2a5f8f,
            transparent: true,
            opacity: 0.35,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        }),
    );
    glow.rotation.x = -Math.PI / 2;
    glow.position.set(fittedCenter.x, fitted.min.y - 2, fittedCenter.z);
    sceneObject.add(glow);

    // Faint reference grid extending beyond the map — flight-sim feel.
    const gridHelper = new THREE.GridHelper(span * 1.7, 34, 0x1c3a55, 0x12263a);
    gridHelper.position.set(fittedCenter.x, fitted.min.y - 2, fittedCenter.z);
    gridHelper.material.transparent = true;
    gridHelper.material.opacity = 0.35;
    sceneObject.add(gridHelper);

    return sceneObject;
}

function getMapBounds(grid, mapBounds) {
    if (mapBounds && ['min_x', 'max_x', 'min_z', 'max_z'].every(key => Number.isFinite(mapBounds[key]))) {
        return mapBounds;
    }

    const xValues = grid.map(point => point.x).filter(Number.isFinite);
    const zValues = grid.map(point => point.z).filter(Number.isFinite);
    if (xValues.length < 2 || zValues.length < 2) {
        throw new Error('Backend response has insufficient coordinates to place the Romania map.');
    }

    return {
        min_x: Math.min(...xValues),
        max_x: Math.max(...xValues),
        min_z: Math.min(...zValues),
        max_z: Math.max(...zValues),
    };
}