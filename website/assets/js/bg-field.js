/* ══════════════════════════════════════════════════════
   FIELD BG — 쌍극자 자기장 배경 (Three.js)
   모바일 우선: 해상도 뭉개짐 수정, 성능 최적화
   v38
══════════════════════════════════════════════════════ */
(function () {
  var canvas = document.getElementById('field-bg');
  if (!canvas || typeof THREE === 'undefined') return;

  /* 접근성 — reduced-motion */
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    canvas.style.display = 'none';
    return;
  }

  /* 디바이스 감지 — isPortrait를 먼저 선언해야 initZ/initFov에서 참조 가능 */
  var isMobile = window.innerWidth < 768;
  var isPortrait = window.innerHeight > window.innerWidth;

  /* ── Renderer ──
     - 모바일: antialias off (성능), DPR 1.5 캡
     - 데스크탑: antialias on, DPR 2 캡
     - setSize 마지막 인자 true: canvas CSS style 업데이트 (해상도 뭉개짐 방지)
  */
  var dpr = isMobile
    ? Math.min(window.devicePixelRatio, 1.5)
    : Math.min(window.devicePixelRatio, 2);

  var renderer = new THREE.WebGLRenderer({
    canvas: canvas,
    alpha: true,
    antialias: !isMobile
  });
  renderer.setPixelRatio(dpr);
  renderer.setClearColor(0x000000, 0);
  /* 초기 크기 설정 — CSS size 동기화 포함 */
  renderer.setSize(window.innerWidth, window.innerHeight, true);

  /* ── Scene & Camera ── */
  var scene = new THREE.Scene();
  var initZ = (isMobile && isPortrait) ? 30 : 22;
  var initFov = (isMobile && isPortrait) ? 48 : 38;

  /* fog: 모바일 세로는 카메라가 더 멀기 때문에 밀도 조정 */
  var fogDensity = 0.030 * (22 / initZ);
  scene.fog = new THREE.FogExp2(0xE3E2E0, fogDensity);

  var fieldGroup = new THREE.Group();
  scene.add(fieldGroup);

  var camera = new THREE.PerspectiveCamera(initFov, window.innerWidth / window.innerHeight, 0.1, 1000);
  camera.position.set(0, 1.2, initZ);
  camera.lookAt(0, 0, 0);

  /* ── 마우스/터치 추적 ── */
  var mouse = { x: 0, y: 0 };
  document.addEventListener('mousemove', function (e) {
    mouse.x = (e.clientX / window.innerWidth - 0.5) * 2;
    mouse.y = (e.clientY / window.innerHeight - 0.5) * 2;
  }, { passive: true });

  /* ── 시간대별 컬러 ── */
  var timeClass = document.documentElement.className;
  var fieldColor, fogHex;
  if (timeClass.indexOf('time-dawn') !== -1) {
    fieldColor = 0x1A1C2E; fogHex = 0xEAEAE8;
  } else if (timeClass.indexOf('time-evening') !== -1) {
    fieldColor = 0x1C0F08; fogHex = 0xE6E5E3;
  } else if (timeClass.indexOf('time-night') !== -1) {
    fieldColor = 0x100E1C; fogHex = 0xDCDCDA;
  } else {
    fieldColor = 0x000000; fogHex = 0xEFEFEB;
  }
  scene.fog.color.setHex(fogHex);

  /* ── 필드라인 파라미터 — 모바일 우선 ── */
  var LINE_COUNT = isMobile ? 18 : 56;
  var SEEDS = isMobile ? 5 : 9;
  var POINTS_PER = isMobile ? 48 : 200;
  var MAX_R = 22.0;
  var SCALE = (isMobile && isPortrait) ? 3.0 : 3.8;

  function buildFieldLine(r0, phi) {
    var pts = new Float32Array(POINTS_PER * 3);
    var baseX = new Float32Array(POINTS_PER);
    var baseY = new Float32Array(POINTS_PER);
    var baseZ = new Float32Array(POINTS_PER);
    var tMin = 0.01, tMax = Math.PI - 0.01;
    for (var i = 0; i < POINTS_PER; i++) {
      var theta = tMin + (i / (POINTS_PER - 1)) * (tMax - tMin);
      var sinT = Math.sin(theta);
      var cosT = Math.cos(theta);
      var r = r0 * sinT * sinT;
      if (r > MAX_R) r = MAX_R;
      pts[i * 3] = r * sinT * Math.cos(phi) * SCALE;
      pts[i * 3 + 1] = r * cosT * SCALE;
      pts[i * 3 + 2] = r * sinT * Math.sin(phi) * SCALE;
      baseX[i] = pts[i * 3];
      baseY[i] = pts[i * 3 + 1];
      baseZ[i] = pts[i * 3 + 2];
    }
    return { pts: pts, baseX: baseX, baseY: baseY, baseZ: baseZ };
  }

  var fieldLines = [];
  var seeds = [];
  for (var si = 0; si < SEEDS; si++) {
    seeds.push(0.4 + Math.pow(si / (SEEDS - 1), 2.2) * 15.0);
  }

  for (var li = 0; li < LINE_COUNT; li++) {
    var phi = (li / LINE_COUNT) * Math.PI * 2;
    for (var si2 = 0; si2 < SEEDS; si2++) {
      var r0 = seeds[si2];
      var frac = (si2 + 1) / SEEDS;
      /* 모바일: 불투명도 낮게, 데스크탑: 적당히 */
      var baseOp = isMobile
        ? (0.10 - frac * 0.05)
        : (0.24 - frac * 0.14);
      var mat = new THREE.LineBasicMaterial({
        color: fieldColor,
        opacity: baseOp,
        transparent: true,
        depthWrite: false,
        linewidth: 1
      });
      var built = buildFieldLine(r0, phi);
      var geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(built.pts, 3));
      fieldGroup.add(new THREE.Line(geo, mat));
      fieldLines.push({
        mat: mat,
        baseOp: baseOp,
        phase: li * (Math.PI * 2 / LINE_COUNT) + si2 * 0.45
      });
    }
  }

  /* ── Dust — 데스크탑만 ── */
  var dustMat = null;
  if (!isMobile) {
    var dustCount = 600;
    var dustGeo = new THREE.BufferGeometry();
    var dustPos = new Float32Array(dustCount * 3);
    for (var di = 0; di < dustCount; di++) {
      var dr = Math.random() * 15 * SCALE;
      var dt = Math.random() * Math.PI;
      var dp = Math.random() * Math.PI * 2;
      dustPos[di * 3] = dr * Math.sin(dt) * Math.cos(dp);
      dustPos[di * 3 + 1] = dr * Math.cos(dt);
      dustPos[di * 3 + 2] = dr * Math.sin(dt) * Math.sin(dp);
    }
    dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
    dustMat = new THREE.PointsMaterial({
      color: 0x000000,
      size: 0.05,
      transparent: true,
      opacity: 0.025,
      sizeAttenuation: true
    });
    fieldGroup.add(new THREE.Points(dustGeo, dustMat));
  }

  /* ── Resize ── */
  var lastW = window.innerWidth;
  var lastH = window.innerHeight;
  var resizeTimer = null;

  function onResize() {
    var W = window.innerWidth;
    var H = window.innerHeight;
    /* 모바일 주소창 show/hide — width 변화 없으면 무시 */
    if (W === lastW && isMobile) return;
    /* 데스크탑 — 미세한 height 변화 무시 */
    if (W === lastW && Math.abs(H - lastH) / lastH < 0.05) return;
    lastW = W; lastH = H;
    /* true: canvas CSS size도 업데이트 — 해상도 동기화 */
    renderer.setSize(W, H, true);
    camera.aspect = W / H;
    camera.updateProjectionMatrix();
    isPortrait = H > W;

    // 레이아웃 스래싱 방지: 높이값 캐싱
    cachedDocH = document.documentElement.scrollHeight - H;
  }

  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(onResize, 200);
  }, { passive: true });

  /* ── Animation ── */
  var clock = new THREE.Clock();
  var targetCamX = 1.2, targetCamY = 0;
  var BASE_Z = initZ, BASE_FOV = initFov;
  var ZOOM_RANGE = isMobile ? 3 : 5;
  var scrollLerp = 0;

  camera.position.set(0, 1.2, BASE_Z);
  camera.fov = BASE_FOV;
  camera.updateProjectionMatrix();

  var cachedDocH = document.documentElement.scrollHeight - window.innerHeight;

  function getRawScroll() {
    return cachedDocH > 10 ? Math.min(1, Math.max(0, window.pageYOffset / cachedDocH)) : 0;
  }

  function animate() {
    requestAnimationFrame(animate);
    var t = clock.getElapsedTime();

    /* 저속 Y 회전 */
    fieldGroup.rotation.y = t * 0.014;

    /* 호흡 */
    var breathe = 1.0 + Math.sin(t * 0.20) * 0.003;
    fieldGroup.scale.set(breathe, breathe, breathe);

    /* 라인 opacity 펄스 */
    for (var fi = 0; fi < fieldLines.length; fi++) {
      var fl = fieldLines[fi];
      fl.mat.opacity = fl.baseOp * (0.80 + 0.20 * Math.sin(t * 0.09 + fl.phase));
    }

    /* 스크롤 줌 */
    scrollLerp += (getRawScroll() - scrollLerp) * 0.04;
    var targetZ = BASE_Z - scrollLerp * ZOOM_RANGE;
    camera.position.z += (targetZ - camera.position.z) * 0.06;
    camera.fov += (BASE_FOV - camera.fov) * 0.06;
    camera.updateProjectionMatrix();

    /* 마우스 틸트 — 모바일은 비활성 */
    if (!isMobile) {
      targetCamX += (1.2 + mouse.y * -0.8 - targetCamX) * 0.04;
      targetCamY += (mouse.x * 1.2 - targetCamY) * 0.04;
      camera.position.x = targetCamY;
      camera.position.y = targetCamX;
    }
    camera.lookAt(0, 0, 0);

    renderer.render(scene, camera);

    /* 프리로더 해제 신호 송신 — 1500ms 이상 경과 후 1회만 */
    if (typeof window.revealField === 'function' && !window.fieldRevealed && t > 1.5) {
      window.revealField();
      window.fieldRevealed = true;
    }
  }
  animate();
})();
