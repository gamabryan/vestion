// Rosto 3D da Lia: cabeça em malha de pontos e linhas, anel HUD e fundo de circuitos.
// Lê o estado e o volume da fala de window.lia (definido em app.js).
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true });
} catch (e) {
  document.body.classList.add("no-webgl");  // plano B: núcleo simples em CSS
  throw e;
}
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
document.body.prepend(renderer.domElement);

const scene = new THREE.Scene();
const PALETTES = {
  cyan: { idle: 0x3aa8d8, listening: 0x5fe4ff, thinking: 0xa98bff, speaking: 0x6feaff,
          dust: 0x4fb8e0, circuit: 0x2a7fb0, dot: 0x9ff0ff, fog: 0x01040a },
  red: { idle: 0xd83040, listening: 0xff4a5c, thinking: 0xff8a3d, speaking: 0xff5c6a,
         dust: 0xe0404f, circuit: 0xb02a36, dot: 0xffa3aa, fog: 0x0a0103 },
};
const initial = PALETTES[(window.lia && window.lia.theme) || "cyan"] || PALETTES.cyan;
scene.fog = new THREE.FogExp2(initial.fog, 0.09);
const camera = new THREE.PerspectiveCamera(38, innerWidth / innerHeight, 0.1, 100);
camera.position.set(0, -0.05, 5.4);

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.75, 0.45, 0.05);
composer.addPass(bloom);

const COLORS = {
  idle: new THREE.Color(initial.idle),
  listening: new THREE.Color(initial.listening),
  thinking: new THREE.Color(initial.thinking),
  speaking: new THREE.Color(initial.speaking),
};
const tint = COLORS.idle.clone();

// ---------- cabeça procedural, de frente ----------
const g = (x, y, cx, cy, sx, sy) => Math.exp(-((x - cx) ** 2) / sx - ((y - cy) ** 2) / sy);
function headPoint(d) {
  let x = d.x * 0.74, y = d.y * 0.94, z = d.z * 0.84;
  if (y > 0.35) x *= 1 - 0.18 * (y - 0.35);
  if (y < -0.15) { const t = Math.min(1, (-y - 0.15) / 0.8); x *= 1 - 0.42 * t * t; z *= 1 - 0.1 * t; }
  if (z > 0) {
    for (const ex of [-0.27, 0.27]) z -= 0.13 * g(x, y, ex, 0.12, 0.012, 0.006);       // órbitas
    z += 0.05 * Math.exp(-((y - 0.27) ** 2) / 0.004) * Math.exp(-(x * x) / 0.16);       // sobrancelha
    z += 0.24 * g(x, y, 0, -0.08, 0.006, 0.05);                                         // nariz
    z += 0.06 * g(x, y, 0, -0.2, 0.01, 0.004);                                          // ponta do nariz
    for (const cx of [-0.36, 0.36]) z += 0.045 * g(x, y, cx, -0.06, 0.02, 0.01);       // maçãs
    z += 0.045 * g(x, y, 0, -0.43, 0.03, 0.004);                                        // lábios
    z += 0.05 * g(x, y, 0, -0.78, 0.03, 0.02);                                          // queixo
  }
  return new THREE.Vector3(x, y, z);
}

const pts = [], isJaw = [];
const N = 2600, golden = Math.PI * (3 - Math.sqrt(5));
let seed = 7;
const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);  // mesmo rosto sempre
for (let i = 0; i < N; i++) {
  const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), th = golden * i;
  const d = new THREE.Vector3(Math.cos(th) * r, y, Math.sin(th) * r);
  if (d.z < -0.2 && rand() < 0.75) continue;
  const p = headPoint(d);
  if (Math.abs(p.x) < 0.17 && Math.abs(p.y + 0.445) < 0.018 && p.z > 0.3) continue;   // fenda da boca
  pts.push(p);
  isJaw.push(p.y < -0.44 && p.z > -0.25 && Math.abs(p.x) < 0.6);
}
for (let i = 0; i < 260; i++) {                                                         // pescoço
  const a = rand() * Math.PI * 2, y = -0.8 - rand() * 0.8;
  pts.push(new THREE.Vector3(Math.cos(a) * 0.3, y, Math.sin(a) * 0.27));
  isJaw.push(false);
}
const P = pts.length;

