/* =============================================
   WOOHWAHAE — Interactions
   ============================================= */

// ─── Service Worker Cleanup (즉시 실행) ───
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then(registrations => {
    registrations.forEach(r => r.unregister());
  });
}

document.addEventListener('DOMContentLoaded', () => {

  // ─── Logo Link Fix ───
  document.addEventListener('click', (e) => {
    const anchor = e.target.closest('a');
    if (anchor && anchor.classList.contains('nav-logo') && window.location.search) {
      e.preventDefault();
      const target = anchor.getAttribute('href');
      const sep = target.includes('?') ? '&' : '?';
      window.location.href = target + sep + window.location.search.substring(1);
    }
  });

  // ─── Fade-in on Scroll ───
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const delay = entry.target.dataset.delay || 0;
        setTimeout(() => entry.target.classList.add('visible'), delay * 80);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.05 });

  document.querySelectorAll('.fade-in, .fade-in-slow').forEach((el) => {
    if (!el.dataset.delay) {
      const siblings = el.parentElement?.querySelectorAll('.fade-in, .fade-in-slow');
      if (siblings) el.dataset.delay = Array.from(siblings).indexOf(el);
    }
    observer.observe(el);
  });

  // 로드 직후 뷰포트 내 요소 즉시 처리
  requestAnimationFrame(() => {
    document.querySelectorAll('.fade-in, .fade-in-slow').forEach((el) => {
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight && rect.bottom > 0) {
        const delay = el.dataset.delay || 0;
        setTimeout(() => el.classList.add('visible'), delay * 80);
      }
    });
  });

  // ─── Nav Active State ───
  const currentPath = window.location.pathname;
  document.querySelectorAll('.nav-links a').forEach(link => {
    const href = link.getAttribute('href');
    if (href === currentPath ||
      (href !== '/' && currentPath.startsWith(href.replace('.html', '')))) {
      link.classList.add('active');
    }
  });

  // ─── Mobile Nav Toggle ───
  const toggle = document.querySelector('.nav-toggle');
  const navLinks = document.querySelector('.nav-links');

  if (toggle && navLinks) {
    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      toggle.classList.toggle('active');
      navLinks.classList.toggle('open');
      document.body.classList.toggle('nav-open');
    });

    navLinks.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        toggle.classList.remove('active');
        navLinks.classList.remove('open');
        document.body.classList.remove('nav-open');
      });
    });

    // 외부 클릭 시 닫기
    document.addEventListener('click', (e) => {
      if (navLinks.classList.contains('open') &&
          !navLinks.contains(e.target) &&
          !toggle.contains(e.target)) {
        toggle.classList.remove('active');
        navLinks.classList.remove('open');
        document.body.classList.remove('nav-open');
      }
    });

    document.addEventListener('touchstart', (e) => {
      if (navLinks.classList.contains('open') &&
          !navLinks.contains(e.target) &&
          !toggle.contains(e.target)) {
        toggle.classList.remove('active');
        navLinks.classList.remove('open');
        document.body.classList.remove('nav-open');
      }
    }, { passive: true });
  }

  // ─── Nav Scroll Blend ───
  const navbar = document.querySelector('nav');
  if (navbar) {
    const THRESHOLD = 40;
    let ticking = false;

    function updateNav() {
      navbar.classList.toggle('scrolled', window.scrollY > THRESHOLD);
      ticking = false;
    }

    window.addEventListener('scroll', () => {
      if (!ticking) {
        requestAnimationFrame(updateNav);
        ticking = true;
      }
    }, { passive: true });
  }

  // ─── Scroll Progress (fallback) ───
  const scrollFill = document.getElementById('scroll-fill');
  if (scrollFill && !CSS.supports('animation-timeline', 'scroll()')) {
    window.addEventListener('scroll', () => {
      const total = document.documentElement.scrollHeight - window.innerHeight;
      scrollFill.style.height = total > 0 ? (window.scrollY / total * 100) + '%' : '0%';
    }, { passive: true });
  }

  // ─── Language Toggle ───
  const langToggle = document.getElementById('lang-toggle');

  function updateLanguage() {
    const lang = localStorage.getItem('woohwahae-lang') || 'ko';

    document.querySelectorAll('[data-lang-' + lang + ']').forEach(el => {
      const text = el.getAttribute('data-lang-' + lang);
      if (text) el.innerHTML = text;
    });

    document.querySelectorAll('[data-placeholder-' + lang + ']').forEach(el => {
      const ph = el.getAttribute('data-placeholder-' + lang);
      if (ph) el.placeholder = ph;
    });

    if (langToggle) langToggle.innerText = lang === 'ko' ? 'EN' : 'KR';
    document.documentElement.lang = lang;
  }

  updateLanguage();

  if (langToggle) {
    langToggle.addEventListener('click', () => {
      const current = localStorage.getItem('woohwahae-lang') || 'ko';
      localStorage.setItem('woohwahae-lang', current === 'ko' ? 'en' : 'ko');
      updateLanguage();
    });
  }

});

/* ─── Section Subnav 주입 (에세이/아티클 페이지) ─── */
(function () {
  var siteNav = document.getElementById('site-nav');
  if (!siteNav) return;

  var path = window.location.pathname;
  if (path === '/' || path === '/index.html') return;

  var active = '';
  if (path.indexOf('/archive') === 0 || path.indexOf('/essay-') !== -1 || path.indexOf('/journal-') !== -1 || path.indexOf('/lookbook') !== -1) active = 'archive';
  else if (path.indexOf('/practice') === 0) active = 'practice';
  else if (path.indexOf('/about') === 0) active = 'about';
  else if (path.indexOf('/lab') === 0) active = 'lab';

  var sections = [
    { key: 'archive', label: 'Archive', href: '/archive/' },
    { key: 'practice', label: 'Practice', href: '/practice/' },
    { key: 'about', label: 'About', href: '/about/' },
    { key: 'lab', label: 'Lab', href: '/lab/' }
  ];

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

/* time-aware class: index.html inline script으로 이전 */
