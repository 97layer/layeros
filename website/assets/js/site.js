/*!
 * WOOHWAHAE — site.js
 * Nav 토글 · Scroll reveal · Breath 시간대 변조
 */

(function () {
  'use strict';

  /* ─── Breath 시간대 변조 ─── */
  var h = new Date().getHours();
  var cls = h < 6 ? 'time-dawn'
    : h < 18 ? 'time-day'
      : h < 22 ? 'time-evening'
        : 'time-night';
  document.documentElement.classList.remove('time-dawn', 'time-day', 'time-evening', 'time-night');
  document.documentElement.classList.add(cls);

  /* ─── Nav 토글 ─── */
  var toggle = document.getElementById('nav-toggle');
  var overlay = document.getElementById('nav-overlay');

  if (toggle && overlay) {
    function setNavOpen(nextOpen) {
      overlay.classList.toggle('open', nextOpen);
      overlay.setAttribute('aria-hidden', String(!nextOpen));
      toggle.setAttribute('aria-expanded', String(nextOpen));
      document.body.classList.toggle('nav-open', nextOpen);
    }

    function closeNav() {
      setNavOpen(false);
    }

    /* dim backdrop — 드롭다운 바깥 클릭 시 닫기 */
    var dim = document.createElement('div');
    dim.className = 'nav-dim';
    document.body.appendChild(dim);
    dim.addEventListener('click', closeNav);

    setNavOpen(false);

    toggle.addEventListener('click', function () {
      setNavOpen(!overlay.classList.contains('open'));
    });

    /* 오버레이 링크 클릭 시 닫기 */
    overlay.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () {
        closeNav();
      });
    });

    /* 오버레이 배경 클릭 시 닫기 */
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeNav();
    });

    /* ESC 닫기 */
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && overlay.classList.contains('open')) {
        closeNav();
        toggle.focus();
      }
    });

    /* 데스크톱 전환 시 열린 오버레이 정리 */
    window.addEventListener('resize', function () {
      if (window.innerWidth > 768 && overlay.classList.contains('open')) {
        closeNav();
      }
    }, { passive: true });

    /* ── 브래킷 초기 노이즈 사이클 ──
       페이지 로드 후 「 」가 노이즈 기호 2회 교체 후 확정 */
    (function () {
      var NOISE_B = ['·', '—', '|', ':', '_'];
      var cycles = 2;
      var count = 0;
      function rn() { return NOISE_B[Math.floor(Math.random() * NOISE_B.length)]; }

      toggle.style.setProperty('--bracket-content', '"[' + rn() + ']"');
      var t = setInterval(function () {
        count++;
        if (count < cycles) {
          /* CSS ::before content는 직접 못 바꾸므로 data-attr 활용 불가.
             대신 toggle에 data-noise 클래스로 임시 문자 표시 */
          toggle.dataset.noise = rn();
          toggle.classList.add('nav-toggle--noise');
        } else {
          clearInterval(t);
          toggle.classList.remove('nav-toggle--noise');
          delete toggle.dataset.noise;
        }
      }, 90);
    })();
  }

  /* ─── Nav Overlay Google OAuth ─── */
  (function () {
    var overlayRoot = document.getElementById('nav-overlay');
    if (!overlayRoot) return;

    var authPanel = document.createElement('section');
    authPanel.className = 'nav-overlay__auth';
    authPanel.innerHTML = [
      '<p class="nav-overlay__auth-label">Login</p>',
      '<p class="nav-overlay__auth-status" id="nav-auth-status">인증 상태를 확인합니다.</p>',
      '<div class="nav-overlay__auth-google" id="nav-google-button"></div>',
      '<button type="button" class="nav-overlay__auth-btn" id="nav-auth-logout" hidden>Logout</button>'
    ].join('');
    overlayRoot.appendChild(authPanel);

    var statusEl = document.getElementById('nav-auth-status');
    var googleButtonHost = document.getElementById('nav-google-button');
    var logoutBtn = document.getElementById('nav-auth-logout');
    if (!statusEl || !googleButtonHost || !logoutBtn) return;

    var STORAGE_KEY = 'wwh_user_token';
    var currentToken = '';
    var googleConfig = null;
    var googleScriptPromise = null;
    var AUTH_API_BASE = /^(localhost|127\.0\.0\.1)$/.test(window.location.hostname)
      ? 'http://localhost:8082'
      : 'https://api.woohwahae.kr';

    function authApiUrl(path) {
      var safePath = String(path || '').replace(/^\/+/, '');
      return AUTH_API_BASE + '/api/auth/' + safePath;
    }

    function setStatus(message, isError) {
      statusEl.textContent = message;
      statusEl.classList.toggle('is-error', !!isError);
    }

    function storeToken(token) {
      currentToken = token || '';
      try {
        if (currentToken) {
          localStorage.setItem(STORAGE_KEY, currentToken);
        } else {
          localStorage.removeItem(STORAGE_KEY);
        }
      } catch (err) {
      }
    }

    function getStoredToken() {
      try {
        return localStorage.getItem(STORAGE_KEY) || '';
      } catch (err) {
        return '';
      }
    }

    function authHeaders(extra) {
      var headers = {};
      if (extra && typeof extra === 'object') {
        Object.keys(extra).forEach(function (key) {
          headers[key] = extra[key];
        });
      }
      if (currentToken) {
        headers.Authorization = 'Bearer ' + currentToken;
      }
      return headers;
    }

    function resetGoogleButton() {
      googleButtonHost.innerHTML = '';
      if (!googleConfig || !googleConfig.enabled) return;
      ensureGoogleScriptLoaded()
        .then(function () {
          if (!(window.google && window.google.accounts && window.google.accounts.id)) {
            throw new Error('google_identity_missing');
          }
          window.google.accounts.id.initialize({
            client_id: googleConfig.client_id,
            callback: onGoogleCredential
          });
          window.google.accounts.id.renderButton(googleButtonHost, {
            type: 'standard',
            theme: 'outline',
            size: 'large',
            text: 'signin_with',
            width: 240,
            shape: 'rectangular',
            logo_alignment: 'left'
          });
          setStatus('Google 계정으로 로그인합니다.', false);
        })
        .catch(function () {
          googleButtonHost.innerHTML = '<span class="nav-overlay__auth-placeholder">Google Script Unavailable</span>';
          setStatus('Google 스크립트를 불러오지 못했습니다.', true);
        });
    }

    function ensureGoogleScriptLoaded() {
      if (window.google && window.google.accounts && window.google.accounts.id) {
        return Promise.resolve();
      }
      if (googleScriptPromise) {
        return googleScriptPromise;
      }
      googleScriptPromise = new Promise(function (resolve, reject) {
        var existing = document.querySelector('script[data-google-identity="true"]');
        if (existing) {
          existing.addEventListener('load', function () { resolve(); }, { once: true });
          existing.addEventListener('error', function () { reject(new Error('google_script_load_failed')); }, { once: true });
          return;
        }

        var script = document.createElement('script');
        script.src = 'https://accounts.google.com/gsi/client';
        script.async = true;
        script.defer = true;
        script.setAttribute('data-google-identity', 'true');
        script.onload = function () { resolve(); };
        script.onerror = function () { reject(new Error('google_script_load_failed')); };
        document.head.appendChild(script);
      });
      return googleScriptPromise;
    }

    function showAuthenticated(user) {
      var name = (user && user.name ? user.name : '') || (user && user.email ? user.email : '');
      setStatus(name ? (name + ' 로그인됨') : '로그인되었습니다.', false);
      googleButtonHost.innerHTML = '';
      logoutBtn.hidden = false;
    }

    function handleLoginFailure(err) {
      var message = '로그인에 실패했습니다. 다시 시도해 주세요.';
      if (err && /login_failed_429/.test(err.message)) {
        message = '로그인 요청이 많습니다. 잠시 후 다시 시도해 주세요.';
      } else if (err && /login_failed_404/.test(err.message)) {
        message = '인증 API가 아직 배포되지 않았습니다.';
      } else if (err && /login_failed_503/.test(err.message)) {
        message = 'Google 로그인이 아직 설정되지 않았습니다.';
      } else if (err && /login_failed_401/.test(err.message)) {
        message = 'Google 인증 정보가 유효하지 않습니다.';
      }
      setStatus(message, true);
      storeToken('');
      resetGoogleButton();
    }

    function onGoogleCredential(response) {
      if (!(response && response.credential)) {
        setStatus('Google 인증 토큰을 받지 못했습니다.', true);
        return;
      }

      setStatus('로그인을 처리하고 있습니다.', false);
      fetch(authApiUrl('google/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: response.credential })
      })
        .then(function (res) {
          if (!res.ok) {
            throw new Error('login_failed_' + res.status);
          }
          return res.json();
        })
        .then(function (data) {
          if (!(data && data.token && data.user)) {
            throw new Error('login_invalid_payload');
          }
          storeToken(data.token);
          showAuthenticated(data.user);
        })
        .catch(handleLoginFailure);
    }

    function fetchGoogleConfig() {
      return fetch(authApiUrl('google/config'), { cache: 'no-store' })
        .then(function (res) {
          if (!res.ok) {
            throw new Error('google_config_failed_' + res.status);
          }
          return res.json();
        });
    }

    function restoreSession() {
      currentToken = getStoredToken();
      if (!currentToken) return Promise.resolve(null);

      return fetch(authApiUrl('me'), {
        method: 'GET',
        headers: authHeaders(),
        cache: 'no-store'
      })
        .then(function (res) {
          if (!res.ok) {
            throw new Error('auth_me_failed');
          }
          return res.json();
        })
        .then(function (payload) {
          if (payload && payload.authenticated && payload.user) {
            return payload.user;
          }
          storeToken('');
          return null;
        })
        .catch(function () {
          storeToken('');
          return null;
        });
    }

    logoutBtn.addEventListener('click', function () {
      setStatus('로그아웃하고 있습니다.', false);
      fetch(authApiUrl('logout'), {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' })
      })
        .catch(function () { })
        .finally(function () {
          storeToken('');
          logoutBtn.hidden = true;
          if (googleConfig && googleConfig.enabled) {
            resetGoogleButton();
          } else {
            googleButtonHost.innerHTML = '<span class="nav-overlay__auth-placeholder">Google Login Disabled</span>';
            setStatus('Google 로그인이 비활성화되어 있습니다.', true);
          }
        });
    });

    fetchGoogleConfig()
      .then(function (config) {
        googleConfig = config || {};
        return restoreSession();
      })
      .then(function (user) {
        if (user) {
          showAuthenticated(user);
          return;
        }

        logoutBtn.hidden = true;
        if (googleConfig && googleConfig.enabled) {
          resetGoogleButton();
        } else {
          googleButtonHost.innerHTML = '<span class="nav-overlay__auth-placeholder">Google Login Disabled</span>';
          setStatus('Google 로그인이 비활성화되어 있습니다.', true);
        }
      })
      .catch(function (err) {
        googleButtonHost.innerHTML = '<span class="nav-overlay__auth-placeholder">Auth Init Failed</span>';
        if (err && /google_config_failed_404/.test(err.message)) {
          setStatus('인증 API가 아직 배포되지 않았습니다. (/api/auth/google/config 404)', true);
          return;
        }
        setStatus('인증 API 경로를 확인해 주세요. (google/config 응답 없음)', true);
      });
  })();

  /* ─── Scroll Reveal ─── */
  var revealEls = document.querySelectorAll('[data-reveal]');
  if (revealEls.length && 'IntersectionObserver' in window) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -32px 0px' });

    revealEls.forEach(function (el, i) {
      /* stagger: 문서 넘기는 느낌 — 80ms 간격 */
      if (el.classList.contains('archive-card') ||
        el.classList.contains('practice-card') ||
        el.classList.contains('ws-item') ||
        el.classList.contains('archive-list-item') ||
        el.classList.contains('home-nav-item')) {
        el.style.transitionDelay = (i % 9 * 0.08) + 's';
      }
      observer.observe(el);
    });
  } else {
    /* IO 미지원 fallback */
    revealEls.forEach(function (el) { el.classList.add('is-visible'); });
  }

  /* ─── 내비게이션 숫자 태그 인터랙션 ─── */
  document.querySelectorAll('.nav-links a, .nav-overlay a').forEach(function (a) {
    var tag = a.querySelector('.numeric-tag');
    if (tag) {
      a.addEventListener('mouseenter', function () { tag.classList.add('numeric-tag--active'); });
      a.addEventListener('mouseleave', function () {
        if (!a.classList.contains('active')) {
          tag.classList.remove('numeric-tag--active');
        }
      });
    }
  });

  /* ─── Deconstructed Title Shuffle ─── */
  var deconTitle = document.querySelector('.decon-title');
  if (deconTitle) {
    setTimeout(function () {
      deconTitle.style.transition = 'opacity 1s var(--ease)';
      deconTitle.style.opacity = '1';
    }, 100);
  }

  /* ─── Document Number Sequential Fade-in ─── */
  var numTags = document.querySelectorAll('.home-nav-item__num, .nav-overlay__num');
  numTags.forEach(function (tag, i) {
    tag.style.opacity = '0';
    tag.style.transition = 'opacity 0.6s var(--ease-out)';
    setTimeout(function () {
      tag.style.opacity = '';
    }, 800 + i * 120);
  });

  /* ─── Section Subnav 주입 ─── */
  (function () {
    var siteNav = document.getElementById('site-nav');
    if (!siteNav) return;
    if (document.querySelector('.site-subnav')) return;

    var path = window.location.pathname;
    /* 홈(/)에서는 숨김 */
    if (path === '/' || path === '/index.html') return;

    var active = '';
    if (path.indexOf('/archive') === 0 || path.indexOf('/essay-') !== -1 || path.indexOf('/journal-') !== -1 || path.indexOf('/lookbook') !== -1 || path.indexOf('/playlist') !== -1) active = 'archive';
    else if (path.indexOf('/practice') === 0) active = 'practice';
    else if (path.indexOf('/about') === 0) active = 'about';
    else if (path.indexOf('/lab') === 0) active = 'lab';
    if (active === 'lab') return;

    var sections = [
      { key: 'archive', label: 'Archive', href: '/archive/' },
      { key: 'practice', label: 'Practice', href: '/practice/' },
      { key: 'about', label: 'About', href: '/about/' }
    ];

    /* 상단 탭 active 통일: 현재 경로에 맞춰 nav/overlay 모두 강조 */
    document.querySelectorAll('.nav-links a, .nav-overlay a').forEach(function (a) {
      var href = a.getAttribute('href') || '';
      var isActive = href !== '/' && path.indexOf(href) === 0;
      a.classList.toggle('active', isActive);
      var num = a.querySelector('.numeric-tag, .nav-overlay__num');
      if (num) num.classList.toggle('numeric-tag--active', isActive);
    });

    var subnav = document.createElement('div');
    subnav.className = 'site-subnav';
    subnav.setAttribute('role', 'navigation');
    subnav.setAttribute('aria-label', 'Section navigation');
    subnav.innerHTML = sections.map(function (s) {
      return '<a href="' + s.href + '" class="site-subnav__link' + (s.key === active ? ' is-active' : '') + '">' + s.label + '</a>';
    }).join('');

    document.body.appendChild(subnav);
    document.body.classList.add('has-subnav');
  })();

  /* ─── Nav Overlay 툴팁 터치 호환 ─── */
  var overlayLinks = document.querySelectorAll('.nav-overlay a');
  overlayLinks.forEach(function (link) {
    link.addEventListener('touchstart', function () {
      var tip = link.querySelector('.nav-overlay__tip');
      if (tip) {
        tip.style.opacity = '0.7';
        tip.style.transform = 'translateY(0)';
      }
    }, { passive: true });
  });

  /* ─── Preamble Typewriter (모든 페이지 공통) ─── */
  (function () {
    var el = document.querySelector('.about-preamble');
    if (!el) return;
    var phrase = el.textContent.trim();
    if (!phrase) return;
    var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var key = 'typed_' + location.pathname;
    el.textContent = '';
    if (reduced || sessionStorage.getItem(key)) {
      el.textContent = phrase;
      return;
    }
    sessionStorage.setItem(key, '1');
    var i = 0;
    var timer = setInterval(function () {
      el.textContent = phrase.slice(0, ++i);
      if (i >= phrase.length) clearInterval(timer);
    }, 65);
  })();

  /* ─── View Transitions: 방향 감지 ─── */
  (function () {
    var NAV_ORDER = ['/', '/archive/', '/practice/', '/about/', '/lab/'];
    function navIdx(path) {
      for (var i = 0; i < NAV_ORDER.length; i++) {
        var p = NAV_ORDER[i];
        if (p === '/' ? path === p : path.indexOf(p) === 0) return i;
      }
      return 0;
    }
    /* 이전 클릭에서 저장한 방향 복원 */
    var dir = sessionStorage.getItem('vt_dir') || 'forward';
    sessionStorage.removeItem('vt_dir');
    document.documentElement.setAttribute('data-nav-dir', dir);

    /* 링크 클릭 시 방향 저장 */
    document.addEventListener('click', function (e) {
      var a = e.target.closest('a[href]');
      if (!a) return;
      var href = a.getAttribute('href');
      if (!href || /^(https?:|mailto:|tel:|#)/.test(href)) return;
      try {
        var url = new URL(href, window.location.href);
        if (url.origin !== window.location.origin) return;
        var from = navIdx(window.location.pathname);
        var to = navIdx(url.pathname);
        sessionStorage.setItem('vt_dir', to < from ? 'back' : 'forward');
      } catch (err) { }
    });
  })();

  /* ─── About 부록 아코디언 ─── */
  (function () {
    var toggles = document.querySelectorAll('.about-appendix__toggle[data-accordion]');
    if (!toggles.length) return;
    toggles.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var targetId = btn.getAttribute('data-accordion');
        var body = document.getElementById(targetId);
        if (!body) return;
        var isOpen = body.classList.contains('is-open');
        body.classList.toggle('is-open', !isOpen);
        btn.setAttribute('aria-expanded', String(!isOpen));
        var indicator = btn.querySelector('span');
        if (indicator) indicator.textContent = isOpen ? '+' : '−';
      });
    });
  })();

  /* ─── 읽기 진행 바 (에세이 전용) ─── */
  (function () {
    if (!document.body.classList.contains('page-essay')) return;
    var bar = document.getElementById('read-progress');
    if (!bar) return;
    var ticking = false;
    function update() {
      var docH = document.documentElement.scrollHeight - document.documentElement.clientHeight;
      var progress = docH > 0 ? Math.min(1, window.pageYOffset / docH) : 0;
      bar.style.transform = 'scaleX(' + progress + ')';
      ticking = false;
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { requestAnimationFrame(update); ticking = true; }
    }, { passive: true });
    /* ─── Admin Portal Easter Egg ─── */
    (function () {
      var footerBrand = document.querySelector('.footer-brand-name');
      if (!footerBrand) return;

      var clicks = 0;
      var timer = null;

      footerBrand.addEventListener('click', function (e) {
        // a 태그일 경우 기본 이동 방지 (필요 시)
        // e.preventDefault(); 

        clicks++;
        if (timer) clearTimeout(timer);

        if (clicks >= 5) {
          clicks = 0;
          window.location.href = '/admin/';
          return;
        }

        timer = setTimeout(function () {
          clicks = 0;
        }, 5000);
      });
    })();

  })();

  /* ─── Pull-to-Refresh (모바일) ─── */
  (function () {
    if (typeof window === 'undefined') return;
    /* 터치 디바이스만 */
    if (!('ontouchstart' in window)) return;

    var PTR_THRESHOLD = 72; /* px — 이 이상 당겨야 새로고침 */
    var PTR_MAX = 110;      /* 최대 당김 거리 */

    /* 인디케이터 엘리먼트 생성 */
    var indicator = document.createElement('div');
    indicator.id = 'ptr-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    indicator.innerHTML = '<span class="ptr-icon"></span>';
    document.body.appendChild(indicator);

    /* 인라인 스타일 — 외부 CSS 의존 없이 */
    var style = document.createElement('style');
    style.textContent = [
      '#ptr-indicator{',
      'position:fixed;top:0;left:0;right:0;',
      'display:flex;align-items:center;justify-content:center;',
      'height:56px;z-index:9999;pointer-events:none;',
      'transform:translateY(-100%);',
      'transition:none;',
      '}',
      '.ptr-icon{',
      'width:20px;height:20px;border-radius:50%;',
      'border:1.5px solid rgba(20,20,18,0.25);',
      'border-top-color:rgba(20,20,18,0.7);',
      'opacity:0;transition:opacity 0.15s;',
      '}',
      '#ptr-indicator.ptr-pulling .ptr-icon{opacity:1;}',
      '#ptr-indicator.ptr-loading .ptr-icon{',
      'opacity:1;animation:ptr-spin 0.7s linear infinite;',
      '}',
      '@keyframes ptr-spin{to{transform:rotate(360deg)}}',
    ].join('');
    document.head.appendChild(style);

    var icon = indicator.querySelector('.ptr-icon');
    var startY = 0;
    var currentY = 0;
    var isPulling = false;
    var isLoading = false;

    function canPull() {
      /* 최상단 스크롤 위치일 때만 */
      return window.pageYOffset <= 0;
    }

    document.addEventListener('touchstart', function (e) {
      if (isLoading) return;
      if (!canPull()) return;
      startY = e.touches[0].clientY;
      isPulling = true;
    }, { passive: true });

    document.addEventListener('touchmove', function (e) {
      if (!isPulling || isLoading) return;
      currentY = e.touches[0].clientY;
      var dist = Math.min(currentY - startY, PTR_MAX);
      if (dist <= 0) { reset(); return; }

      var progress = Math.min(dist / PTR_THRESHOLD, 1);
      var translateY = dist * 0.45; /* 저항감 */
      indicator.style.transform = 'translateY(calc(-100% + ' + translateY + 'px))';
      indicator.classList.add('ptr-pulling');
      /* 회전 각도로 진행도 표현 */
      icon.style.transform = 'rotate(' + (progress * 360) + 'deg)';
      icon.style.borderTopColor = progress >= 1
        ? 'rgba(20,20,18,0.9)'
        : 'rgba(20,20,18,0.7)';
    }, { passive: true });

    document.addEventListener('touchend', function () {
      if (!isPulling || isLoading) return;
      var dist = currentY - startY;
      if (dist >= PTR_THRESHOLD) {
        triggerRefresh();
      } else {
        reset();
      }
      isPulling = false;
    }, { passive: true });

    function triggerRefresh() {
      isLoading = true;
      indicator.classList.remove('ptr-pulling');
      indicator.classList.add('ptr-loading');
      indicator.style.transform = 'translateY(0)';
      icon.style.transform = '';
      setTimeout(function () {
        window.location.reload();
      }, 600);
    }

    function reset() {
      isPulling = false;
      indicator.classList.remove('ptr-pulling');
      indicator.style.transform = 'translateY(-100%)';
    }
  })();

  /* ─── Home Dev Log 위젯 ─── */
  (function () {
    if (!document.body.classList.contains('page-home')) return;
    var container = document.getElementById('home-devlog-entries');
    if (!container) return;

    var TYPE_MAP = {
      'feat:': '+ FEAT',
      'fix:': '~ FIX',
      'style:': '* STYLE',
      'refactor:': '> REFACTOR',
      'docs:': '- DOCS',
      'chore:': '. CHORE'
    };

    function typeLabel(msg) {
      var lower = (msg || '').toLowerCase();
      for (var k in TYPE_MAP) {
        if (lower.startsWith(k)) return TYPE_MAP[k];
      }
      return '· UPD';
    }

    function fmtDate(str) {
      var d = new Date(str);
      var mm = String(d.getMonth() + 1).padStart(2, '0');
      var dd = String(d.getDate()).padStart(2, '0');
      return mm + '.' + dd;
    }

    fetch('/lab/changelog/data.json?t=' + Date.now())
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var entries = (data.entries || []).slice(0, 6);
        if (!entries.length) { container.innerHTML = ''; return; }
        container.innerHTML = entries.map(function (e) {
          return '<div class="hdl-entry">' +
            '<span class="hdl-meta">[' + fmtDate(e.date) + '] ' + typeLabel(e.rawMsg || e.msg) + '</span>' +
            '<span class="hdl-msg">' + (e.msg || '') + '</span>' +
            '</div>';
        }).join('');
      })
      .catch(function () { container.innerHTML = ''; });
  })();

  /* ─── Practice Release Gate ─── */
  (function () {
    var isPractice = document.body.classList.contains('page-practice') ||
      document.body.classList.contains('page-practice-sub');
    if (!isPractice) return;

    var fallback = {
      homepage: { live: true },
      practice: {
        atelier: { live: false },
        direction: { live: true },
        project: { live: true },
        product: { live: false }
      }
    };

    function normalizeState(raw) {
      var state = JSON.parse(JSON.stringify(fallback));
      if (!raw || typeof raw !== 'object') return state;
      if (raw.homepage && typeof raw.homepage === 'object' && typeof raw.homepage.live === 'boolean') {
        state.homepage.live = raw.homepage.live;
      }
      if (raw.practice && typeof raw.practice === 'object') {
        Object.keys(state.practice).forEach(function (key) {
          var item = raw.practice[key];
          if (item && typeof item === 'object' && typeof item.live === 'boolean') {
            state.practice[key].live = item.live;
          }
        });
      }
      return state;
    }

    function isLive(state, key) {
      return !!(state.practice[key] && state.practice[key].live);
    }

    function applyStatus(state) {
      document.querySelectorAll('[data-release-status]').forEach(function (el) {
        var key = el.getAttribute('data-release-status');
        var live = isLive(state, key);
        el.textContent = live ? 'LIVE' : 'HOLD';
        el.classList.toggle('is-live', live);
        el.classList.toggle('is-hold', !live);
      });
    }

    function applyActionState(el, live) {
      var liveHref = el.getAttribute('data-release-live-href') || '';
      var holdHref = el.getAttribute('data-release-hold-href') || '/practice/';
      var liveLabel = el.getAttribute('data-release-live-label') || '';
      var holdLabel = el.getAttribute('data-release-hold-label') || '준비 중';

      if (live) {
        if (liveHref) el.setAttribute('href', liveHref);
        if (liveLabel) el.textContent = liveLabel;
        el.removeAttribute('aria-disabled');
        el.classList.remove('release-action--hold');
        if (/^https?:\/\//.test(liveHref)) {
          el.setAttribute('target', '_blank');
          el.setAttribute('rel', 'noopener');
        }
        return;
      }

      el.setAttribute('href', holdHref);
      if (holdLabel) el.textContent = holdLabel;
      el.setAttribute('aria-disabled', 'true');
      el.classList.add('release-action--hold');
      el.removeAttribute('target');
      el.removeAttribute('rel');
    }

    function applyLinks(state) {
      document.querySelectorAll('[data-release-link], [data-release-action]').forEach(function (el) {
        var key = el.getAttribute('data-release-link') || el.getAttribute('data-release-action');
        if (!key) return;
        applyActionState(el, isLive(state, key));
      });
    }

    function applyBanners(state) {
      document.querySelectorAll('[data-release-banner]').forEach(function (el) {
        var key = el.getAttribute('data-release-banner');
        var live = isLive(state, key);
        var liveCopy = el.getAttribute('data-release-live-copy');
        var holdCopy = el.getAttribute('data-release-hold-copy');
        if (live && liveCopy) el.textContent = liveCopy;
        if (!live && holdCopy) el.textContent = holdCopy;
        el.classList.toggle('is-live', live);
        el.classList.toggle('release-banner--hold', !live);
      });
    }

    function applyState(raw) {
      var state = normalizeState(raw);
      applyStatus(state);
      applyLinks(state);
      applyBanners(state);
    }

    fetch('/practice/release-state.json?t=' + Date.now(), { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) throw new Error('release-state fetch failed');
        return res.json();
      })
      .then(applyState)
      .catch(function () {
        applyState(fallback);
      });
  })();

  /* ─── Footer Live Time (KST) ─── */
  (function () {
    var timeEl = document.getElementById('footer-time');
    if (!timeEl) return;

    function updateTime() {
      var d = new Date();
      var h = d.getHours();
      var m = d.getMinutes();
      var s = d.getSeconds();

      var hh = h < 10 ? '0' + h : h;
      var mm = m < 10 ? '0' + m : m;
      var ss = s < 10 ? '0' + s : s;

      /* 울산 방구정 20길 인근 근사 좌표 + 24시 형식 초단위 표시 (밀도 높은 좌표계 연출) */
      timeEl.textContent = ' ⸰ 35.556° N, 129.332° E · ' + hh + ':' + mm + ':' + ss;
    }

    updateTime();
    setInterval(updateTime, 1000);
  })();
})();
