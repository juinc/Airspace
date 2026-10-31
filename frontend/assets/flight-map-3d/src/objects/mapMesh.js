import * as THREE from 'three';

export function createLights(scene) {
    const ambient = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambient);

    const directional = new THREE.DirectionalLight(0xffffff, 1);
    directional.position.set(10, 20, 10);
    directional.castShadow = true;

    // Shadow camera bounds — how large an area can cast/receive shadows
    directional.shadow.camera.left = -20;
    directional.shadow.camera.right = 20;
    directional.shadow.camera.top = 20;
    directional.shadow.camera.bottom = -20;

    scene.add(directional);
}   model.scale.y *= (scaleX + scaleZ) / 2;
    model.scale.z *= scaleZ;
    model.updateWorldMatrix(true, true);

    const fittedBounds = new THREE.Box3().setFromObject(model);
    const center = fittedBounds.getCenter(new THREE.Vector3());
    model.position.x += (sceneBounds.min_x + sceneBounds.max_x) / 2 - center.x;
    model.position.z += (sceneBounds.min_z + sceneBounds.max_z) / 2 - center.z;
    model.position.y += getMapPlaneY() - fittedBounds.max.y;

    model.scale.y *= 2;

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