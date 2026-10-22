/* Zodiac Seeker / Dyatlov theme v1 — strictly decorative, no API/storage/clock changes. */
(() => {
  'use strict';
  const root = document.documentElement;
  let route;
  try { route = decodeURIComponent(location.pathname).toLowerCase().replace(/\/+$/, '').replace(/\.html$/, '') || '/'; }
  catch (_) { return; }
  // Allowlist, not a broad site-wide wildcard. Original levels and evidence lab stay untouched,
  // even if someone accidentally adds this script to one of those pages.
  const allowed = new Set(['/', '/index', '/play', '/organizer', '/event-ended', '/dispatch']);
  if (!allowed.has(route)) return;
  if (root.dataset.zodiacTheme === 'dyatlov') return;
  root.dataset.zodiacTheme = 'dyatlov';
  function ready() {
    const body = document.body;
    if (!body) return;
    const page = body.querySelector('#days') && body.querySelector('#enter') ? 'launch'
      : body.querySelector('#closure-status') ? 'ending'
      : body.querySelector('.desk') ? 'organizer'
      : body.querySelector('.lab-shell') ? 'dispatch' : 'play';
    root.dataset.zodiacPage = page;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = '#0c0a09';
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (!reduceMotion.matches && page !== 'organizer') {
      const atmosphere = document.createElement('div');
      atmosphere.className = 'zs-atmosphere';
      atmosphere.setAttribute('aria-hidden', 'true');
      // Deterministic decorative particles; no mouse listener, trail, timers, or dependencies.
      for (let i = 0; i < 22; i++) {
        const dot = document.createElement('i');
        dot.className = 'zs-particle';
        dot.style.cssText = `--x:${(i * 47 + 9) % 100}%;--y:${(i * 31 + 5) % 100}%;--duration:${15 + i % 11}s;--delay:-${i % 19}s`;
        atmosphere.appendChild(dot);
      }
      body.prepend(atmosphere);
      if (typeof reduceMotion.addEventListener === 'function') {
        reduceMotion.addEventListener('change', event => { atmosphere.hidden = event.matches; });
      }
    }
    if (!reduceMotion.matches && 'IntersectionObserver' in window) {
      const cards = document.querySelectorAll('.auth-card,.paper-card,.desk section,.dispatch-card,.winner');
      if (cards.length) {
        const observer = new IntersectionObserver(entries => {
          for (const entry of entries) if (entry.isIntersecting) {
            entry.target.setAttribute('data-zs-visible', '');
            observer.unobserve(entry.target);
          }
        }, { threshold: 0.03 });
        cards.forEach(card => { card.setAttribute('data-zs-reveal', ''); observer.observe(card); });
        root.dataset.zsMotion = 'on';
        // Focusing a control always reveals its parent immediately for keyboard users.
        document.addEventListener('focusin', event => {
          const card = event.target.closest && event.target.closest('[data-zs-reveal]');
          if (card) card.setAttribute('data-zs-visible', '');
        });
      }
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, { once: true });
  else ready();
})();
