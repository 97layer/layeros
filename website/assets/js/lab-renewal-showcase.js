/*!
 * WOOHWAHAE Lab — Full Renewal Showcase controller
 */

(function () {
  'use strict';

  var root = document.body;
  if (!root || !root.classList.contains('page-lab-renewal')) return;

  var tabs = Array.prototype.slice.call(document.querySelectorAll('[data-renewal-view]'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('[data-renewal-panel]'));
  var vpButtons = Array.prototype.slice.call(document.querySelectorAll('[data-renewal-vp]'));
  var canvas = document.getElementById('renewal-canvas');

  if (!tabs.length || !panels.length || !canvas) return;

  function setActiveView(view) {
    tabs.forEach(function (tab) {
      var isActive = tab.getAttribute('data-renewal-view') === view;
      tab.classList.toggle('is-active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    panels.forEach(function (panel) {
      var isActive = panel.getAttribute('data-renewal-panel') === view;
      panel.classList.toggle('is-active', isActive);
    });
  }

  function setViewport(width) {
    var value = Number(width);
    if (!value) return;

    canvas.style.setProperty('--renewal-canvas-width', value + 'px');

    vpButtons.forEach(function (btn) {
      var isActive = Number(btn.getAttribute('data-renewal-vp')) === value;
      btn.classList.toggle('is-active', isActive);
      btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
  }

  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      setActiveView(tab.getAttribute('data-renewal-view'));
    });
  });

  vpButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      setViewport(btn.getAttribute('data-renewal-vp'));
    });
  });

  setActiveView('ops');
  setViewport(1440);
})();