const cell = 0.14, grid = new Map();
const key = (x, y, z) => `${x},${y},${z}`;
const cellOf = (p) => [Math.floor(p.x / cell), Math.floor(p.y / cell), Math.floor(p.z / cell)];
pts.forEach((p, i) => { const k = key(...cellOf(p)); (grid.get(k) || grid.set(k, []).get(k)).push(i); });
const pairs = [], deg = new Uint8Array(P);
for (let i = 0; i < P; i++) {
  const [cx, cy, cz] = cellOf(pts[i]);
  for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) for (let c = -1; c <= 1; c++) {
    for (const j of grid.get(key(cx + a, cy + b, cz + c)) || []) {
      if (j <= i || deg[i] >= 4 || deg[j] >= 4) continue;
      if (pts[i].distanceTo(pts[j]) < 0.115) { pairs.push(i, j); deg[i]++; deg[j]++; }
    }
  }
}

const head = new THREE.Group();
scene.add(head);

const pos = new Float32Array(P * 3), phase = new Float32Array(P), feature = new Float32Array(P);
pts.forEach((p, i) => {
  pos.set([p.x, p.y, p.z], i * 3);
  phase[i] = rand() * 6.28;
  feature[i] = p.z > 0.2 ? Math.min(1, 1.6 * (
    g(p.x, p.y, 0, -0.08, 0.004, 0.05) + g(p.x, p.y, 0, -0.43, 0.035, 0.004) +
    Math.exp(-((p.y - 0.27) ** 2) / 0.003) * Math.exp(-(p.x * p.x) / 0.12) +
    g(p.x, p.y, -0.27, 0.12, 0.02, 0.012) + g(p.x, p.y, 0.27, 0.12, 0.02, 0.012) + g(p.x, p.y, 0, -0.8, 0.02, 0.01))) : 0;
});
const pointGeo = new THREE.BufferGeometry();
pointGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
pointGeo.setAttribute("aPhase", new THREE.BufferAttribute(phase, 1));
pointGeo.setAttribute("aFeature", new THREE.BufferAttribute(feature, 1));
const pointMat = new THREE.ShaderMaterial({
  transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  uniforms: { uTime: { value: 0 }, uLevel: { value: 0 }, uColor: { value: tint } },
  vertexShader: `
    attribute float aPhase; attribute float aFeature;
    uniform float uTime; uniform float uLevel; varying float vA;
    void main() {
      vec4 mv = modelViewMatrix * vec4(position, 1.0);
      vec3 n = normalize(normalMatrix * normalize(position * vec3(1.0, 0.8, 1.0)));
      float rim = pow(1.0 - abs(n.z), 2.0);
      float tw = 0.6 + 0.4 * sin(uTime * 2.2 + aPhase);
      vA = tw * (0.12 + 0.75 * rim + 0.8 * aFeature) + uLevel * 0.5 * aFeature;
      gl_PointSize = (1.6 + 1.6 * aFeature + 1.0 * rim + uLevel * 1.5) * (5.4 / -mv.z);
      gl_Position = projectionMatrix * mv;
    }`,
  fragmentShader: `
    uniform vec3 uColor; varying float vA;
    void main() {
      float a = smoothstep(0.5, 0.0, length(gl_PointCoord - 0.5));
      gl_FragColor = vec4(uColor * 1.25, a * vA);
    }`,
});
head.add(new THREE.Points(pointGeo, pointMat));

const linePos = new Float32Array(pairs.length * 3);
const lineGeo = new THREE.BufferGeometry();
lineGeo.setAttribute("position", new THREE.BufferAttribute(linePos, 3));
const lineMat = new THREE.LineBasicMaterial({ color: tint, transparent: true, opacity: 0.14,
                                              blending: THREE.AdditiveBlending, depthWrite: false });
head.add(new THREE.LineSegments(lineGeo, lineMat));

const eyes = [];
for (const ex of [-0.27, 0.27]) {
  const eye = new THREE.Group();
  eye.position.set(ex, 0.12, 0.62);
  const glow = new THREE.Mesh(new THREE.SphereGeometry(0.03, 24, 24), new THREE.MeshBasicMaterial({ color: 0xffffff }));
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.06, 0.072, 48),
                              new THREE.MeshBasicMaterial({ color: tint, transparent: true, opacity: 0.8, side: THREE.DoubleSide }));
  eye.add(glow, ring);
  head.add(eye);
  eyes.push({ eye, glow, ring });
}

