(() => {
  'use strict';
  const root = document.documentElement;
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const FALLBACK_TIMEOUT_MS = 5000;
  const PROFILE_ENTRANCE_MS = 1450;
  let finished = false;
  let finishing = false;
  let initializedProfiles = false;
  let profileObserver = null;
  let profileTimer = null;
  let exitTimer = null;
  let fallbackTimer = null;
  root.classList.add('love-loading');

  function settleProfiles() {
    profileObserver?.disconnect();
    profileObserver = null;
    if (profileTimer !== null) window.clearTimeout(profileTimer);
    profileTimer = null;
    root.classList.remove('love-profiles-waiting');
    document.querySelectorAll('.profile').forEach((profile) => {
      profile.classList.remove('profile-love-enter');
      profile.classList.add('profile-love-done');
      profile.querySelector('.profile-love-dust')?.remove();
    });
  }

  function enterProfiles() {
    if (motion.matches || document.hidden) { settleProfiles(); return; }
    profileObserver?.disconnect();
    root.classList.remove('love-profiles-waiting');
    const particles = [
      ['6%', '50%', '-15px', '11px', '♡'],
      ['88%', '35%', '13px', '9px', '✦'],
      ['17%', '12%', '-10px', '8px', '✧'],
      ['81%', '70%', '16px', '12px', '♡']
    ];
    document.querySelectorAll('.profile').forEach((profile, index) => {
      profile.style.setProperty('--profile-index', String(index));
      const dust = document.createElement('span');
      dust.className = 'profile-love-dust';
      dust.setAttribute('aria-hidden', 'true');
      particles.forEach(([x, y, dx, size, symbol]) => {
        const particle = document.createElement('span');
        particle.textContent = symbol;
        particle.style.setProperty('--dust-x', x);
        particle.style.setProperty('--dust-y', y);
        particle.style.setProperty('--dust-dx', dx);
        particle.style.setProperty('--dust-size', size);
        dust.appendChild(particle);
      });
      profile.appendChild(dust);
      profile.classList.add('profile-love-enter');
    });
    profileTimer = window.setTimeout(settleProfiles, PROFILE_ENTRANCE_MS);
  }

  function initializeProfileEntrance() {
    if (initializedProfiles) return;
    initializedProfiles = true;
    const info = document.getElementById('info');
    if (!info || motion.matches || document.hidden || typeof IntersectionObserver !== 'function') {
      enterProfiles();
      return;
    }
    root.classList.add('love-profiles-waiting');
    profileObserver = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) enterProfiles();
    }, { threshold: .1 });
    profileObserver.observe(info);
  }

  function removeLoader() {
    if (finished) return;
    finished = true;
    window.clearTimeout(exitTimer);
    window.clearTimeout(fallbackTimer);
    document.getElementById('love-loader')?.remove();
    initializeProfileEntrance();
    root.classList.remove('love-loading', 'love-loading-out');
    document.dispatchEvent(new CustomEvent('love:ready'));
  }

  function finishLoading() {
    if (finishing || finished) return;
    finishing = true;
    root.classList.add('love-loading-out');
    const loader = document.getElementById('love-loader');
    if (!loader || motion.matches || document.hidden) { removeLoader(); return; }
    loader.addEventListener('transitionend', (event) => {
      if (event.target === loader && event.propertyName === 'opacity') removeLoader();
    });
    exitTimer = window.setTimeout(removeLoader, 320);
  }

  fallbackTimer = window.setTimeout(finishLoading, FALLBACK_TIMEOUT_MS);
  document.addEventListener('DOMContentLoaded', () => {
    // Defer scripts have now executed. Remote avatars and audio do not block readiness.
    if (finished) initializeProfileEntrance();
    else finishLoading();
  }, { once: true });
  if (document.readyState !== 'loading') finishLoading();
  document.addEventListener('focusin', (event) => {
    if (finished && event.target instanceof Element && event.target.closest('.profile')) settleProfiles();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { settleProfiles(); if (finishing) removeLoader(); }
  });
  const onMotionChange = () => {
    if (motion.matches) { settleProfiles(); if (finishing) removeLoader(); }
  };
  if (motion.addEventListener) motion.addEventListener('change', onMotionChange);
  else motion.addListener(onMotionChange);
})();
