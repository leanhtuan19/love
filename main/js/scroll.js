(() => {
  'use strict';

  const root = document.documentElement;
  const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const progressBar = document.querySelector('.scroll-progress > span');
  const sections = Array.from(document.querySelectorAll('[data-reveal]'));
  let frame = null;
  let progressFrame = null;
  let target = window.scrollY;
  let lastTimestamp = null;
  let observer = null;

  const maximumScroll = () => Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
  const clamp = (value) => Math.max(0, Math.min(maximumScroll(), value));

  function stopScroll() {
    if (frame !== null) window.cancelAnimationFrame(frame);
    frame = null;
    lastTimestamp = null;
    target = window.scrollY;
    root.classList.remove('is-smooth-scrolling');
  }

  function updateProgress() {
    progressFrame = null;
    if (document.body.classList.contains('dialog-open')) return;
    const maximum = maximumScroll();
    if (progressBar) progressBar.style.transform = `scaleX(${maximum ? Math.min(1, Math.max(0, window.scrollY / maximum)) : 0})`;
  }

  function requestProgress() {
    if (progressFrame === null) progressFrame = window.requestAnimationFrame(updateProgress);
  }

  function animateScroll(timestamp) {
    frame = null;
    if (motionPreference.matches || document.hidden || document.body.classList.contains('dialog-open')) {
      stopScroll();
      return;
    }
    target = clamp(target);
    const elapsed = lastTimestamp === null ? 16 : Math.min(50, timestamp - lastTimestamp);
    lastTimestamp = timestamp;
    const current = window.scrollY;
    const remaining = target - current;
    if (Math.abs(remaining) < 1) {
      window.scrollTo({ top: target, behavior: 'instant' });
      stopScroll();
      return;
    }
    const next = current + remaining * (1 - Math.exp(-elapsed / 65));
    window.scrollTo({ top: next, behavior: 'instant' });
    // Avoid a subpixel rounding stall when a browser rounds scrollY to integers.
    if (window.scrollY === current && Math.abs(remaining) < 3) {
      window.scrollTo({ top: target, behavior: 'instant' });
      stopScroll();
      return;
    }
    frame = window.requestAnimationFrame(animateScroll);
  }

  function hasNativeScrollTarget(element) {
    if (!element) return false;
    if (element.closest('audio, input, textarea, select, [contenteditable], [role="slider"], dialog')) return true;
    for (let parent = element; parent && parent !== document.body; parent = parent.parentElement) {
      if (parent.scrollHeight > parent.clientHeight + 1 && /auto|scroll/.test(window.getComputedStyle(parent).overflowY)) return true;
    }
    return false;
  }

  window.addEventListener('wheel', (event) => {
    if (event.defaultPrevented || !event.cancelable || motionPreference.matches || !finePointer.matches ||
        event.ctrlKey || event.metaKey || event.shiftKey || !event.deltaY ||
        Math.abs(event.deltaX) > Math.abs(event.deltaY) || document.body.classList.contains('dialog-open') ||
        hasNativeScrollTarget(event.target instanceof Element ? event.target : null)) {
      stopScroll();
      return;
    }
    const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? window.innerHeight : 1);
    const nextTarget = clamp((frame === null ? window.scrollY : target) + delta);
    if (nextTarget === window.scrollY && frame === null) return;
    event.preventDefault();
    target = nextTarget;
    if (frame === null) {
      root.classList.add('is-smooth-scrolling');
      lastTimestamp = null;
      frame = window.requestAnimationFrame(animateScroll);
    }
  }, { passive: false });

  window.addEventListener('scroll', requestProgress, { passive: true });
  window.addEventListener('resize', () => { stopScroll(); requestProgress(); }, { passive: true });
  window.addEventListener('pointerdown', stopScroll, { passive: true });
  window.addEventListener('touchstart', stopScroll, { passive: true });
  window.addEventListener('keydown', (event) => {
    if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) stopScroll();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopScroll();
      if (progressFrame !== null) window.cancelAnimationFrame(progressFrame);
      progressFrame = null;
    } else requestProgress();
  });

  function setupReveals() {
    stopScroll();
    observer?.disconnect();
    root.classList.remove('reveal-enabled');
    if (motionPreference.matches || typeof IntersectionObserver !== 'function') {
      sections.forEach((section) => section.classList.add('is-revealed'));
      return;
    }
    observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-revealed');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -12px 0px' });
    root.classList.add('reveal-enabled');
    sections.forEach((section) => {
      if (!section.classList.contains('is-revealed')) observer.observe(section);
    });
    requestProgress();
  }

  // Keyboard focus must never land on content still waiting for a scroll reveal.
  document.addEventListener('focusin', (event) => {
    const section = event.target instanceof Element ? event.target.closest('[data-reveal]') : null;
    section?.classList.add('is-revealed');
  });
  if (motionPreference.addEventListener) motionPreference.addEventListener('change', setupReveals);
  else motionPreference.addListener(setupReveals);
  setupReveals();
})();
