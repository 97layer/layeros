import * as THREE from './three_src/three.module.js';
import { GLTFLoader } from './three_src/GLTFLoader.js';

window.__hairRendererLoaded = true;
const canvas = document.getElementById('hair-canvas');
if (!canvas) throw new Error('hair-canvas not found');

const style = canvas.dataset.style || 'medium_natural';
const W = 90, H = 140;

const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(W, H);
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
const aspect = W / H;
const frustum = 2.2;
const camera = new THREE.OrthographicCamera(
  -frustum * aspect,  frustum * aspect,
   frustum,           -frustum,
  0.1, 20
);
camera.position.set(0, 0, 6);
camera.lookAt(0, 0.3, 0);

const ambient = new THREE.AmbientLight(0xfaf9f6, 1.2);
scene.add(ambient);
const key = new THREE.DirectionalLight(0xffffff, 1.0);
key.position.set(1.5, 3, 4);
scene.add(key);
const rim = new THREE.DirectionalLight(0xddd8cc, 0.3);
rim.position.set(-2, -1, 2);
scene.add(rim);

const loader = new GLTFLoader();
loader.load(
  `/assets/3d/hair_${style}.glb`,
  (gltf) => {
    const model = gltf.scene;
    const box = new THREE.Box3().setFromObject(model);
    const center = box.getCenter(new THREE.Vector3());
    model.position.sub(center);
    model.position.y += 0.1;
    scene.add(model);
    renderer.render(scene, camera);
    let t = 0;
    function tick() {
      requestAnimationFrame(tick);
      t += 0.004;
      model.rotation.y = Math.sin(t) * 0.12;
      renderer.render(scene, camera);
    }
    tick();
  },
  undefined,
  (err) => {
    console.warn('Hair model load failed:', err);
    canvas.style.display = 'none';
  }
);
