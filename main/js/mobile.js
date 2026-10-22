(() => {
  'use strict';
  // Safari exposes gesture events for pinch. Only cancel these dedicated zoom
  // events on touch devices, never ordinary pointer/touch/scroll events.
  const touchDevice = window.matchMedia('(any-pointer: coarse)');
  const preventGestureZoom = (event) => {
    if (touchDevice.matches && event.cancelable) event.preventDefault();
  };
  document.addEventListener('gesturestart', preventGestureZoom, { passive: false });
  document.addEventListener('gesturechange', preventGestureZoom, { passive: false });
})();
