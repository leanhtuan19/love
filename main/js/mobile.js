(() => {
  'use strict';

  const root = document.documentElement;
  const owners = new Set();
  const viewportProperties = ['--love-viewport-height', '--love-viewport-width', '--love-viewport-top', '--love-viewport-left'];
  const bodyProperties = ['position', 'top', 'left', 'width', 'padding-right'];
  const editable = 'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="button"]):not([type="submit"]):not([type="file"]), textarea, select, [contenteditable]:not([contenteditable="false"])';
  let saved = null;
  let viewport = null;
  let frame = null;
  let focusTimer = null;
  let lastHeight = null;

  function snapshot(style, properties) {
    return properties.map((property) => [property, style.getPropertyValue(property), style.getPropertyPriority(property)]);
  }

  function restore(style, values) {
    values.forEach(([property, value, priority]) => {
      if (value) style.setProperty(property, value, priority);
      else style.removeProperty(property);
    });
  }

  function bounds() {
    const positive = (value, fallback) => Number.isFinite(value) && value > 0 ? value : fallback;
    return {
      height: positive(viewport?.height, window.innerHeight),
      width: positive(viewport?.width, root.clientWidth || window.innerWidth),
      top: Math.max(0, viewport?.offsetTop || 0),
      left: Math.max(0, viewport?.offsetLeft || 0)
    };
  }

  function revealActiveControl() {
    focusTimer = null;
    const active = document.activeElement;
    if (!(active instanceof HTMLElement) || !active.matches(editable)) return;
    const dialog = active.closest('dialog[open]');
    if (!dialog || !owners.has(dialog)) return;

    // Move only the modal's scroll container, never the document. Waiting until
    // resize events settle avoids fighting the browser's keyboard animation.
    let scroller = active.parentElement;
    while (scroller && dialog.contains(scroller)) {
      const style = getComputedStyle(scroller);
      if (/auto|scroll/.test(style.overflowY) && scroller.scrollHeight > scroller.clientHeight + 1) {
        const view = bounds();
        const container = scroller.getBoundingClientRect();
        const control = active.getBoundingClientRect();
        const top = Math.max(view.top, container.top) + Math.max(12, Number.parseFloat(style.scrollPaddingTop) || 0);
        const bottom = Math.min(view.top + view.height, container.bottom) - 16;
        if (bottom <= top) return;
        let delta = 0;
        if (control.top < top || control.height > bottom - top) delta = control.top - top;
        else if (control.bottom > bottom) delta = control.bottom - bottom;
        if (Math.abs(delta) > 1) scroller.scrollTo({ top: scroller.scrollTop + delta, behavior: 'instant' });
        return;
      }
      if (scroller === dialog) break;
      scroller = scroller.parentElement;
    }
  }

  function scheduleFocus() {
    if (focusTimer !== null) window.clearTimeout(focusTimer);
    focusTimer = window.setTimeout(revealActiveControl, 100);
  }

  function refresh() {
    if (!owners.size) return;
    const view = bounds();
    Object.entries(view).forEach(([key, value]) => {
      const property = `--love-viewport-${key}`;
      const next = `${Math.round(value * 100) / 100}px`;
      if (root.style.getPropertyValue(property) !== next) root.style.setProperty(property, next);
    });
    if (lastHeight !== null && Math.abs(lastHeight - view.height) > 1) scheduleFocus();
    lastHeight = view.height;
  }

  function requestRefresh() {
    if (frame !== null) return;
    frame = window.requestAnimationFrame(() => { frame = null; refresh(); });
  }

  function focusChanged(event) {
    if (event.target instanceof HTMLElement && event.target.matches(editable)) scheduleFocus();
  }

  function lock(owner) {
    if (!(owner instanceof Element) || owners.has(owner)) return;
    owners.add(owner);
    if (saved) { refresh(); return; }
    const body = document.body;
    const scrollbar = Math.max(0, window.innerWidth - root.clientWidth);
    const padding = Number.parseFloat(getComputedStyle(body).paddingRight) || 0;
    saved = { x: window.scrollX, y: window.scrollY, body: snapshot(body.style, bodyProperties),
      viewport: snapshot(root.style, viewportProperties), hadClass: body.classList.contains('dialog-open') };
    body.classList.add('dialog-open');
    body.style.position = 'fixed';
    body.style.top = `${-saved.y}px`;
    body.style.left = `${-saved.x}px`;
    body.style.width = '100%';
    if (scrollbar) body.style.paddingRight = `${padding + scrollbar}px`;
    viewport = window.visualViewport || null;
    window.addEventListener('resize', requestRefresh, { passive: true });
    window.addEventListener('orientationchange', requestRefresh, { passive: true });
    window.addEventListener('pageshow', requestRefresh, { passive: true });
    viewport?.addEventListener('resize', requestRefresh, { passive: true });
    viewport?.addEventListener('scroll', requestRefresh, { passive: true });
    document.addEventListener('focusin', focusChanged);
    refresh();
  }

  function unlock(owner) {
    if (!owners.delete(owner) || owners.size || !saved) return;
    const previous = saved;
    saved = null;
    window.removeEventListener('resize', requestRefresh);
    window.removeEventListener('orientationchange', requestRefresh);
    window.removeEventListener('pageshow', requestRefresh);
    viewport?.removeEventListener('resize', requestRefresh);
    viewport?.removeEventListener('scroll', requestRefresh);
    document.removeEventListener('focusin', focusChanged);
    viewport = null;
    lastHeight = null;
    if (frame !== null) window.cancelAnimationFrame(frame);
    if (focusTimer !== null) window.clearTimeout(focusTimer);
    frame = focusTimer = null;
    restore(document.body.style, previous.body);
    restore(root.style, previous.viewport);
    document.body.classList.toggle('dialog-open', previous.hadClass);

    const behavior = snapshot(root.style, ['scroll-behavior']);
    root.style.setProperty('scroll-behavior', 'auto', 'important');
    window.scrollTo({ left: previous.x, top: previous.y, behavior: 'instant' });
    restore(root.style, behavior);
  }

  window.LoveDaysViewport = Object.freeze({ lock, unlock, refresh });

  // Safari exposes gesture events for pinch. Only cancel these dedicated zoom
  // events on touch devices, never ordinary pointer/touch/scroll events.
  const touchDevice = window.matchMedia('(any-pointer: coarse)');
  const preventGestureZoom = (event) => {
    if (touchDevice.matches && event.cancelable) event.preventDefault();
  };
  document.addEventListener('gesturestart', preventGestureZoom, { passive: false });
  document.addEventListener('gesturechange', preventGestureZoom, { passive: false });
})();
