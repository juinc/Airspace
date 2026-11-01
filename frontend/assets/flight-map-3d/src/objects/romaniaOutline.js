import * as THREE from 'three';

/**
 * Draws the Romania border polygon (scene coords from meta.romania_border)
 * as a translucent fill + glowing outline, laid flat on the terrain.
 * Call updateRomaniaBorder(group, border) every time a new payload arrives —
 * it replaces the previous border automatically.
 */
export function updateRomaniaBorder(group, borderPoints) {
    const old = group.getObjectByName('romaniaBorder');
    if (old) {
        group.remove(old);
        old.traverse((obj) => {
            if (obj.geometry) obj.geometry.dispose();
            if (obj.material) obj.material.dispose();
        });
    }
    if (!borderPoints || borderPoints.length < 3) return;

    const borderGroup = new THREE.Group();
    borderGroup.name = 'romaniaBorder';

    // Fill — very subtle, just enough to read the country's silhouette.
    const shape = new THREE.Shape();
    borderPoints.forEach((p, i) => {
        if (i === 0) shape.moveTo(p.x, p.z);
        else shape.lineTo(p.x, p.z);
    });
    const fillGeometry = new THREE.ShapeGeometry(shape);
    fillGeometry.rotateX(Math.PI / 2); // shape (x, z) -> scene (x, 0, z)
    const fillMaterial = new THREE.MeshBasicMaterial({
        color: 0x1a3a4f,
        transparent: true,
        opacity: 0.25,
        side: THREE.DoubleSide,
        depthWrite: false,
    });
    const fill = new THREE.Mesh(fillGeometry, fillMaterial);
    fill.position.y = 0.05;
    borderGroup.add(fill);

    // Outline — crisp glowing line slightly above the fill.
    const linePoints = borderPoints.map(
        (p) => new THREE.Vector3(p.x, 0.35, p.z)
    );
    const lineGeometry = new THREE.BufferGeometry().setFromPoints(linePoints);
    const lineMaterial = new THREE.LineBasicMaterial({
        color: 0x9adcf0,
        transparent: true,
        opacity: 0.95,
    });
    const line = new THREE.Line(lineGeometry, lineMaterial);
    borderGroup.add(line);

    group.add(borderGroup);
}