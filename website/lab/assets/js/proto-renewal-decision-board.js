/*!
 * WOOHWAHAE Lab — Renewal Decision Board controller
 */

(function () {
  'use strict';

  var root = document.body;
  if (!root || !root.classList.contains('page-lab-renewal')) return;

  var tabs = document.querySelectorAll('[data-decision-view]');
  var panels = document.querySelectorAll('[data-decision-panel]');
  var canvas = document.getElementById('decision-canvas');
  var vpButtons = document.querySelectorAll('[data-decision-vp]');

  if (!tabs.length || !panels.length || !canvas) return;

  function setView(view) {
    tabs.forEach(function (tab) {
      var active = tab.getAttribute('data-decision-view') === view;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });

    panels.forEach(function (panel) {
      var active = panel.getAttribute('data-decision-panel') === view;
      panel.classList.toggle('is-active', active);
    });
  }

  function setViewport(width) {
    var value = Number(width);
    if (!value) return;

    canvas.style.setProperty('--renewal-canvas-width', value + 'px');
    vpButtons.forEach(function (button) {
      var active = Number(button.getAttribute('data-decision-vp')) === value;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
  }

  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      setView(tab.getAttribute('data-decision-view'));
    });
  });

  vpButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      setViewport(button.getAttribute('data-decision-vp'));
    });
  });

  setView('identity');
  setViewport(1440);
})();
