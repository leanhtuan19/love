(() => {
  'use strict';

  let current = null;
  let controller = null;
  let lastRefresh = 0;
  const url = (path) => new URL(path, new URL('.', document.baseURI)).href;
  const setText = (selector, value) => {
    if (typeof value === 'string') document.querySelectorAll(selector).forEach((node) => { node.textContent = value; });
  };
  function asset(value) {
    if (typeof value !== 'string' || !value.trim()) return null;
    try {
      const parsed = new URL(value, new URL('.', document.baseURI));
      return parsed.protocol === 'https:' || (parsed.origin === location.origin && parsed.protocol === 'http:') ? parsed.href : null;
    } catch (_) { return null; }
  }

  function apply(data) {
    if (!data || typeof data !== 'object') return;
    current = data;
    const content = data.content || {};
    if (typeof content.title === 'string') document.title = content.title;
    setText('.page-header h1', content.heading);
    setText('.page-subtitle', content.introduction);
    if (typeof content.kicker === 'string') {
      const label = document.querySelector('.page-header .eyebrow');
      if (label) { const heart = document.createElement('span'); heart.setAttribute('aria-hidden', 'true'); heart.textContent = '♡'; label.replaceChildren(heart, document.createTextNode(' ' + content.kicker)); }
    }
    setText('#clock-box .section-label', content.clockLabel);
    if (typeof content.loveNote === 'string') {
      const note = document.querySelector('.love-message');
      if (note) { const heart = document.createElement('span'); heart.setAttribute('aria-hidden', 'true'); heart.textContent = ' ♡'; note.replaceChildren(document.createTextNode(content.loveNote), heart); }
    }
    setText('.record-details h2', content.musicTitle);
    setText('.record-eyebrow', content.musicEyebrow);
    setText('.record-description', content.musicDescription);
    setText('.record-label > span', content.recordLabel);
    if (typeof content.footer === 'string') {
      const footer = document.querySelector('#wrapper > footer');
      if (footer) { const heart = document.createElement('span'); heart.setAttribute('aria-hidden', 'true'); heart.textContent = ' ♥'; footer.replaceChildren(document.createTextNode(content.footer), heart); }
    }
    setText('#profile-dialog .eyebrow', content.profileEyebrow);
    if (typeof content.profileNote === 'string') {
      const note = document.querySelector('.profile-dialog-note');
      if (note) { const heart = document.createElement('span'); heart.setAttribute('aria-hidden', 'true'); heart.textContent = '♡'; note.replaceChildren(heart, document.createTextNode(' ' + content.profileNote)); }
    }
    const anniversary = document.getElementById('anniversary');
    if (anniversary && /^\d{4}-\d{2}-\d{2}$/.test(content.anniversary || '')) {
      anniversary.dateTime = content.anniversary;
      anniversary.textContent = content.anniversary.split('-').reverse().join('/');
    }
    Object.entries(data.profiles || {}).forEach(([id, profile]) => {
      const trigger = Array.from(document.querySelectorAll('.profile[data-profile]')).find((node) => node.dataset.profile === id);
      if (!trigger || !profile || typeof profile !== 'object') return;
      const label = trigger.querySelector('.name');
      if (label && typeof profile.displayName === 'string') label.textContent = profile.displayName;
      if (typeof profile.name === 'string') trigger.setAttribute('aria-label', `Xem thông tin về ${profile.name}`);
      const avatar = trigger.querySelector('.avt');
      const source = asset(profile.avatar);
      if (avatar && source) { avatar.src = source; avatar.alt = `Ảnh đại diện của ${profile.name || profile.displayName || ''}`; }
    });
    const audio = document.getElementById('love-audio');
    const music = asset(content.musicSrc);
    if (audio && music && audio.src !== music) { audio.pause(); audio.src = music; audio.load(); }
    if (typeof content.backgroundImage === 'string') {
      const background = asset(content.backgroundImage);
      if (background) {
        document.body.style.backgroundImage = `linear-gradient(#fff4f6e8, #fff4f6e8), url(${JSON.stringify(background)})`;
        document.body.style.backgroundSize = 'cover';
        document.body.style.backgroundPosition = 'center';
      } else {
        ['background-image', 'background-size', 'background-position'].forEach((property) => document.body.style.removeProperty(property));
      }
    }
    const description = document.querySelector('meta[name="description"]');
    if (description && typeof content.introduction === 'string') description.content = content.introduction;
    document.dispatchEvent(new CustomEvent('lovedays:site-updated', { detail: data }));
  }

  async function refresh() {
    controller?.abort();
    const request = new AbortController();
    controller = request;
    try {
      const response = await fetch(url('api/site'), { credentials: 'same-origin', cache: 'no-store', signal: request.signal });
      if (!response.ok) return null;
      const data = await response.json();
      if (controller !== request) return null;
      lastRefresh = Date.now();
      apply(data);
      return data;
    } catch (_) { return null; }
    finally { if (controller === request) controller = null; }
  }
  window.LoveDaysSite = { refresh, apply, get data() { return current; } };
  document.addEventListener('visibilitychange', () => { if (!document.hidden && Date.now() - lastRefresh > 30000) refresh(); });
  function initialize() {
    const bootstrap = document.getElementById('site-public-config');
    if (bootstrap) {
      try { apply(JSON.parse(bootstrap.textContent)); } catch (_) { /* Keep the basic HTML if bootstrap data is unavailable. */ }
    }
    refresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else initialize();
})();
