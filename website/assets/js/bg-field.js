/* ══════════════════════════════════════════════════════
   FIELD BG — 전체 페이지 배경 쌍극자 자기장 (Three.js)
   품질 압도적 향상: 초정밀 밀도, 깊이 렌더링, 정교한 포그, 부드러운 감쇄
   출처: index.html
══════════════════════════════════════════════════════ */
(function () {
  var canvas = document.getElementById('field-bg');
  if (!canvas || typeof THREE === 'undefined') return;

  /* ── prefers-reduced-motion: 접근성 — 애니메이션 비활성화 ── */
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    canvas.style.display = 'none';
    return;
  }

  /* ── 모바일 감지 — 부하 경량화 모드 전환용 ── */
  var isMobile = window.innerWidth < 768;

  /* ── Renderer ── */
  var renderer = new THREE.WebGLRenderer({
    canvas: canvas,
    alpha: true,
    antialias: true
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);

  /* ── Scene & Camera ── */
  var scene = new THREE.Scene();
  /* 깊이감: 멀수록 배경으로 녹아드는 지수 안개 */
  scene.fog = new THREE.FogExp2(0xE3E2E0, 0.042);

  var fieldGroup = new THREE.Group();
  scene.add(fieldGroup);

  var camera = new THREE.PerspectiveCamera(42, window.innerWidth / window.innerHeight, 0.1, 1000);
  camera.position.set(0, 1.2, 22);
  camera.lookAt(0, 0, 0);

  /* ── 마우스 추적 (관성 적용) ── */
  var mouse = { x: 0, y: 0 };
  document.addEventListener('mousemove', function (e) {
    mouse.x = (e.clientX / window.innerWidth - 0.5) * 2;
    mouse.y = (e.clientY / window.innerHeight - 0.5) * 2;
  });

  /* ── 시간대별 컬러 팔레트 ── */
  var timeClass = document.documentElement.className;
  var fieldColor, fogHex;
  if (timeClass === 'time-dawn') {
    fieldColor = 0x1A1C2E; fogHex = 0xEAEAE8; /* 새벽: 차고 깊음 */
  } else if (timeClass === 'time-evening') {
    fieldColor = 0x1C0F08; fogHex = 0xE6E5E3; /* 저녁: 따뜻하고 어두움 */
  } else if (timeClass === 'time-night') {
    fieldColor = 0x100E1C; fogHex = 0xDCDCDA; /* 밤: 어둡고 차갑게 */
  } else {
    fieldColor = 0x000000; fogHex = 0xE3E2E0; /* 낮: 기준 */
  }
  scene.fog.color.setHex(fogHex);

  /* ── 쌍극자 필드라인 파라미터 (V37: 가시성 보정 — 맑지만 선명하게) ── */
  var isPortrait = window.innerHeight > window.innerWidth;
  var LINE_COUNT = isMobile ? 32 : 80;
  var SEEDS = isMobile ? 6 : 14;
  var POINTS_PER = isMobile ? 60 : 180;
  var MAX_R = 22.0;
  var SCALE = (isMobile && isPortrait) ? 3.0 : 3.8;

  function buildFieldLine(r0, phi) {
    var pts = new Float32Array(POINTS_PER * 3);
    var baseX = new Float32Array(POINTS_PER);
    var baseY = new Float32Array(POINTS_PER);
    var baseZ = new Float32Array(POINTS_PER);
    var tMin = 0.01;
    var tMax = Math.PI - 0.01;
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

  /* 지수적 분포 씨앗: 형태감을 위해 지수 소폭 상향 (1.8 -> 2.2) */
  var seeds = [];
  for (var si = 0; si < SEEDS; si++) {
    seeds.push(0.4 + Math.pow(si / (SEEDS - 1), 2.2) * 15.0);
  }

  for (var li = 0; li < LINE_COUNT; li++) {
    var phi = (li / LINE_COUNT) * Math.PI * 2;
    for (var si2 = 0; si2 < SEEDS; si2++) {
      var r0 = seeds[si2];
      var frac = (si2 + 1) / SEEDS;

      /* 극(pole) 근처 진하게, 바깥으로 갈수록 소멸 */
      var baseOp = isMobile ? (0.15 - frac * 0.10) : (0.30 - frac * 0.22);
      var col = fieldColor;

      var mat = new THREE.LineBasicMaterial({
        color: col,
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
        phase: li * (Math.PI * 2 / LINE_COUNT) + si2 * 0.45,
        geo: geo,
        pts: built.pts,
        baseX: built.baseX,
        baseY: built.baseY,
        baseZ: built.baseZ,
        frac: frac
      });
    }
  }

  /* ── 분진 레이어 (Particle Dust) — 모바일에서 완전 제거하여 성능 확보 ── */
  var dustSystem = null;
  var dustMat = null;
  if (!isMobile) {
    var dustCount = 2000;
    var dustGeo = new THREE.BufferGeometry();
    var dustPos = new Float32Array(dustCount * 3);
    for (var di = 0; di < dustCount; di++) {
      var r = Math.random() * 15 * SCALE;
      var theta = Math.random() * Math.PI;
      var phi = Math.random() * Math.PI * 2;
      dustPos[di * 3] = r * Math.sin(theta) * Math.cos(phi);
      dustPos[di * 3 + 1] = r * Math.cos(theta);
      dustPos[di * 3 + 2] = r * Math.sin(theta) * Math.sin(phi);
    }
    dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
    dustMat = new THREE.PointsMaterial({
      color: 0x000000,
      size: 0.05,
      transparent: true,
      opacity: 0.06,
      sizeAttenuation: true
    });
    dustSystem = new THREE.Points(dustGeo, dustMat);
    fieldGroup.add(dustSystem);
  }

  var lastW = window.innerWidth;
  function onResize() {
    var W = window.innerWidth;
    var H = window.innerHeight;
    if (isMobile && W === lastW && Math.abs(H - renderer.domElement.height / renderer.getPixelRatio()) < 100) return;
    lastW = W;
    renderer.setSize(W, H, false);
    camera.aspect = W / H;
    camera.updateProjectionMatrix();
    isPortrait = H > W;
  }
  onResize();
  window.addEventListener('resize', onResize, { passive: true });

  /* ── 정교한 애니메이션 루프 ── */
  var clock = new THREE.Clock();

  /* 카메라 완전 고정 */
  camera.position.set(0, 1.2, 22);
  camera.fov = 38;
  camera.updateProjectionMatrix();

  var targetCamX = 1.2, targetCamY = 0;
  var BASE_Z = 22, BASE_FOV = 38;

  function animate() {
    requestAnimationFrame(animate);
    var t = clock.getElapsedTime();

    /* Y축 저속 회전 — 더 느리게, 더 관조적으로 */
    fieldGroup.rotation.y = t * 0.016;

    /* 미세 호흡: 전체 필드가 4.5초 주기로 아주 조금 팽창/수축 */
    var breathe = 1.0 + Math.sin(t * 0.22) * 0.004;
    fieldGroup.scale.set(breathe, breathe, breathe);

    /* 라인별 opacity 호흡 — 각 라인이 미세하게 다른 타이밍으로 */
    for (var fi = 0; fi < fieldLines.length; fi++) {
      var fl = fieldLines[fi];
      fl.mat.opacity = fl.baseOp * (0.82 + 0.18 * Math.sin(t * 0.10 + fl.phase));
    }

    /* 스크롤 줌 비활성화 — 페이지 구조 단축으로 ratio 튐 방지 */
    camera.position.z += (BASE_Z - camera.position.z) * 0.06;
    camera.fov += (BASE_FOV - camera.fov) * 0.06;
    camera.updateProjectionMatrix();

    /* 마우스 틸트 — 감도 절제 */
    targetCamX += (1.2 + mouse.y * -1.0 - targetCamX) * 0.04;
    targetCamY += (mouse.x * 1.4 - targetCamY) * 0.04;
    camera.position.x = targetCamY;
    camera.position.y = targetCamX;
    camera.lookAt(0, 0, 0);

    if (dustMat) dustMat.opacity = 0.025;

    renderer.render(scene, camera);

    if (!window.__fieldReady) {
      window.__fieldReady = true;
      var elapsed = performance.now();
      var preloader = document.getElementById('preloader');
      if (preloader) {
        preloader.classList.add('is-revealing');
        setTimeout(function () {
          document.body.classList.add('is-loaded');
        }, 300);
      }
    }
  }
  animate();
})();

(function () {
  var scrollRatio = 0;
  var lerpRatio = 0;

  function updateScroll() {
    /* window.innerHeight 대신 clientHeight를 사용하여 주소창 변화에 의한 튕김 방지 */
    var viewportH = document.documentElement.clientHeight;
    var docH = document.documentElement.scrollHeight - viewportH;
    scrollRatio = docH > 0 ? window.scrollY / docH : 0;
  }
  window.addEventListener('scroll', updateScroll, { passive: true });
  window.addEventListener('resize', updateScroll, { passive: true });
  updateScroll();

  window._fieldState = {
    get ratio() { return lerpRatio; }
  };

  (function lerpLoop() {
    lerpRatio += (scrollRatio - lerpRatio) * 0.035; /* 관성 증가 */
    requestAnimationFrame(lerpLoop);
  })();
})();
