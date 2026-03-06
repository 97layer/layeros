/*!
 * WOOHWAHAE Lab — Concept Sprint V2 Interior controller
 */

(function () {
  'use strict';

  var root = document.body;
  if (!root || !root.classList.contains('page-lab-sprint')) return;

  var configs = {
    a: {
      id: 'Track A',
      name: 'Quiet Grid',
      thesis: '정보 밀도를 낮추고 구조 신뢰를 우선. 운영 페이지까지 같은 문법으로 연결한다.',
      type: 'IBM Plex Mono 비중 확대, 본문은 Pretendard 최소 단위 유지',
      motion: '0.24s 단발성 전환, 과한 easing 제거',
      layout: '2열 기준선 고정, 카드/컨트롤 간격 계단식 통일',
      interior: '직선 동선, 노출형 수납, 낮은 대비의 재료 배합',
      risk: '정서적 임팩트가 약해질 수 있음',
      stageLabel: 'Quiet Grid',
      stageCopy: '정보는 선형으로, 결정은 빠르게.',
      defaultIntensity: 58,
      defaultOpenness: 64,
      metrics: {
        consistency: 86,
        sensory: 71,
        operational: 88,
        risk: 36
      },
      materials: [
        { name: 'Lime Plaster', role: '벽체', tone: '#d8d6d1' },
        { name: 'Brushed Steel', role: '작업대', tone: '#b7b6b1' },
        { name: 'Ash Wood', role: '수납', tone: '#bab4a9' },
        { name: 'Fog Glass', role: '파티션', tone: '#e2e2df' }
      ],
      lights: [76, 62, 58, 66, 48, 72],
      flow: [
        '입구 시선축에서 오늘의 서비스 타입을 즉시 인식',
        '상담 테이블에서 기록/스타일 보드를 동시에 확인',
        '커팅 존은 직선 동선으로 손 동작의 낭비 최소화',
        '마감 존에서 촬영과 결제를 같은 시퀀스로 결합'
      ],
      zones: {
        entry: {
          name: 'Entry',
          meta: '도입 리셉션',
          note: '입구에서 핵심 축이 바로 읽히게 구성합니다.'
        },
        consult: {
          name: 'Consult',
          meta: '상담/기록',
          note: '상담 테이블과 기록 모니터를 같은 시야선에 둡니다.'
        },
        cut: {
          name: 'Cut',
          meta: '메인 작업대',
          note: '작업대 간격을 일정하게 맞춰 동작 리듬을 고정합니다.'
        },
        finish: {
          name: 'Finish',
          meta: '스타일링/촬영',
          note: '마감 존 조명 대비를 높여 결과물을 안정적으로 확보합니다.'
        }
      }
    },
    b: {
      id: 'Track B',
      name: 'Ritual Flow',
      thesis: '느림의 리듬을 전면화. 동일한 콘텐츠를 더 깊은 몰입 흐름으로 재배치한다.',
      type: '헤더 대비 강화, 레이블은 얇고 본문은 호흡 간격 확장',
      motion: '1.10s 지연형 페이드 + 스태거',
      layout: '비대칭 흐름, 장면 단위 블록 전환',
      interior: '곡선 동선, 낮은 조도 중심, 레이어형 소재 중첩',
      risk: '운영 페이지에서 과연출로 읽힐 수 있음',
      stageLabel: 'Ritual Flow',
      stageCopy: '장면은 느리게, 인상은 깊게.',
      defaultIntensity: 74,
      defaultOpenness: 51,
      metrics: {
        consistency: 78,
        sensory: 91,
        operational: 69,
        risk: 58
      },
      materials: [
        { name: 'Dark Stucco', role: '벽체', tone: '#9a9790' },
        { name: 'Smoked Mirror', role: '포인트', tone: '#b2b0aa' },
        { name: 'Charcoal Fabric', role: '라운지', tone: '#86827c' },
        { name: 'Oil Stone', role: '카운터', tone: '#a5a29b' }
      ],
      lights: [42, 55, 78, 88, 63, 46],
      flow: [
        '입구 앞 전이 존에서 조도 전환으로 속도를 늦춤',
        '상담 존에서 재료 샘플과 헤어 히스토리를 레이어링',
        '커팅 존은 집중형 스폿 조명으로 장면 몰입 강화',
        '마감 존은 저속 모션과 촬영 동선을 분리해 여운 확보'
      ],
      zones: {
        entry: {
          name: 'Threshold',
          meta: '전이 게이트',
          note: '문턱 구간에서 밝기와 소리를 단계적으로 낮춥니다.'
        },
        consult: {
          name: 'Ritual Desk',
          meta: '상담 라운지',
          note: '상담을 브리핑이 아닌 의식 흐름으로 느끼게 설계합니다.'
        },
        cut: {
          name: 'Core Stage',
          meta: '집중 작업대',
          note: '작업 장면만 도드라지도록 주변 광량을 억제합니다.'
        },
        finish: {
          name: 'Afterglow',
          meta: '여운 존',
          note: '마감 직후 촬영과 제품 안내를 느린 리듬으로 연결합니다.'
        }
      }
    }
  };

  var ids = {
    id: document.getElementById('sprint-current-id'),
    name: document.getElementById('sprint-current-name'),
    thesis: document.getElementById('sprint-thesis'),
    type: document.getElementById('sprint-type'),
    motion: document.getElementById('sprint-motion'),
    layout: document.getElementById('sprint-layout'),
    interior: document.getElementById('sprint-interior'),
    risk: document.getElementById('sprint-risk'),
    stage: document.getElementById('sprint-stage'),
    stageLabel: document.getElementById('sprint-stage-label'),
    stageCopy: document.getElementById('sprint-stage-copy'),
    zoneNote: document.getElementById('sprint-zone-note'),
    intensity: document.getElementById('sprint-intensity'),
    intensityValue: document.getElementById('sprint-intensity-value'),
    openness: document.getElementById('sprint-openness'),
    opennessValue: document.getElementById('sprint-openness-value'),
    metricConsistency: document.getElementById('sprint-metric-consistency'),
    metricSensory: document.getElementById('sprint-metric-sensory'),
    metricOperational: document.getElementById('sprint-metric-operational'),
    metricRisk: document.getElementById('sprint-metric-risk'),
    materialList: document.getElementById('sprint-material-list'),
    lightGrid: document.getElementById('sprint-light-grid'),
    flowList: document.getElementById('sprint-flow-list')
  };

  var conceptButtons = Array.prototype.slice.call(document.querySelectorAll('[data-sprint-concept]'));
  var zoneButtons = Array.prototype.slice.call(document.querySelectorAll('.sprint-zone[data-zone]'));

  var activeConcept = 'a';
  var activeZone = 'entry';

  function setText(node, value) {
    if (!node) return;
    node.textContent = String(value);
  }

  function emptyNode(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function renderMaterials(materials) {
    if (!ids.materialList) return;
    emptyNode(ids.materialList);

    materials.forEach(function (item) {
      var li = document.createElement('li');
      li.className = 'sprint-material-item';

      var swatch = document.createElement('span');
      swatch.className = 'sprint-material-item__swatch';
      swatch.style.backgroundColor = item.tone;

      var name = document.createElement('span');
      name.className = 'sprint-material-item__name';
      name.textContent = item.name;

      var role = document.createElement('span');
      role.className = 'sprint-material-item__role';
      role.textContent = item.role;

      li.appendChild(swatch);
      li.appendChild(name);
      li.appendChild(role);
      ids.materialList.appendChild(li);
    });
  }

  function renderLights(lights) {
    if (!ids.lightGrid) return;
    emptyNode(ids.lightGrid);

    lights.forEach(function (value, index) {
      var bar = document.createElement('span');
      bar.className = 'sprint-light-grid__bar';
      bar.style.setProperty('--light-height', String(value));
      bar.style.setProperty('--light-order', String(index + 1));
      bar.setAttribute('aria-hidden', 'true');
      ids.lightGrid.appendChild(bar);
    });
  }

  function renderFlow(flow) {
    if (!ids.flowList) return;
    emptyNode(ids.flowList);

    flow.forEach(function (line) {
      var li = document.createElement('li');
      li.textContent = line;
      ids.flowList.appendChild(li);
    });
  }

  function renderZones(cfg) {
    zoneButtons.forEach(function (btn, index) {
      var zoneKey = btn.getAttribute('data-zone');
      var zone = cfg.zones[zoneKey];
      if (!zone) return;

      var nameNode = btn.querySelector('.sprint-zone__name');
      var metaNode = btn.querySelector('.sprint-zone__meta');
      if (nameNode) nameNode.textContent = zone.name;
      if (metaNode) metaNode.textContent = zone.meta;

      btn.style.setProperty('--zone-order', String(index + 1));
    });
  }

  function syncIntensity() {
    if (!ids.intensity || !ids.intensityValue || !ids.stage) return;
    var value = Number(ids.intensity.value || 0);
    ids.intensityValue.textContent = String(value);
    ids.stage.style.setProperty('--sprint-intensity', (value / 100).toFixed(2));
  }

  function syncOpenness() {
    if (!ids.openness || !ids.opennessValue || !ids.stage) return;
    var value = Number(ids.openness.value || 0);
    ids.opennessValue.textContent = String(value);
    ids.stage.style.setProperty('--sprint-openness', (value / 100).toFixed(2));
  }

  function applyZone(zoneKey) {
    var cfg = configs[activeConcept];
    if (!cfg) return;

    if (!cfg.zones[zoneKey]) {
      zoneKey = 'entry';
    }
    activeZone = zoneKey;

    var zoneIndex = 0;
    zoneButtons.forEach(function (btn, index) {
      var isActive = btn.getAttribute('data-zone') === zoneKey;
      btn.classList.toggle('is-active', isActive);
      if (isActive) zoneIndex = index;
    });

    if (ids.stage) {
      ids.stage.style.setProperty('--sprint-zone-index', String(zoneIndex));
    }

    setText(ids.zoneNote, cfg.zones[zoneKey].note);
  }

  function applyMetrics(metrics) {
    setText(ids.metricConsistency, metrics.consistency);
    setText(ids.metricSensory, metrics.sensory);
    setText(ids.metricOperational, metrics.operational);
    setText(ids.metricRisk, metrics.risk);
  }

  function applyConcept(key) {
    var cfg = configs[key];
    if (!cfg) return;
    activeConcept = key;

    setText(ids.id, cfg.id);
    setText(ids.name, cfg.name);
    setText(ids.thesis, cfg.thesis);
    setText(ids.type, cfg.type);
    setText(ids.motion, cfg.motion);
    setText(ids.layout, cfg.layout);
    setText(ids.interior, cfg.interior);
    setText(ids.risk, cfg.risk);
    setText(ids.stageLabel, cfg.stageLabel);
    setText(ids.stageCopy, cfg.stageCopy);

    if (ids.stage) {
      ids.stage.classList.remove('is-concept-a', 'is-concept-b');
      ids.stage.classList.add(key === 'b' ? 'is-concept-b' : 'is-concept-a');
    }

    conceptButtons.forEach(function (btn) {
      var isActive = btn.getAttribute('data-sprint-concept') === key;
      btn.classList.toggle('is-active', isActive);
      btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    applyMetrics(cfg.metrics);
    renderMaterials(cfg.materials);
    renderLights(cfg.lights);
    renderFlow(cfg.flow);
    renderZones(cfg);

    if (ids.intensity) ids.intensity.value = String(cfg.defaultIntensity);
    if (ids.openness) ids.openness.value = String(cfg.defaultOpenness);

    syncIntensity();
    syncOpenness();
    applyZone(cfg.zones[activeZone] ? activeZone : 'entry');
  }

  conceptButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      applyConcept(btn.getAttribute('data-sprint-concept'));
    });
  });

  zoneButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      applyZone(btn.getAttribute('data-zone'));
    });
  });

  if (ids.intensity) {
    ids.intensity.addEventListener('input', syncIntensity);
  }

  if (ids.openness) {
    ids.openness.addEventListener('input', syncOpenness);
  }

  applyConcept('a');
})();
