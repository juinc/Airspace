import * as THREE from 'three';

export function getMapPlaneY(gridConfig) {
    const { size, cubeSize, spacing } = gridConfig;
    return -(size * (cubeSize + spacing) - spacing) / 2;
}

export function createMapMesh(model, gridConfig) {
    const bounds = new THREE.Box3().setFromObject(model);
    const targetWidth = gridConfig.size * (gridConfig.cubeSize + gridConfig.spacing) -
        gridConfig.spacing;
    model.scale.multiplyScalar(targetWidth / bounds.getSize(new THREE.Vector3()).x);
    model.updateWorldMatrix(true, true);

    const fittedBounds = new THREE.Box3().setFromObject(model);
    const center = fittedBounds.getCenter(new THREE.Vector3());
    model.position.x -= center.x;
    model.position.z -= center.z;
    model.position.y += getMapPlaneY(gridConfig) - fittedBounds.min.y;

    model.scale.y *= 2;

    model.traverse(object => {
        if (object.isMesh) {
            object.castShadow = true;
            object.receiveShadow = true;
        }
    });

    return model;
}