// ---------- anel HUD ----------
const hud = new THREE.Group();
hud.position.set(0, 0.2, -0.7);
scene.add(hud);
const hudMats = [];
function circle(r, segs, dashed, arc, op) {
  const ps = [];
  for (let i = 0; i <= segs; i++) { const a = (i / segs) * arc; ps.push(new THREE.Vector3(Math.cos(a) * r, Math.sin(a) * r, 0)); }
  const mat = dashed ? new THREE.LineDashedMaterial({ color: tint, dashSize: 0.04, gapSize: 0.05, transparent: true, opacity: op })
                     : new THREE.LineBasicMaterial({ color: tint, transparent: true, opacity: op });
  hudMats.push(mat);
  const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(ps), mat);
  if (dashed) l.computeLineDistances();
  return l;
}
const rings = [circle(1.55, 200, false, Math.PI * 2, 0.25), circle(1.68, 200, true, Math.PI * 2, 0.5),
               circle(1.82, 120, false, Math.PI * 0.7, 0.8), circle(1.82, 120, false, Math.PI * 0.4, 0.8),
               circle(1.95, 200, true, Math.PI * 2, 0.25)];
rings.forEach((r) => hud.add(r));
const ticks = new THREE.Group();
const tickMat = new THREE.LineBasicMaterial({ color: tint, transparent: true, opacity: 0.45 });
hudMats.push(tickMat);
for (let i = 0; i < 72; i++) {
  const a = (i / 72) * Math.PI * 2, r2 = i % 6 === 0 ? 1.66 : 1.63;
  ticks.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(Math.cos(a) * 1.6, Math.sin(a) * 1.6, 0), new THREE.Vector3(Math.cos(a) * r2, Math.sin(a) * r2, 0)]), tickMat));
}
hud.add(ticks);

// ---------- fundo ----------
const dustN = 1400, dustPos = new Float32Array(dustN * 3);
for (let i = 0; i < dustN; i++) dustPos.set([(rand() - 0.5) * 14, (rand() - 0.5) * 9, -1.5 - rand() * 6], i * 3);
const dustGeo = new THREE.BufferGeometry();
dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPos, 3));
const dust = new THREE.Points(dustGeo, new THREE.PointsMaterial({ color: initial.dust, size: 0.018, transparent: true, opacity: 0.55,
                                                                   blending: THREE.AdditiveBlending, depthWrite: false }));
scene.add(dust);

const circuits = [], circuitMats = [], dotMats = [];
for (let k = 0; k < 26; k++) {
  const side = k % 2 ? 1 : -1;
  let x = side * (1.9 + rand() * 0.4), y = (rand() - 0.5) * 3.6;
  const path = [new THREE.Vector3(x, y, -2.2)];
  for (let s = 0; s < 4; s++) {
    if (s % 2 === 0) x += side * (0.4 + rand() * 1.4); else y += (rand() - 0.5) * 0.9;
    path.push(new THREE.Vector3(x, y, -2.2));
  }
  const lineMatC = new THREE.LineBasicMaterial({ color: initial.circuit, transparent: true, opacity: 0.35 });
  circuitMats.push(lineMatC);
  scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(path), lineMatC));
  const dotMat = new THREE.MeshBasicMaterial({ color: initial.dot });
  dotMats.push(dotMat);
  const dot = new THREE.Mesh(new THREE.SphereGeometry(0.018, 8, 8), dotMat);
  scene.add(dot);
  const lens = []; let total = 0;
  for (let i = 1; i < path.length; i++) { const l = path[i].distanceTo(path[i - 1]); lens.push(l); total += l; }
  circuits.push({ path, lens, total, dot, t: rand(), speed: 0.08 + rand() * 0.12 });
}

// ---------- interação e animação ----------
const mouse = new THREE.Vector2(), look = new THREE.Vector2();
addEventListener("pointermove", (e) => mouse.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1));
addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight); composer.setSize(innerWidth, innerHeight);
});

function voiceLevel() {
  const env = window.lia && window.lia.envelope;
  if (!env) return 0;
  const idx = Math.floor((performance.now() - env.start) / env.frameMs);
  return idx >= 0 && idx < env.values.length ? env.values[idx] : 0;
}

