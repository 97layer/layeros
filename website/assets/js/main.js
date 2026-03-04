/* =============================================
   WOOHWAHAE — main.js (legacy-compatible minimal layer)
   Shared behavior lives in assets/js/site.js.
   ============================================= */

(function () {
  'use strict';

  // Remove stale service workers from previous prototypes.
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations().then(function (registrations) {
      registrations.forEach(function (registration) { registration.unregister(); });
    }).catch(function () {});
  }

  document.addEventListener('DOMContentLoaded', function () {
    // Keep query params when clicking legacy nav-logo links.
    document.addEventListener('click', function (e) {
      var anchor = e.target.closest('a');
      if (!anchor || !anchor.classList.contains('nav-logo') || !window.location.search) return;
      e.preventDefault();
      var target = anchor.getAttribute('href') || '/';
      var sep = target.indexOf('?') === -1 ? '?' : '&';
      window.location.href = target + sep + window.location.search.substring(1);
    });

    // Fade-in legacy blocks only. Shared reveal is handled by site.js.
    var nodes = document.querySelectorAll('.fade-in, .fade-in-slow');
    if (nodes.length && 'IntersectionObserver' in window) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var delay = Number(entry.target.getAttribute('data-delay') || 0);
          setTimeout(function () { entry.target.classList.add('visible'); }, delay * 80);
          observer.unobserve(entry.target);
        });
      }, { threshold: 0.05 });

      nodes.forEach(function (el) { observer.observe(el); });
    } else {
      nodes.forEach(function (el) { el.classList.add('visible'); });
    }

    // Optional language toggle for pages that still expose data-lang-* attributes.
    var langToggle = document.getElementById('lang-toggle');
    var updateLanguage = function () {
      var lang = localStorage.getItem('woohwahae-lang') || 'ko';
      document.querySelectorAll('[data-lang-' + lang + ']').forEach(function (el) {
        var text = el.getAttribute('data-lang-' + lang);
        if (text) el.innerHTML = text;
      });
      document.querySelectorAll('[data-placeholder-' + lang + ']').forEach(function (el) {
        var ph = el.getAttribute('data-placeholder-' + lang);
        if (ph) el.setAttribute('placeholder', ph);
      });
      if (langToggle) langToggle.textContent = lang === 'ko' ? 'EN' : 'KR';
      document.documentElement.lang = lang;
    };

    updateLanguage();
    if (langToggle) {
      langToggle.addEventListener('click', function () {
        var current = localStorage.getItem('woohwahae-lang') || 'ko';
        localStorage.setItem('woohwahae-lang', current === 'ko' ? 'en' : 'ko');
        updateLanguage();
      });
    }
  });
})();
