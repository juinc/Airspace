import * as THREE from 'three';

export function getMapPlaneY() {
    return 0;
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
        }
    });

    return model;
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