const hinge = new THREE.Vector3(0, -0.2, -0.2);
const clock = new THREE.Clock();
let level = 0;

function animate() {
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();
  const state = (window.lia && window.lia.state) || "idle";
  const target = state === "speaking" ? voiceLevel() : state === "listening" ? 0.25 + 0.2 * Math.sin(t * 6) ** 2 : 0;
  level += (target - level) * 0.35;

  tint.lerp(COLORS[state] || COLORS.idle, 0.05);
  pointMat.uniforms.uTime.value = t;
  pointMat.uniforms.uLevel.value = level;
  lineMat.color.copy(tint);  // a malha acompanha o estado e o tema de cor
  lineMat.opacity = 0.11 + level * 0.18 + (state === "thinking" ? 0.08 * Math.sin(t * 8) ** 2 : 0);
  bloom.strength = 0.7 + level * 0.45 + (state === "idle" ? -0.2 : 0);

  const ang = -level * 0.16, cosA = Math.cos(ang), sinA = Math.sin(ang);
  for (let i = 0; i < P; i++) {
    if (!isJaw[i]) continue;
    const p = pts[i], y = p.y - hinge.y, z = p.z - hinge.z;
    pos[i * 3 + 1] = hinge.y + y * cosA - z * sinA;
    pos[i * 3 + 2] = hinge.z + y * sinA + z * cosA;
  }
  pointGeo.attributes.position.needsUpdate = true;
  for (let k = 0; k < pairs.length; k++) {
    const i = pairs[k];
    linePos[k * 3] = pos[i * 3]; linePos[k * 3 + 1] = pos[i * 3 + 1]; linePos[k * 3 + 2] = pos[i * 3 + 2];
  }
  lineGeo.attributes.position.needsUpdate = true;

  look.lerp(mouse, 0.05);
  head.rotation.y = look.x * 0.45 + Math.sin(t * 0.35) * 0.04;
  head.rotation.x = -look.y * 0.22 + Math.sin(t * 0.5) * 0.02;
  head.position.y = 0.18 + Math.sin(t * 0.8) * 0.02;

  const blink = (t % 4.2) < 0.12 ? 0.1 : 1;
  for (const e of eyes) {
    e.glow.scale.setScalar(1 + level * 0.5 + (state === "listening" ? 0.25 : 0));
    e.ring.rotation.z = t * (state === "thinking" ? 4 : 0.6);
    e.ring.material.color.copy(tint);
    e.eye.scale.y = blink;
  }

  const spin = state === "thinking" ? 3 : 1;
  rings[1].rotation.z = t * 0.15 * spin;
  rings[2].rotation.z = -t * 0.4 * spin;
  rings[3].rotation.z = Math.PI - t * 0.4 * spin;
  rings[4].rotation.z = -t * 0.08;
  ticks.rotation.z = t * 0.05;
  hud.scale.setScalar(1 + level * 0.04 + (state === "listening" ? 0.02 * Math.sin(t * 6) : 0));
  hudMats.forEach((m) => m.color.copy(tint));

  dust.rotation.y = t * 0.01;
  dust.rotation.z = t * (state === "thinking" ? 0.03 : 0.004);
  for (const c of circuits) {
    c.t = (c.t + c.speed * 0.016 * (state === "thinking" ? 3 : 1)) % 1;
    let dist = c.t * c.total, i = 0;
    while (i < c.lens.length - 1 && dist > c.lens[i]) { dist -= c.lens[i]; i++; }
    c.dot.position.lerpVectors(c.path[i], c.path[i + 1], Math.min(1, dist / c.lens[i]));
  }
  camera.position.x = look.x * 0.15;
  camera.lookAt(0, 0, 0);
  composer.render();
}
animate();

// Troca de tema (app.js chama ao clicar no botão do topo). O tom do rosto acompanha aos poucos.
window.liaSetFaceTheme = (name) => {
  const p = PALETTES[name] || PALETTES.cyan;
  for (const k of ["idle", "listening", "thinking", "speaking"]) COLORS[k].setHex(p[k]);
  dust.material.color.setHex(p.dust);
  circuitMats.forEach((m) => m.color.setHex(p.circuit));
  dotMats.forEach((m) => m.color.setHex(p.dot));
  scene.fog.color.setHex(p.fog);
};
window.liaFaceReady = true;
