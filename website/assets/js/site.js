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
    document.documentElement.className = cls;

    /* ─── Nav 토글 ─── */
    var toggle = document.getElementById('nav-toggle');
    var overlay = document.getElementById('nav-overlay');

    if (toggle && overlay) {
        toggle.addEventListener('click', function () {
            var isOpen = overlay.classList.contains('open');
            overlay.classList.toggle('open', !isOpen);
            toggle.setAttribute('aria-expanded', String(!isOpen));
            document.body.style.overflow = isOpen ? '' : 'hidden';
        });

        /* 오버레이 링크 클릭 시 닫기 */
        overlay.querySelectorAll('a').forEach(function (a) {
            a.addEventListener('click', function () {
                overlay.classList.remove('open');
                toggle.setAttribute('aria-expanded', 'false');
                document.body.style.overflow = '';
            });
        });

        /* ESC 닫기 */
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && overlay.classList.contains('open')) {
                overlay.classList.remove('open');
                toggle.setAttribute('aria-expanded', 'false');
                document.body.style.overflow = '';
                toggle.focus();
            }
        });
    }

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
        setTimeout(function() {
            deconTitle.style.transition = 'opacity 1s var(--ease)';
            deconTitle.style.opacity = '1';
        }, 100);
    }

    /* ─── Document Number Sequential Fade-in ─── */
    var numTags = document.querySelectorAll('.home-nav-item__num, .nav-overlay__num');
    numTags.forEach(function(tag, i) {
        tag.style.opacity = '0';
        tag.style.transition = 'opacity 0.6s var(--ease-out)';
        setTimeout(function() {
            tag.style.opacity = '';
        }, 800 + i * 120);
    });

    /* ─── Nav Overlay 툴팁 터치 호환 ─── */
    var overlayLinks = document.querySelectorAll('.nav-overlay a');
    overlayLinks.forEach(function(link) {
        link.addEventListener('touchstart', function() {
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
            } catch (err) {}
        });
    })();

})();
