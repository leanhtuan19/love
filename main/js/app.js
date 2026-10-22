(() => {
  'use strict';

  function initialize() {
    const startDate = new Date('2026-08-14T00:00:00');
    const dayCount = document.getElementById('day-count');
    const elapsedTime = document.getElementById('elapsed-time');
    const anniversary = document.getElementById('anniversary');
    const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const pad = (value) => String(value).padStart(2, '0');
    const heartButton = document.getElementById('heart');
    const heartMessage = document.getElementById('heart-message');
    const musicStatus = document.getElementById('music-status');
    const celebrationLayer = document.getElementById('celebration-layer');
    const loveCard = document.querySelector('.love-card');
    const statusStates = new WeakMap();
    const statusElements = [heartMessage, musicStatus].filter(Boolean);
    const canAnimate = () => !motionPreference.matches && !document.hidden;
    let clockTimer = null;
    let previousDays = null;
    let counterFrame = null;
    let counterPulseTimer = null;

    function updateStatus(element, message) {
      if (!element) return;
      const previous = statusStates.get(element);
      if (previous?.message === message) return;
      const transition = (previous?.transition ?? -1) + 1;
      const visual = document.createElement('span');
      visual.className = 'status-visual';
      visual.setAttribute('aria-hidden', 'true');
      visual.textContent = message;
      if (canAnimate()) {
        const mode = ['status-typewriter', 'status-fade', 'status-slide'][transition % 3];
        visual.classList.add(mode);
        const characters = typeof Intl.Segmenter === 'function'
          ? Array.from(new Intl.Segmenter('vi', { granularity: 'grapheme' }).segment(message), (part) => part.segment)
          : Array.from(message);
        const characterDelay = Math.min(25, 1400 / Math.max(1, characters.length));
        visual.style.setProperty('--status-steps', String(characters.length));
        visual.style.setProperty('--character-delay', `${characterDelay}ms`);
        visual.style.setProperty('--status-duration', `${Math.min(1400, Math.max(650, characters.length * 25))}ms`);
        if (mode === 'status-typewriter') {
          visual.replaceChildren(...characters.map((character, index) => {
            const span = document.createElement('span');
            span.className = 'status-character';
            span.style.setProperty('--char-index', String(index));
            span.textContent = character;
            return span;
          }));
        }
      }
      const announcement = document.createElement('span');
      announcement.className = 'sr-only';
      announcement.textContent = message;
      element.setAttribute('aria-atomic', 'true');
      // Announce the complete message once; only the hidden visual copy animates.
      element.replaceChildren(visual, announcement);
      statusStates.set(element, { message, transition });
    }

    function settleStatuses() {
      statusElements.forEach((element) => {
        element.querySelector('.status-visual')?.classList.remove('status-typewriter', 'status-fade', 'status-slide');
      });
    }

    function setCounterText(value) {
      if (dayCount && dayCount.textContent !== String(value)) dayCount.textContent = String(value);
    }

    function settleCounter() {
      if (counterFrame !== null) window.cancelAnimationFrame(counterFrame);
      counterFrame = null;
      if (previousDays !== null) setCounterText(previousDays);
      dayCount?.classList.remove('is-counting');
    }

    function renderDays(days) {
      if (!dayCount || days === previousDays) return;
      const firstRender = previousDays === null;
      const increased = previousDays !== null && days > previousDays;
      previousDays = days;
      settleCounter();
      dayCount.setAttribute('aria-label', `${days} ngày bên nhau`);
      if (firstRender && days > 0 && canAnimate()) {
        let startedAt = null;
        dayCount.classList.add('is-counting');
        setCounterText(0);
        const countUp = (timestamp) => {
          counterFrame = null;
          if (!canAnimate()) {
            settleCounter();
            return;
          }
          if (startedAt === null) startedAt = timestamp;
          const progress = Math.min(1, (timestamp - startedAt) / 1150);
          setCounterText(Math.round(days * (1 - Math.pow(1 - progress, 3))));
          if (progress < 1) counterFrame = window.requestAnimationFrame(countUp);
          else dayCount.classList.remove('is-counting');
        };
        counterFrame = window.requestAnimationFrame(countUp);
      }
      window.clearTimeout(counterPulseTimer);
      dayCount.classList.remove('is-updated');
      if (increased && canAnimate()) {
        void dayCount.offsetWidth;
        dayCount.classList.add('is-updated');
        counterPulseTimer = window.setTimeout(() => dayCount.classList.remove('is-updated'), 800);
      }
    }

    if (anniversary) {
      anniversary.textContent = `${pad(startDate.getDate())}/${pad(startDate.getMonth() + 1)}/${startDate.getFullYear()}`;
      anniversary.setAttribute('datetime', `${startDate.getFullYear()}-${pad(startDate.getMonth() + 1)}-${pad(startDate.getDate())}`);
    }

    function updateClock() {
      const totalSeconds = Math.max(0, Math.floor((Date.now() - startDate.getTime()) / 1000));
      const days = Math.floor(totalSeconds / 86400);
      const hours = Math.floor(totalSeconds / 3600) % 24;
      const minutes = Math.floor(totalSeconds / 60) % 60;
      const seconds = totalSeconds % 60;

      renderDays(days);
      if (elapsedTime) {
        elapsedTime.textContent = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
        elapsedTime.setAttribute('datetime', `PT${hours}H${minutes}M${seconds}S`);
        elapsedTime.setAttribute('aria-label', `${hours} giờ, ${minutes} phút, ${seconds} giây`);
      }
    }

    function synchronizeClock() {
      if (clockTimer !== null) window.clearInterval(clockTimer);
      clockTimer = null;
      updateClock();
      if (!document.hidden) clockTimer = window.setInterval(updateClock, 1000);
    }

    synchronizeClock();
    let heartbeatTimer = null;
    let celebrationTimer = null;
    const burstAnimations = new Set();
    const burstNodes = new Set();

    function clearBurst() {
      burstAnimations.forEach((animation) => animation.cancel());
      burstAnimations.clear();
      burstNodes.forEach((node) => node.remove());
      burstNodes.clear();
    }

    function cancelCelebration() {
      window.clearTimeout(heartbeatTimer);
      window.clearTimeout(celebrationTimer);
      heartButton?.classList.remove('is-beating');
      loveCard?.classList.remove('is-celebrating');
      clearBurst();
    }

    function animateBurstNode(node, keyframes, options) {
      celebrationLayer.appendChild(node);
      burstNodes.add(node);
      if (typeof node.animate !== 'function') {
        node.remove();
        burstNodes.delete(node);
        return;
      }
      const animation = node.animate(keyframes, options);
      burstAnimations.add(animation);
      animation.onfinish = () => {
        burstAnimations.delete(animation);
        burstNodes.delete(node);
        node.remove();
      };
    }

    function celebrate() {
      cancelCelebration();
      if (!canAnimate() || !heartButton) return;
      void heartButton.offsetWidth;
      heartButton.classList.add('is-beating');
      loveCard?.classList.add('is-celebrating');
      heartbeatTimer = window.setTimeout(() => heartButton.classList.remove('is-beating'), 600);
      celebrationTimer = window.setTimeout(cancelCelebration, 1500);
      if (!celebrationLayer) return;

      const bounds = heartButton.getBoundingClientRect();
      const centerX = Math.max(0, Math.min(window.innerWidth, bounds.left + bounds.width / 2));
      const centerY = Math.max(0, Math.min(window.innerHeight, bounds.top + bounds.height / 2));
      const radius = Math.min(180, window.innerWidth * 0.38, window.innerHeight * 0.3);
      const count = window.innerWidth < 600 ? 16 : 24;
      const colors = ['#ce6d93', '#b66b96', '#e5a7be', '#f1c2d4', '#fff2f7'];
      for (let index = 0; index < count; index += 1) {
        const particle = document.createElement('span');
        particle.className = 'celebration-particle';
        particle.textContent = index % 4 === 0 ? '✦' : '♥';
        particle.style.left = `${centerX}px`;
        particle.style.top = `${centerY}px`;
        particle.style.fontSize = `${10 + Math.random() * 13}px`;
        particle.style.color = colors[index % colors.length];
        const angle = Math.PI * 2 * index / count + (Math.random() - 0.5) * 0.3;
        const distance = radius * (0.55 + Math.random() * 0.45);
        const x = Math.cos(angle) * distance;
        const y = Math.sin(angle) * distance - radius * 0.2;
        const rotation = Math.round((Math.random() - 0.5) * 180);
        animateBurstNode(particle, [
          { transform: 'translate(-50%, -50%) scale(0.25)', opacity: 0 },
          { transform: `translate(calc(-50% + ${x * 0.35}px), calc(-50% + ${y * 0.35}px)) scale(1) rotate(${rotation * 0.3}deg)`, opacity: 0.9, offset: 0.22 },
          { transform: `translate(calc(-50% + ${x}px), calc(-50% + ${y + 30}px)) scale(0.4) rotate(${rotation}deg)`, opacity: 0 }
        ], { duration: 900 + Math.random() * 420, easing: 'cubic-bezier(.16,.7,.3,1)', fill: 'both' });
      }
      for (let index = 0; index < 2; index += 1) {
        const ring = document.createElement('span');
        ring.className = 'celebration-ring';
        ring.style.left = `${centerX}px`;
        ring.style.top = `${centerY}px`;
        ring.style.color = colors[index];
        animateBurstNode(ring, [
          { transform: 'translate(-50%, -50%) scale(0.3)', opacity: 0.65 },
          { transform: 'translate(-50%, -50%) scale(5.5)', opacity: 0 }
        ], { duration: 850, delay: index * 140, easing: 'ease-out', fill: 'both' });
      }
    }

    if (heartButton) {
      heartButton.disabled = false;
      const messages = [
        'Thêm một ngày, thêm một chút thương.',
        'Cảm ơn vì đã luôn ở đây.',
        'Mãi cùng nhau nhé.',
        'Yêu thương vẫn đong đầy.'
      ];
      let messageIndex = 0;
      heartButton.addEventListener('click', () => {
        updateStatus(heartMessage, messages[messageIndex]);
        messageIndex = (messageIndex + 1) % messages.length;
        celebrate();
      });
    }

    const audio = document.getElementById('love-audio');
    const musicSection = document.getElementById('music');
    const musicButton = document.getElementById('music-toggle');
    const musicLabel = musicButton?.querySelector('[data-music-label]');
    if (audio && musicButton) {
      musicButton.disabled = false;
      let pending = false;
      let playing = false;
      let playAttempt = 0;
      const setMusicStatus = (message) => updateStatus(musicStatus, message);
      const renderMusicState = () => {
        const active = !audio.paused || pending;
        const label = active ? 'Tạm dừng' : 'Bật nhạc';
        if (musicLabel && musicLabel.textContent !== label) musicLabel.textContent = label;
        musicButton.setAttribute('aria-pressed', String(active));
        musicButton.setAttribute('aria-label', label);
        musicButton.setAttribute('aria-busy', String(pending));
        musicSection?.classList.toggle('is-playing', playing && !audio.paused && !audio.ended && !audio.error);
        musicSection?.classList.toggle('is-loading', pending);
      };

      musicButton.addEventListener('click', async () => {
        if (!audio.paused || pending) {
          playAttempt += 1;
          pending = false;
          playing = false;
          audio.pause();
          renderMusicState();
          setMusicStatus('Nhạc đã tạm dừng.');
          return;
        }

        const currentAttempt = ++playAttempt;
        pending = true;
        playing = false;
        renderMusicState();
        setMusicStatus('Đang tải bản nhạc…');
        try {
          if (audio.error) audio.load();
          await audio.play();
          if (currentAttempt !== playAttempt) return;
          pending = !playing && !audio.paused;
          renderMusicState();
        } catch (error) {
          if (currentAttempt !== playAttempt) return;
          pending = false;
          playing = false;
          if (!audio.paused) audio.pause();
          renderMusicState();
          setMusicStatus(error?.name === 'NotAllowedError'
            ? 'Trình duyệt chưa cho phép phát nhạc. Hãy thử lại.'
            : 'Chưa phát được bản nhạc. Bạn có thể thử lại.');
        }
      });

      audio.addEventListener('play', () => {
        if (audio.paused) return;
        pending = true;
        playing = false;
        renderMusicState();
        setMusicStatus('Đang tải bản nhạc…');
      });
      audio.addEventListener('playing', () => {
        if (audio.paused || audio.error) return;
        pending = false;
        playing = true;
        renderMusicState();
        setMusicStatus('Giai điệu dành cho chúng mình đang phát.');
      });
      const handleBuffering = () => {
        if (audio.paused) return;
        pending = true;
        playing = false;
        renderMusicState();
        setMusicStatus('Chờ một chút để giai điệu tiếp tục…');
      };
      audio.addEventListener('waiting', handleBuffering);
      audio.addEventListener('stalled', () => {
        if (audio.readyState < 3) handleBuffering();
      });
      audio.addEventListener('pause', () => {
        if (!audio.paused) return;
        playAttempt += 1;
        pending = false;
        playing = false;
        renderMusicState();
        if (!audio.error) setMusicStatus('Nhạc đã tạm dừng.');
      });
      audio.addEventListener('ended', () => {
        playAttempt += 1;
        pending = false;
        playing = false;
        renderMusicState();
        setMusicStatus('Bản nhạc đã kết thúc.');
      });
      audio.addEventListener('error', () => {
        if (!audio.error) return;
        playAttempt += 1;
        pending = false;
        playing = false;
        audio.pause();
        renderMusicState();
        setMusicStatus('Chưa tải được bản nhạc. Bạn có thể thử lại.');
      });
      renderMusicState();
    }

    statusElements.forEach((element) => updateStatus(element, element.textContent.trim()));
    let synchronizeBackground = () => {};
    function synchronizeVisuals() {
      document.documentElement.classList.toggle('is-page-hidden', document.hidden);
      if (!canAnimate()) {
        settleCounter();
        window.clearTimeout(counterPulseTimer);
        dayCount?.classList.remove('is-updated');
        cancelCelebration();
        settleStatuses();
      }
      synchronizeBackground();
    }
    document.addEventListener('visibilitychange', () => {
      synchronizeClock();
      synchronizeVisuals();
    });
    if (motionPreference.addEventListener) {
      motionPreference.addEventListener('change', synchronizeVisuals);
    } else {
      motionPreference.addListener(synchronizeVisuals);
    }
    synchronizeVisuals();

    const canvas = document.getElementById('c');
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;

    let width = 1;
    let height = 1;
    let particles = [];
    let frameId = null;
    let lastFrameTime = null;
    const random = (minimum, maximum) => minimum + Math.random() * Math.max(0, maximum - minimum);

    function drawHearts() {
      context.clearRect(0, 0, width, height);
      particles.forEach((particle) => {
        context.save();
        context.translate(particle.x, particle.y);
        context.rotate(particle.angle);
        context.scale(particle.size, particle.size);
        context.fillStyle = `rgba(205, 86, 119, ${particle.opacity})`;
        context.beginPath();
        context.moveTo(0, 0.5);
        context.bezierCurveTo(-0.15, 0.32, -0.58, 0.03, -0.5, -0.25);
        context.bezierCurveTo(-0.42, -0.58, -0.08, -0.53, 0, -0.25);
        context.bezierCurveTo(0.08, -0.53, 0.42, -0.58, 0.5, -0.25);
        context.bezierCurveTo(0.58, 0.03, 0.15, 0.32, 0, 0.5);
        context.closePath();
        context.fill();
        context.restore();
      });
    }

    function stopAnimation() {
      if (frameId !== null) window.cancelAnimationFrame(frameId);
      frameId = null;
      lastFrameTime = null;
    }

    function animate(timestamp) {
      frameId = null;
      if (document.hidden || motionPreference.matches) {
        lastFrameTime = null;
        return;
      }
      const elapsed = lastFrameTime === null ? 0 : Math.min((timestamp - lastFrameTime) / 1000, 0.05);
      lastFrameTime = timestamp;
      particles.forEach((particle) => {
        const margin = particle.size * 0.8;
        particle.x += particle.vx * elapsed;
        particle.y += particle.vy * elapsed;
        if (particle.x < margin || particle.x > width - margin) {
          particle.vx *= -1;
          particle.x = Math.max(margin, Math.min(width - margin, particle.x));
        }
        if (particle.y < margin || particle.y > height - margin) {
          particle.vy *= -1;
          particle.y = Math.max(margin, Math.min(height - margin, particle.y));
        }
      });
      drawHearts();
      frameId = window.requestAnimationFrame(animate);
    }

    function synchronizeAnimation() {
      stopAnimation();
      drawHearts();
      if (!document.hidden && !motionPreference.matches) {
        frameId = window.requestAnimationFrame(animate);
      }
    }

    function resizeCanvas() {
      const bounds = canvas.getBoundingClientRect();
      width = Math.max(1, bounds.width || window.innerWidth || 1);
      height = Math.max(1, bounds.height || window.innerHeight || 1);
      const pixelRatio = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
      canvas.width = Math.round(width * pixelRatio);
      canvas.height = Math.round(height * pixelRatio);
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      const count = Math.max(4, Math.min(22, Math.round(width * height / 55000)));
      const maximumSize = Math.min(24, width / 4, height / 4);
      particles = Array.from({ length: count }, () => {
        const size = random(maximumSize * 0.45, maximumSize);
        const margin = size * 0.8;
        return {
          x: random(margin, width - margin),
          y: random(margin, height - margin),
          size,
          vx: random(-4, 4),
          vy: random(-10, -4),
          angle: random(-0.35, 0.35),
          opacity: random(0.08, 0.2)
        };
      });
      synchronizeAnimation();
    }

    synchronizeBackground = synchronizeAnimation;
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, { once: true });
  } else {
    initialize();
  }
})();
