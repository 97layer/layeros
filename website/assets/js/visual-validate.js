/**
 * visual-validate.js
 * CSS 레이아웃 수치 검증 — 스크린샷 없이 숫자로 판단
 * puppeteer_evaluate()로 실행. 이미지 토큰 0.
 *
 * 사용: puppeteer_evaluate(fs.readFileSync('website/assets/js/visual-validate.js', 'utf8'))
 * 또는 인라인으로 함수만 호출
 */

(function validateLayout() {
  const results = { pass: [], fail: [], warn: [] };

  function check(label, value, min, max) {
    const entry = { label, value: Math.round(value) };
    if (value >= min && value <= max) results.pass.push(entry);
    else if (Math.abs(value - (value < min ? min : max)) < 20) results.warn.push({ ...entry, expected: `${min}–${max}` });
    else results.fail.push({ ...entry, expected: `${min}–${max}` });
  }

  function gap(a, b) {
    const ra = document.querySelector(a)?.getBoundingClientRect();
    const rb = document.querySelector(b)?.getBoundingClientRect();
    if (!ra || !rb) return -1;
    return Math.round(rb.top - ra.bottom);
  }

  function rect(sel) {
    return document.querySelector(sel)?.getBoundingClientRect() || null;
  }

  function prop(sel, prop) {
    const el = document.querySelector(sel);
    if (!el) return null;
    return getComputedStyle(el)[prop];
  }

  // ─── 공통 레이아웃 ───────────────────────────────────────
  const nav = rect('.site-nav');
  if (nav) check('nav height', nav.height, 50, 80);

  // ─── Atelier 전용 ────────────────────────────────────────
  const heroToGallery = gap('.atelier-hero', '.atelier-gallery');
  if (heroToGallery >= 0) {
    check('hero→gallery gap', heroToGallery, 0, 10);

    const galleryToInfo = gap('.atelier-gallery', '.atelier-info');
    check('gallery→info gap', galleryToInfo, 0, 20);

    const infoToDetail = gap('.atelier-info', '.atelier-detail');
    check('info→detail gap', infoToDetail, 40, 100);

    // 갤러리 항목 존재 확인
    const galleryItems = document.querySelectorAll('.atelier-gallery__item');
    check('gallery items', galleryItems.length, 3, 3);

    // info 그리드 3컬럼 확인
    const infoGrid = rect('.atelier-info-grid');
    const infoBlock = rect('.atelier-info-block');
    if (infoGrid && infoBlock) {
      check('info-block width ratio', infoBlock.width / infoGrid.width, 0.25, 0.40);
    }

    // 모바일 감지
    const vw = window.innerWidth;
    if (vw <= 768) {
      const heroGrid = prop('.atelier-hero', 'gridTemplateColumns');
      results.pass.push({ label: 'mobile single-col', value: heroGrid });
    }
  }

  // ─── 색상 대비 (CTA 버튼) ────────────────────────────────
  const cta = document.querySelector('.form-submit');
  if (cta) {
    const color = getComputedStyle(cta).color;
    const bg = getComputedStyle(cta).backgroundColor;
    results.pass.push({ label: 'cta color', value: color });
    results.pass.push({ label: 'cta bg', value: bg });
  }

  // ─── data-reveal 잔여 opacity:0 감지 ────────────────────
  const hiddenReveal = [...document.querySelectorAll('[data-reveal]')]
    .filter(el => getComputedStyle(el).opacity === '0').length;
  if (hiddenReveal > 0) {
    results.warn.push({ label: 'data-reveal hidden elements', value: hiddenReveal, expected: 0 });
  }

  return {
    viewport: `${window.innerWidth}×${window.innerHeight}`,
    url: location.pathname,
    pass: results.pass.length,
    fail: results.fail.length,
    warn: results.warn.length,
    details: {
      pass: results.pass,
      warn: results.warn,
      fail: results.fail,
    },
    verdict: results.fail.length === 0 ? '✅ PASS' : `❌ FAIL (${results.fail.length}건)`,
  };
})();
