import * as THREE from 'three';
import { planeModelConfig } from '../data/modelConfig.js';
import { loadModel } from '../loaders/modelLoader.js';

const modelPath = `${import.meta.env.BASE_URL}${planeModelConfig.path.replace(/^\/+/, '')}`;

export function createPlaneTemplate() {
    return loadModel(modelPath);
}

export function instantiatePlane(template) {
    const plane = new THREE.Group();
    const model = template.clone(true);

    model.scale.multiplyScalar(planeModelConfig.scale);
    model.rotation.y += planeModelConfig.rotationOffsetY;
    model.traverse(object => {
        if (!object.isMesh) return;
        object.geometry = object.geometry.clone();
        object.material = Array.isArray(object.material) ?
            object.material.map(material => material.clone()) :
            object.material.clone();
    });
    plane.add(model);

    return plane;
}

export function createPlaneAnimator(planeMesh, curve, speed = 0.05, initialProgress = 0) {
    let t = initialProgress;

    function update(delta) {
        t += delta * speed;
        if (t > 1) t = 0; // loop back to start of route

        const position = curve.getPointAt(t);
        const lookAtPoint = curve.getPointAt(Math.min(t + 0.01, 1));

        planeMesh.position.copy(position);
        planeMesh.lookAt(lookAtPoint);
    }

    update.getProgress = () => t;
    return update;
}