(() => {
  'use strict';

  // Thay đổi số lần nhấn / thời gian tại đây. Mật khẩu chỉ được kiểm tra ở máy chủ.
  const SECRET_CONFIG = Object.freeze({ clicks: 7, windowMs: 2000, maxImages: 5, maxImageBytes: 5 * 1024 * 1024 });
  const LETTER_TYPES = Object.freeze({ diary: 'Nhật ký', 'love-letter': 'Thư tình', message: 'Lời nhắn' });
  const DEFAULT_PEOPLE = [{ id: 'tuan', name: 'Lê Anh Tuấn' }, { id: 'thu', name: 'Lê Phạm Anh Thư' }];

  function initializeLetters() {
    const heart = document.getElementById('heart');
    const column = document.querySelector('.heart-column');
    if (!heart || !column || typeof HTMLDialogElement === 'undefined') return;

    // Chỉ mẫu tĩnh dùng HTML. Tất cả dữ liệu thư / tên / tên tệp dùng textContent.
    const template = document.createElement('template');
    template.innerHTML = `
      <dialog id="secret-dialog" class="secret-dialog" aria-labelledby="secret-heading">
        <div class="secret-shell">
          <button id="secret-close" class="secret-close" type="button" aria-label="Đóng hộp thư"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>
          <section id="secret-gate" class="secret-gate">
            <div id="secret-envelope" class="secret-envelope" aria-hidden="true"><div class="secret-envelope-paper"><span>♡</span><i></i><i></i><i></i></div><div class="secret-envelope-pocket"></div><div class="secret-envelope-flap"></div><span class="secret-envelope-seal">♥</span></div>
            <p class="secret-eyebrow">Chỉ riêng chúng mình</p><h2 id="secret-heading">Hộp thư bí mật</h2>
            <p class="secret-gate-description">Có những điều chỉ muốn gửi đến một người.</p>
            <form id="secret-auth" class="secret-auth">
              <label for="secret-password">Mật khẩu của chúng mình</label>
              <div class="secret-password-row"><input id="secret-password" name="password" type="password" autocomplete="current-password" required maxlength="256" aria-describedby="secret-auth-status"><button id="secret-auth-submit" class="secret-button" type="submit">Mở thư <span aria-hidden="true">♡</span></button></div>
            </form>
            <p id="secret-auth-status" class="secret-feedback" role="status" aria-live="polite" aria-atomic="true"></p>
          </section>
          <section id="secret-workspace" class="secret-workspace" aria-label="Những lá thư của chúng mình" hidden>
            <header class="secret-workspace-header"><div><p class="secret-eyebrow">Một nơi để giữ yêu thương</p><h2 id="secret-workspace-title">Thư của chúng mình</h2></div><button id="secret-logout" class="secret-text-button" type="button">Khóa hộp thư</button></header>
            <p class="secret-access-note">Những người biết mật khẩu có chung quyền đọc, sửa và xóa thư.</p>
            <div class="secret-toolbar"><label class="secret-filter-label" for="secret-filter">Gửi đến <select id="secret-filter"><option value="">Tất cả</option></select></label><button id="secret-new" class="secret-button" type="button"><span aria-hidden="true">＋</span> Viết thư</button></div>
            <div class="secret-columns">
              <aside class="secret-sidebar" aria-label="Danh sách thư"><p id="secret-list-summary" class="secret-list-summary"></p><div id="secret-list" class="secret-list"></div></aside>
              <section id="secret-reading" class="secret-reading" aria-label="Nội dung thư"></section>
              <section id="secret-compose" class="secret-compose" aria-labelledby="secret-compose-title" hidden>
                <h3 id="secret-compose-title">Viết một lá thư</h3>
                <form id="secret-compose-form">
                  <fieldset id="secret-compose-fields" class="secret-compose-fields">
                    <div class="secret-form-grid"><label>Người viết<select id="secret-sender" required></select></label><label>Người nhận<select id="secret-recipient" required></select></label></div>
                    <label>Tên người viết<input id="secret-sender-name" name="senderName" required maxlength="80" autocomplete="off"></label>
                    <label>Loại thư<select id="secret-type" required><option value="diary">Nhật ký</option><option value="love-letter">Thư tình</option><option value="message">Lời nhắn</option></select></label>
                    <label>Tiêu đề<input id="secret-title" name="title" required maxlength="160" placeholder="Một điều muốn gửi đến bạn…" autocomplete="off"></label>
                    <label>Nội dung<textarea id="secret-content" name="content" rows="9" required maxlength="20000" placeholder="Viết từ những điều thật lòng…"></textarea></label>
                    <p id="secret-content-count" class="secret-field-hint"></p>
                    <label class="secret-upload-label" for="secret-images"><span aria-hidden="true">＋</span> Thêm ảnh đính kèm<input id="secret-images" type="file" accept="image/jpeg,image/png,image/webp" multiple></label>
                    <p id="secret-image-hint" class="secret-field-hint"></p><div id="secret-previews" class="secret-previews"></div>
                  </fieldset>
                  <div id="secret-conflict" class="secret-conflict" hidden><p>Lá thư đã được sửa ở nơi khác. Bản nháp của bạn vẫn được giữ. Đọc bản mới trước khi chọn dùng nội dung nháp.</p><div><button id="secret-conflict-review" class="secret-text-button" type="button">Đọc phiên bản mới</button><button id="secret-conflict-apply" class="secret-text-button" type="button" disabled>Dùng nháp trên bản mới</button></div></div>
                  <div class="secret-form-actions"><button id="secret-discard" class="secret-text-button" type="button">Bỏ bản nháp</button><button id="secret-save" class="secret-button" type="submit">Gửi lá thư <span aria-hidden="true">♡</span></button></div>
                </form>
              </section>
            </div>
            <p id="secret-workspace-status" class="secret-feedback" role="status" aria-live="polite" aria-atomic="true"></p>
          </section>
        </div>
      </dialog>
      <dialog id="secret-lightbox" class="secret-lightbox" aria-label="Xem ảnh đính kèm"><button id="secret-lightbox-close" class="secret-close" type="button" aria-label="Đóng ảnh"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button><img id="secret-lightbox-image" alt=""><p id="secret-lightbox-status" role="status" aria-live="polite" aria-atomic="true"></p></dialog>
      <p id="secret-toast" class="secret-toast" role="status" aria-live="polite" aria-atomic="true" hidden></p>`;
    document.body.append(template.content);
    const byId = (id) => document.getElementById(`secret-${id}`);
    const dialog = byId('dialog');
    const gate = byId('gate');
    const workspace = byId('workspace');
    const password = byId('password');
    const authForm = byId('auth');
    const authSubmit = byId('auth-submit');
    const authStatus = byId('auth-status');
    const status = byId('workspace-status');
    const closeButton = byId('close');
    const list = byId('list');
    const reader = byId('reading');
    const compose = byId('compose');
    const composeForm = byId('compose-form');
    const fields = byId('compose-fields');
    const filter = byId('filter');
    const sender = byId('sender');
    const senderName = byId('sender-name');
    const recipient = byId('recipient');
    const type = byId('type');
    const title = byId('title');
    const content = byId('content');
    const images = byId('images');
    const previews = byId('previews');
    const saveButton = byId('save');
    const newButton = byId('new');
    const logoutButton = byId('logout');
    const lightbox = byId('lightbox');
    const lightboxImage = byId('lightbox-image');
    const lightboxStatus = byId('lightbox-status');
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const state = { open: false, authenticated: false, csrf: '', people: DEFAULT_PEOPLE, limits: { ...SECRET_CONFIG, maxTitleLength: 160, maxContentLength: 20000, maxNameLength: 80 }, letters: [], selected: null, draft: null, conflictLatest: null, view: 'read', saving: false, deleting: false, authenticating: false, lockUntil: 0 };
    let generation = 0;
    let detailGeneration = 0;
    let controller = null;
    let scrollState = null;
    let lockTimer = null;
    let toastTimer = null;
    let imageKey = 0;
    let previewUrls = [];
    let lightboxTrigger = null;
    let activeTrigger = null;
    let sessionTimer = null;
    let sessionLoading = false;
    let sessionRequestGeneration = 0;
    let requestsInFlight = 0;
    let lastSessionCheck = 0;
    let tapCount = 0;
    let tapStarted = 0;
    let tapTimer = null;
    let forwarding = false;
    let passwordShakeTimer = null;

    const element = (tag, className, text) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = String(text);
      return node;
    };
    const button = (label, className, action) => {
      const node = element('button', className, label);
      node.type = 'button';
      node.addEventListener('click', action);
      return node;
    };
    const alive = (token) => token === generation && state.open && dialog.open;
    const cancelled = (error) => error?.name === 'AbortError';
    const delay = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
    const formatDate = (value) => {
      const date = new Date(value);
      return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh' }).format(date) : '';
    };
    const imageUrl = (image) => `/api/images/${encodeURIComponent(image.id)}`;
    const personName = (id) => state.people.find((person) => person.id === id)?.name || '';
    const mutationBusy = () => state.saving || state.deleting;

    function announce(message, error = false, target = status) {
      target.textContent = message;
      target.classList.toggle('is-error', error);
    }

    async function request(path, options = {}) {
      const method = options.method || 'GET';
      const headers = new Headers(options.headers || {});
      if (method !== 'GET') headers.set('X-CSRF-Token', state.csrf);
      if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
      requestsInFlight += 1;
      try {
        const response = await fetch(path, { ...options, method, headers, credentials: 'same-origin', cache: 'no-store', signal: controller?.signal });
        let data;
        try { data = await response.json(); } catch (_) { data = {}; }
        if (!response.ok) {
          const error = new Error(data.message || (response.status === 503 ? 'Hộp thư chưa được cấu hình trên máy chủ.' : 'Chưa kết nối được với hộp thư. Vui lòng thử lại.'));
          error.status = response.status;
          error.data = data;
          throw error;
        }
        return data;
      } finally { requestsInFlight = Math.max(0, requestsInFlight - 1); }
    }

    function lockScroll() {
      const body = document.body;
      const properties = ['position', 'top', 'left', 'width', 'padding-right'];
      const scrollbarWidth = Math.max(0, window.innerWidth - document.documentElement.clientWidth);
      const padding = Number.parseFloat(window.getComputedStyle(body).paddingRight) || 0;
      scrollState = { x: window.scrollX, y: window.scrollY, styles: properties.map((key) => [key, body.style.getPropertyValue(key), body.style.getPropertyPriority(key)]) };
      body.classList.add('dialog-open');
      body.style.position = 'fixed';
      body.style.top = `${-scrollState.y}px`;
      body.style.left = `${-scrollState.x}px`;
      body.style.width = '100%';
      if (scrollbarWidth) body.style.paddingRight = `${padding + scrollbarWidth}px`;
    }

    function unlockScroll() {
      if (!scrollState) return;
      const saved = scrollState;
      scrollState = null;
      document.body.classList.remove('dialog-open');
      saved.styles.forEach(([key, value, priority]) => value ? document.body.style.setProperty(key, value, priority) : document.body.style.removeProperty(key));
      const root = document.documentElement;
      const behavior = root.style.getPropertyValue('scroll-behavior');
      const priority = root.style.getPropertyPriority('scroll-behavior');
      root.style.setProperty('scroll-behavior', 'auto', 'important');
      window.scrollTo({ left: saved.x, top: saved.y, behavior: 'instant' });
      if (behavior) root.style.setProperty('scroll-behavior', behavior, priority);
      else root.style.removeProperty('scroll-behavior');
    }

    function trapFocus(event) {
      if (event.key !== 'Tab') return;
      const modal = event.currentTarget;
      const nodes = Array.from(modal.querySelectorAll('a[href], button, input, select, textarea, [tabindex]'))
        .filter((node) => node.tabIndex >= 0 && !node.matches(':disabled') && !node.closest('[hidden], [inert]') && node.getClientRects().length && !['hidden', 'collapse'].includes(window.getComputedStyle(node).visibility))
        .sort((a, b) => (a.tabIndex || Infinity) - (b.tabIndex || Infinity));
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (!first) { event.preventDefault(); modal.focus({ preventScroll: true }); }
      else if (event.shiftKey && (document.activeElement === first || !nodes.includes(document.activeElement))) { event.preventDefault(); last.focus({ preventScroll: true }); }
      else if (!event.shiftKey && (document.activeElement === last || !nodes.includes(document.activeElement))) { event.preventDefault(); first.focus({ preventScroll: true }); }
    }

    function revokePreviews() {
      previewUrls.forEach((url) => URL.revokeObjectURL(url));
      previewUrls = [];
      state.draft?.files.forEach((entry) => { entry.url = null; });
    }

    function clearPrivateDOM() {
      if (lightbox.open) lightbox.close();
      lightboxImage.removeAttribute('src');
      lightboxStatus.textContent = '';
      state.letters = [];
      state.selected = null;
      state.conflictLatest = null;
      state.view = 'read';
      list.replaceChildren();
      reader.replaceChildren();
      previews.replaceChildren();
      composeForm.reset();
      compose.hidden = true;
      byId('conflict').hidden = true;
      workspace.hidden = true;
      byId('list-summary').textContent = '';
      announce('');
      if (state.draft && !state.draft.dirty) clearDraft();
    }

    function showGate(message = '', error = false) {
      state.authenticated = false;
      window.clearTimeout(sessionTimer);
      clearPrivateDOM();
      gate.hidden = false;
      gate.classList.remove('is-unlocking');
      dialog.classList.remove('is-workspace');
      dialog.setAttribute('aria-labelledby', 'secret-heading');
      announce(message, error, authStatus);
    }

    function syncSession(data) {
      state.authenticated = data.authenticated === true;
      state.csrf = typeof data.csrfToken === 'string' ? data.csrfToken : '';
      if (Array.isArray(data.people) && data.people.length) state.people = data.people.filter((person) => typeof person.id === 'string' && typeof person.name === 'string');
      if (!state.people.length) state.people = DEFAULT_PEOPLE;
      const limits = data.limits || {};
      ['maxImages', 'maxImageBytes', 'maxTitleLength', 'maxContentLength', 'maxNameLength'].forEach((key) => {
        if (Number.isFinite(limits[key]) && limits[key] > 0) state.limits[key] = limits[key];
      });
      state.lockUntil = Number(data.retryAfter) > 0 ? Date.now() + Number(data.retryAfter) * 1000 : 0;
      title.maxLength = state.limits.maxTitleLength;
      content.maxLength = state.limits.maxContentLength;
      senderName.maxLength = state.limits.maxNameLength;
      byId('image-hint').textContent = `Tối đa ${state.limits.maxImages} ảnh JPEG, PNG hoặc WebP; mỗi ảnh tối đa ${Math.round(state.limits.maxImageBytes / 1048576)} MB.`;
      scheduleSessionExpiry(data);
    }

    function scheduleSessionExpiry(data) {
      window.clearTimeout(sessionTimer);
      sessionTimer = null;
      if (!state.authenticated) return;
      const date = Date.parse(data.expiresAt);
      const remaining = Number.isFinite(date) ? date - Date.now() : Number(data.expiresIn) * 1000;
      if (!Number.isFinite(remaining)) return;
      const expire = () => {
        if (!state.open || !state.authenticated) return;
        if (mutationBusy() || sessionLoading || requestsInFlight) { sessionTimer = window.setTimeout(expire, 250); return; }
        loadSession(generation, true);
      };
      sessionTimer = window.setTimeout(expire, Math.max(0, Math.min(remaining + 100, 2147483647)));
    }

    function updateGateControls() {
      const remaining = Math.max(0, Math.ceil((state.lockUntil - Date.now()) / 1000));
      password.disabled = state.authenticating || remaining > 0 || !state.csrf;
      authSubmit.disabled = password.disabled;
      authSubmit.textContent = state.authenticating ? 'Đang mở…' : 'Mở thư ♡';
      if (remaining) announce(`Hộp thư đang tạm khóa. Thử lại sau ${remaining} giây.`, true, authStatus);
      else if (lockTimer !== null) {
        window.clearInterval(lockTimer);
        lockTimer = null;
        announce('Bạn có thể nhập lại mật khẩu.', false, authStatus);
      }
    }

    function startLockCountdown() {
      if (lockTimer !== null) window.clearInterval(lockTimer);
      lockTimer = null;
      updateGateControls();
      if (state.lockUntil > Date.now()) lockTimer = window.setInterval(updateGateControls, 1000);
    }

    async function loadSession(token, expired = false) {
      if (sessionLoading) return;
      sessionLoading = true;
      const sessionToken = ++sessionRequestGeneration;
      lastSessionCheck = Date.now();
      showGate(expired ? 'Phiên đã hết hạn. Nhập lại mật khẩu để tiếp tục; bản nháp vẫn được giữ trong phiên này.' : 'Đang mở cánh thư…');
      state.csrf = '';
      updateGateControls();
      try {
        const data = await request('/api/session');
        if (!alive(token) || sessionToken !== sessionRequestGeneration) return;
        if (sessionToken === sessionRequestGeneration) sessionLoading = false;
        syncSession(data);
        if (state.authenticated) await enterWorkspace(token);
        else {
          announce(expired ? 'Phiên đã hết hạn. Nhập lại mật khẩu để tiếp tục; bản nháp vẫn được giữ trong phiên này.' : 'Nhập mật khẩu để mở những điều dành riêng cho chúng mình.', false, authStatus);
          startLockCountdown();
          if (!password.disabled) password.focus({ preventScroll: true });
        }
      } catch (error) {
        if (alive(token) && !cancelled(error)) {
          announce(error.message, true, authStatus);
          updateGateControls();
        }
      } finally { if (sessionToken === sessionRequestGeneration) sessionLoading = false; }
    }

    async function verifySession() {
      if (!state.open || !state.authenticated || sessionLoading || requestsInFlight || state.authenticating || mutationBusy() || Date.now() - lastSessionCheck < 1000) return;
      sessionLoading = true;
      const sessionToken = ++sessionRequestGeneration;
      lastSessionCheck = Date.now();
      const token = generation;
      try {
        const data = await request('/api/session');
        if (!alive(token) || sessionToken !== sessionRequestGeneration) return;
        if (sessionToken === sessionRequestGeneration) sessionLoading = false;
        syncSession(data);
        if (!state.authenticated) {
          showGate('Phiên đã hết hạn. Nhập lại mật khẩu để tiếp tục; bản nháp vẫn được giữ trong phiên này.');
          password.value = '';
          startLockCountdown();
          if (!password.disabled) password.focus({ preventScroll: true });
        } else if (workspace.hidden) await enterWorkspace(token);
      } catch (error) { if (alive(token) && !cancelled(error)) announce('Chưa kiểm tra lại được phiên làm việc. Vui lòng kiểm tra kết nối.', true); }
      finally { if (sessionToken === sessionRequestGeneration) sessionLoading = false; }
    }
    document.addEventListener('visibilitychange', () => { if (!document.hidden) verifySession(); });
    window.addEventListener('focus', verifySession);

    function toast(message) {
      const note = byId('toast');
      window.clearTimeout(toastTimer);
      note.textContent = message;
      note.hidden = false;
      toastTimer = window.setTimeout(() => { note.hidden = true; note.textContent = ''; }, 7000);
    }

    async function openDialog() {
      if (state.open || dialog.open || document.querySelector('dialog[open]')) return;
      state.open = true;
      state.authenticated = false;
      state.authenticating = false;
      state.csrf = '';
      generation += 1;
      const token = generation;
      controller = new AbortController();
      sessionLoading = false;
      sessionRequestGeneration += 1;
      activeTrigger = heart;
      authForm.reset();
      password.removeAttribute('aria-invalid');
      showGate();
      lockScroll();
      try { dialog.showModal(); } catch (_) { state.open = false; unlockScroll(); return; }
      closeButton.focus({ preventScroll: true });
      await loadSession(token);
    }

    function closeDialog(force = false) {
      if (mutationBusy() && !force) { announce('Đang lưu thay đổi. Chờ một chút trước khi đóng nhé.'); return; }
      if (!force && state.view === 'compose' && state.draft?.dirty && !window.confirm('Đóng hộp thư? Bản nháp được giữ tạm trong phiên này, đến khi tải lại trang.')) return;
      if (lightbox.open) lightbox.close();
      if (dialog.open) dialog.close();
    }

    dialog.addEventListener('close', () => {
      generation += 1;
      detailGeneration += 1;
      state.open = false;
      state.authenticated = false;
      state.authenticating = false;
      state.csrf = '';
      controller?.abort();
      controller = null;
      sessionLoading = false;
      sessionRequestGeneration += 1;
      window.clearTimeout(sessionTimer);
      sessionTimer = null;
      if (lockTimer !== null) window.clearInterval(lockTimer);
      lockTimer = null;
      authForm.reset();
      password.removeAttribute('aria-invalid');
      window.clearTimeout(passwordShakeTimer);
      password.closest('.secret-password-row').classList.remove('secret-auth-error');
      clearPrivateDOM();
      gate.hidden = false;
      gate.classList.remove('is-unlocking');
      dialog.classList.remove('is-workspace');
      unlockScroll();
      activeTrigger?.focus({ preventScroll: true });
      activeTrigger = null;
    });
    closeButton.addEventListener('click', () => closeDialog());
    dialog.addEventListener('cancel', (event) => { event.preventDefault(); closeDialog(); });
    dialog.addEventListener('keydown', trapFocus);
    lightbox.addEventListener('keydown', trapFocus);

    function bindBackdrop(modal, close) {
      let pointer = null;
      const outside = (event) => { const rect = modal.getBoundingClientRect(); return event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom; };
      modal.addEventListener('pointerdown', (event) => { pointer = event.button === 0 && outside(event) ? event.pointerId : null; });
      modal.addEventListener('pointerup', (event) => { const dismiss = pointer === event.pointerId && outside(event); pointer = null; if (dismiss) close(); });
      modal.addEventListener('pointercancel', () => { pointer = null; });
    }
    bindBackdrop(dialog, () => closeDialog());
    bindBackdrop(lightbox, () => lightbox.close());

    authForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!state.open || state.authenticating || state.lockUntil > Date.now() || !state.csrf || !authForm.reportValidity()) return;
      const token = generation;
      const entered = password.value;
      state.authenticating = true;
      updateGateControls();
      announce('Đang mở phong thư…', false, authStatus);
      try {
        const data = await request('/api/auth', { method: 'POST', body: JSON.stringify({ password: entered }) });
        if (!alive(token)) return;
        syncSession(data);
        password.value = '';
        password.removeAttribute('aria-invalid');
        if (!state.authenticated) throw new Error('Chưa mở được hộp thư. Vui lòng thử lại.');
        await enterWorkspace(token);
      } catch (error) {
        if (!alive(token) || cancelled(error)) return;
        password.value = '';
        if (error.data?.closePopup || error.status === 429) {
          const seconds = Math.max(1, Number(error.data?.retryAfter) || 60);
          state.lockUntil = Date.now() + seconds * 1000;
          closeDialog(true);
          toast(`Bạn đã nhập sai quá số lần cho phép. Hộp thư tạm khóa trong ${seconds} giây.`);
        } else if (error.status === 401) {
          password.setAttribute('aria-invalid', 'true');
          const row = password.closest('.secret-password-row');
          row.classList.remove('secret-auth-error');
          window.clearTimeout(passwordShakeTimer);
          if (!motion.matches) {
            void row.offsetWidth;
            row.classList.add('secret-auth-error');
            passwordShakeTimer = window.setTimeout(() => row.classList.remove('secret-auth-error'), 380);
          }
          const remaining = Number(error.data?.attemptsRemaining);
          announce(Number.isFinite(remaining) ? `Mật khẩu chưa đúng. Bạn còn ${remaining} lần thử.` : error.message, true, authStatus);
        } else if (error.status === 403) {
          await loadSession(token);
          if (alive(token) && !state.authenticated) announce('Phiên làm việc đã thay đổi. Hãy nhập lại mật khẩu.', true, authStatus);
        } else announce(error.message, true, authStatus);
      } finally {
        state.authenticating = false;
        if (alive(token)) { updateGateControls(); if (!state.authenticated && !password.disabled) password.focus({ preventScroll: true }); }
      }
    });
    password.addEventListener('input', () => password.removeAttribute('aria-invalid'));

    function fillPeople() {
      const previousFilter = filter.value;
      filter.replaceChildren(new Option('Tất cả', ''));
      sender.replaceChildren();
      recipient.replaceChildren();
      state.people.forEach((person) => {
        filter.append(new Option(person.name, person.id));
        sender.append(new Option(person.name, person.id));
        recipient.append(new Option(person.name, person.id));
      });
      filter.value = state.people.some((person) => person.id === previousFilter) ? previousFilter : '';
    }

    async function enterWorkspace(token) {
      if (!alive(token) || !state.authenticated) return;
      gate.classList.add('is-unlocking');
      announce('Phong thư đã mở…', false, authStatus);
      await delay(motion.matches ? 0 : 650);
      if (!alive(token) || !state.authenticated) return;
      gate.hidden = true;
      workspace.hidden = false;
      dialog.classList.add('is-workspace');
      dialog.setAttribute('aria-labelledby', 'secret-workspace-title');
      fillPeople();
      announce('Đang tìm những lá thư…');
      list.setAttribute('aria-busy', 'true');
      try {
        const data = await request('/api/letters');
        if (!alive(token) || !state.authenticated) return;
        state.letters = Array.isArray(data.letters) ? data.letters : [];
        sortLetters();
        renderList();
        announce('');
        if (state.draft) showCompose();
        else renderEmpty();
        (state.draft ? title : newButton).focus({ preventScroll: true });
      } catch (error) { await handlePrivateError(error, token); }
      finally { if (alive(token)) list.removeAttribute('aria-busy'); }
    }

    async function handlePrivateError(error, token) {
      if (!alive(token) || cancelled(error)) return;
      if (error.status === 401 || error.status === 403) {
        state.saving = false;
        state.deleting = false;
        setBusy(false);
        password.value = '';
        await loadSession(token, true);
      } else if (error.status === 409 && state.draft?.id) {
        state.draft.conflicted = true;
        byId('conflict').hidden = false;
        byId('conflict-apply').disabled = true;
        announce(error.message || 'Đã có phiên bản mới. Bản nháp vẫn được giữ để bạn đối chiếu.', true);
      } else announce(error.message || 'Chưa thực hiện được. Bản nháp vẫn được giữ để bạn thử lại.', true);
    }

    function sortLetters() {
      state.letters.sort((a, b) => (Date.parse(b.createdAt) || 0) - (Date.parse(a.createdAt) || 0));
    }

    function renderList() {
      list.replaceChildren();
      const letters = state.letters.filter((letter) => !filter.value || letter.recipientId === filter.value);
      byId('list-summary').textContent = `${letters.length} lá thư${filter.value ? ` gửi đến ${personName(filter.value)}` : ' được giữ ở đây'}`;
      if (!letters.length) list.append(element('p', 'secret-list-empty', 'Một khoảng giấy trắng, chờ những điều muốn kể.'));
      letters.forEach((letter) => {
        const row = button('', 'secret-letter-row', () => { if (!mutationBusy()) openLetter(letter.id); });
        row.dataset.letterId = letter.id;
        row.setAttribute('aria-pressed', String(state.selected?.id === letter.id));
        if (Array.isArray(letter.images) && letter.images[0]) {
          const cover = element('img', 'secret-letter-cover');
          cover.loading = 'lazy';
          cover.alt = '';
          cover.src = imageUrl(letter.images[0]);
          cover.addEventListener('error', () => { cover.hidden = true; }, { once: true });
          row.append(cover);
        }
        row.append(element('span', 'secret-type-badge', LETTER_TYPES[letter.type] || 'Lá thư'));
        row.append(element('strong', 'secret-letter-title', letter.title));
        row.append(element('span', 'secret-letter-route', `${letter.senderName} → ${letter.recipientName}`));
        row.append(element('span', 'secret-letter-excerpt', String(letter.content || '').replace(/\s+/g, ' ').slice(0, 90)));
        row.append(element('time', 'secret-letter-time', formatDate(letter.createdAt)));
        row.disabled = mutationBusy();
        list.append(row);
      });
      newButton.textContent = state.draft ? 'Viết tiếp bản nháp' : '＋ Viết thư';
    }

    function renderEmpty() {
      state.view = 'read';
      reader.hidden = false;
      compose.hidden = true;
      reader.replaceChildren();
      const empty = element('div', 'secret-reading-empty');
      empty.append(element('span', 'secret-empty-heart', '♡'), element('h3', '', 'Mỗi lá thư, một chút thương.'), element('p', '', 'Chọn một lá thư để đọc, hoặc viết điều bạn đang nghĩ đến.'));
      reader.append(empty);
    }

    async function openLetter(id) {
      if (!state.authenticated || mutationBusy()) return;
      const token = generation;
      const detailToken = ++detailGeneration;
      announce('Đang mở lá thư…');
      try {
        const data = await request(`/api/letters/${encodeURIComponent(id)}`);
        if (!alive(token) || detailToken !== detailGeneration || !state.authenticated) return;
        if (!data.letter) throw new Error('Không tìm thấy lá thư này.');
        if (state.draft?.id === data.letter.id && state.draft.updatedAt !== data.letter.updatedAt) state.conflictLatest = data.letter;
        renderDetail(data.letter);
        announce('');
      } catch (error) { if (detailToken === detailGeneration) await handlePrivateError(error, token); }
    }

    function renderDetail(letter) {
      state.selected = letter;
      state.view = 'read';
      compose.hidden = true;
      reader.hidden = false;
      reader.replaceChildren();
      const top = element('div', 'secret-reading-top');
      top.append(element('span', 'secret-type-badge', LETTER_TYPES[letter.type] || 'Lá thư'));
      const actions = element('div', 'secret-letter-actions');
      actions.append(button('Sửa thư', 'secret-text-button', () => startCompose(letter)), button('Xóa', 'secret-text-button secret-danger', () => deleteLetter(letter)));
      top.append(actions);
      const heading = element('h3', 'secret-reading-title', letter.title);
      heading.tabIndex = -1;
      const back = button('← Quay lại danh sách', 'secret-text-button secret-back', () => {
        renderEmpty();
        const target = list.querySelector(`[data-letter-id="${CSS.escape(String(letter.id))}"]`) || newButton;
        target.focus();
        list.scrollIntoView({ block: 'nearest', behavior: motion.matches ? 'instant' : 'smooth' });
      });
      reader.append(back, top, heading, element('p', 'secret-reading-route', `Từ ${letter.senderName}, gửi ${letter.recipientName}`));
      reader.append(element('p', 'secret-reading-date', `${formatDate(letter.createdAt)}${letter.updatedAt && letter.updatedAt !== letter.createdAt ? ` · Đã sửa ${formatDate(letter.updatedAt)}` : ''}`));
      reader.append(element('div', 'secret-letter-content', letter.content));
      if (Array.isArray(letter.images) && letter.images.length) {
        const gallery = element('div', 'secret-gallery');
        letter.images.forEach((image, index) => {
          const item = button('', 'secret-gallery-item', () => openLightbox(image, item));
          item.setAttribute('aria-label', `Xem ảnh ${index + 1}: ${image.alt || image.originalName || 'Ảnh đính kèm'}`);
          const img = element('img');
          item.classList.add('is-loading');
          item.setAttribute('aria-busy', 'true');
          img.loading = 'lazy';
          img.alt = image.alt || image.originalName || `Ảnh đính kèm ${index + 1}`;
          img.src = imageUrl(image);
          img.addEventListener('load', () => { item.classList.remove('is-loading'); item.removeAttribute('aria-busy'); }, { once: true });
          img.addEventListener('error', () => { img.hidden = true; item.classList.remove('is-loading'); item.removeAttribute('aria-busy'); item.classList.add('is-error'); item.append(element('span', 'secret-image-error', 'Chưa tải được ảnh. Nhấn để thử lại.')); }, { once: true });
          item.append(img);
          gallery.append(item);
        });
        reader.append(gallery);
      }
      renderList();
      heading.focus({ preventScroll: true });
      reader.scrollIntoView({ block: 'nearest', behavior: motion.matches ? 'instant' : 'smooth' });
    }

    function openLightbox(image, trigger) {
      if (!state.authenticated || lightbox.open) return;
      lightboxTrigger = trigger;
      lightboxImage.hidden = false;
      lightboxImage.alt = image.alt || image.originalName || 'Ảnh đính kèm';
      lightboxStatus.textContent = 'Đang tải ảnh…';
      lightboxImage.onload = () => { if (lightbox.open) lightboxStatus.textContent = ''; };
      lightboxImage.onerror = () => { if (lightbox.open) { lightboxImage.hidden = true; lightboxStatus.textContent = 'Chưa tải được ảnh. Hãy đóng rồi mở lại để thử lại.'; } };
      lightboxImage.src = imageUrl(image);
      lightbox.showModal();
      byId('lightbox-close').focus({ preventScroll: true });
    }
    byId('lightbox-close').addEventListener('click', () => lightbox.close());
    lightbox.addEventListener('close', () => {
      lightboxImage.removeAttribute('src');
      lightboxImage.onload = null;
      lightboxImage.onerror = null;
      lightboxStatus.textContent = '';
      if (lightboxTrigger?.isConnected && dialog.open) lightboxTrigger.focus({ preventScroll: true });
      lightboxTrigger = null;
    });

    async function deleteLetter(letter) {
      if (mutationBusy() || !state.authenticated || !window.confirm(`Xóa vĩnh viễn lá thư “${letter.title}” và ảnh đính kèm?`)) return;
      const token = generation;
      state.deleting = true;
      setBusy(true);
      announce('Đang xóa lá thư…');
      try {
        await request(`/api/letters/${encodeURIComponent(letter.id)}`, { method: 'DELETE' });
        if (!alive(token)) return;
        state.letters = state.letters.filter((entry) => entry.id !== letter.id);
        if (state.draft?.id === letter.id) clearDraft();
        state.selected = null;
        renderList();
        renderEmpty();
        announce('Đã xóa lá thư và ảnh đính kèm.');
      } catch (error) { await handlePrivateError(error, token); }
      finally { state.deleting = false; if (alive(token)) setBusy(false); }
    }

    function startCompose(letter = null) {
      if (!state.authenticated || mutationBusy()) return;
      if (state.draft && state.draft.id !== (letter?.id || null)) {
        if (state.draft.dirty && !window.confirm('Bạn đang có một bản nháp. Bỏ bản nháp đó để sửa lá thư này?')) return;
        clearDraft();
      }
      if (!state.draft) state.draft = {
        id: letter?.id || null,
        updatedAt: letter?.updatedAt || null,
        senderId: letter?.senderId || state.people[0].id,
        senderName: letter?.senderName || state.people[0].name,
        recipientId: letter?.recipientId || state.people[Math.min(1, state.people.length - 1)].id,
        type: letter?.type || 'love-letter',
        title: letter?.title || '',
        content: letter?.content || '',
        keepImages: Array.isArray(letter?.images) ? [...letter.images] : [],
        files: [],
        dirty: false
      };
      showCompose();
      title.focus({ preventScroll: true });
    }

    function showCompose() {
      const draft = state.draft;
      if (!draft) return;
      detailGeneration += 1;
      state.view = 'compose';
      compose.hidden = false;
      reader.hidden = true;
      sender.value = draft.senderId;
      senderName.value = draft.senderName;
      recipient.value = draft.recipientId;
      type.value = draft.type;
      title.value = draft.title;
      content.value = draft.content;
      byId('compose-title').textContent = draft.id ? 'Viết tiếp lá thư' : 'Viết một lá thư';
      saveButton.textContent = draft.id ? 'Lưu thay đổi ♡' : 'Gửi lá thư ♡';
      fields.disabled = false;
      renderPreviews();
      updateContentCount();
      renderList();
      announce(draft.dirty ? 'Bản nháp được giữ tạm trong phiên này. Hãy lưu trước khi tải lại trang.' : '');
      byId('conflict').hidden = !draft.conflicted;
      byId('conflict-apply').disabled = !state.conflictLatest;
      compose.scrollIntoView({ block: 'nearest', behavior: motion.matches ? 'instant' : 'smooth' });
    }

    function updateContentCount() {
      byId('content-count').textContent = `${content.value.length.toLocaleString('vi-VN')} / ${state.limits.maxContentLength.toLocaleString('vi-VN')} ký tự`;
    }

    composeForm.addEventListener('input', (event) => {
      if (!state.draft || state.saving) return;
      const mapping = new Map([[senderName, 'senderName'], [title, 'title'], [content, 'content']]);
      const key = mapping.get(event.target);
      if (key) { state.draft[key] = event.target.value; state.draft.dirty = true; }
      updateContentCount();
    });
    [sender, recipient, type].forEach((input) => input.addEventListener('change', () => {
      if (!state.draft || state.saving) return;
      state.draft.senderId = sender.value;
      state.draft.recipientId = recipient.value;
      state.draft.type = type.value;
      if (input === sender) { senderName.value = personName(sender.value); state.draft.senderName = senderName.value; }
      state.draft.dirty = true;
    }));

    function renderPreviews() {
      previews.replaceChildren();
      const draft = state.draft;
      if (!draft) return;
      const entries = [
        ...draft.keepImages.map((image) => ({ key: image.id, name: image.originalName || 'Ảnh đính kèm', url: imageUrl(image), retained: true })),
        ...draft.files.map((entry) => { if (!entry.url) { entry.url = URL.createObjectURL(entry.file); previewUrls.push(entry.url); } return { key: entry.key, name: entry.file.name, url: entry.url, retained: false }; })
      ];
      entries.forEach((entry) => {
        const item = element('figure', 'secret-preview');
        const img = element('img');
        img.alt = entry.name;
        img.src = entry.url;
        img.addEventListener('error', () => { img.hidden = true; item.prepend(element('span', 'secret-image-error', 'Không xem được ảnh')); }, { once: true });
        const remove = button('×', 'secret-preview-remove', () => {
          if (state.saving) return;
          if (entry.retained) draft.keepImages = draft.keepImages.filter((image) => image.id !== entry.key);
          else {
            const removed = draft.files.find((file) => file.key === entry.key);
            if (removed?.url) { URL.revokeObjectURL(removed.url); previewUrls = previewUrls.filter((url) => url !== removed.url); }
            draft.files = draft.files.filter((file) => file.key !== entry.key);
          }
          draft.dirty = true;
          renderPreviews();
        });
        remove.setAttribute('aria-label', `Bỏ ảnh ${entry.name}`);
        item.append(img, element('figcaption', '', entry.name), remove);
        previews.append(item);
      });
    }

    images.addEventListener('change', () => {
      if (!state.draft || state.saving) return;
      const draft = state.draft;
      const errors = [];
      let added = 0;
      Array.from(images.files || []).forEach((file) => {
        if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { errors.push(`${file.name}: chỉ nhận JPEG, PNG hoặc WebP.`); return; }
        if (!file.size || file.size > state.limits.maxImageBytes) { errors.push(`${file.name}: ảnh phải lớn hơn 0 byte và tối đa ${Math.round(state.limits.maxImageBytes / 1048576)} MB.`); return; }
        if (draft.keepImages.length + draft.files.length >= state.limits.maxImages) { errors.push(`Mỗi thư chỉ đính kèm tối đa ${state.limits.maxImages} ảnh.`); return; }
        draft.files.push({ key: `upload-${++imageKey}`, file });
        added += 1;
      });
      images.value = '';
      if (added) draft.dirty = true;
      renderPreviews();
      announce([...new Set(errors)].join(' ') || `Đã thêm ${added} ảnh vào bản nháp.`, errors.length > 0);
    });

    function clearDraft() {
      revokePreviews();
      state.draft = null;
      state.conflictLatest = null;
      byId('conflict').hidden = true;
      previews.replaceChildren();
      composeForm.reset();
    }

    byId('conflict-review').addEventListener('click', () => { if (state.draft?.id && !mutationBusy()) openLetter(state.draft.id); });
    byId('conflict-apply').addEventListener('click', () => {
      const draft = state.draft;
      const latest = state.conflictLatest;
      if (!draft || !latest || mutationBusy() || !window.confirm('Dùng nội dung bản nháp trên phiên bản vừa đọc? Khi lưu, nội dung và ảnh có thể thay thế các thay đổi ở nơi khác.')) return;
      draft.updatedAt = latest.updatedAt;
      draft.keepImages = draft.keepImages.filter((image) => latest.images.some((current) => current.id === image.id));
      draft.conflicted = false;
      draft.dirty = true;
      state.conflictLatest = null;
      byId('conflict').hidden = true;
      renderPreviews();
      announce('Đã dùng mốc phiên bản mới. Kiểm tra nội dung và ảnh trước khi bấm Lưu thay đổi.');
    });

    byId('discard').addEventListener('click', () => {
      if (mutationBusy() || !state.draft || (state.draft.dirty && !window.confirm('Bỏ các thay đổi và ảnh chưa lưu trong bản nháp này?'))) return;
      const previous = state.selected;
      clearDraft();
      if (previous) renderDetail(previous);
      else { renderEmpty(); renderList(); }
      announce('Đã bỏ bản nháp.');
    });

    function setBusy(busy) {
      fields.disabled = busy;
      saveButton.disabled = busy;
      byId('discard').disabled = busy;
      newButton.disabled = busy;
      logoutButton.disabled = busy;
      closeButton.disabled = busy;
      filter.disabled = busy;
      list.querySelectorAll('button').forEach((node) => { node.disabled = busy; });
      reader.querySelectorAll('.secret-letter-actions button').forEach((node) => { node.disabled = busy; });
      if (state.saving) saveButton.textContent = 'Đang lưu…';
      else saveButton.textContent = state.draft?.id ? 'Lưu thay đổi ♡' : 'Gửi lá thư ♡';
    }

    composeForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const draft = state.draft;
      if (!state.authenticated || mutationBusy() || !draft || !composeForm.reportValidity()) return;
      if (!draft.senderName.trim() || !draft.title.trim() || !draft.content.trim()) { announce('Hãy điền tên người viết, tiêu đề và nội dung thư.', true); return; }
      const token = generation;
      const payload = { senderId: draft.senderId, senderName: draft.senderName.trim(), recipientId: draft.recipientId, recipientName: personName(draft.recipientId), type: draft.type, title: draft.title.trim(), content: draft.content, keepImageIds: draft.keepImages.map((image) => image.id) };
      if (draft.updatedAt) payload.expectedUpdatedAt = draft.updatedAt;
      const form = new FormData();
      form.append('payload', JSON.stringify(payload));
      draft.files.forEach((entry) => form.append('images', entry.file, entry.file.name));
      state.saving = true;
      setBusy(true);
      announce('Đang giữ lại những điều bạn vừa viết…');
      try {
        const data = await request(draft.id ? `/api/letters/${encodeURIComponent(draft.id)}` : '/api/letters', { method: draft.id ? 'PUT' : 'POST', body: form });
        if (!alive(token) || !state.authenticated) return;
        if (!data.letter) throw new Error('Máy chủ chưa trả lại lá thư. Bản nháp vẫn được giữ.');
        state.letters = state.letters.filter((letter) => letter.id !== data.letter.id);
        state.letters.unshift(data.letter);
        sortLetters();
        clearDraft();
        renderDetail(data.letter);
        announce(draft.id ? 'Đã lưu những thay đổi trong lá thư.' : 'Lá thư đã được gửi và lưu lại.');
      } catch (error) { await handlePrivateError(error, token); }
      finally { state.saving = false; if (alive(token)) setBusy(false); }
    });

    newButton.addEventListener('click', () => { if (!state.authenticated || mutationBusy()) return; if (state.draft) { showCompose(); title.focus({ preventScroll: true }); } else startCompose(); });
    filter.addEventListener('change', renderList);
    logoutButton.addEventListener('click', async () => {
      if (mutationBusy() || !state.authenticated) return;
      if (state.draft?.dirty && !window.confirm('Khóa hộp thư? Bản nháp được giữ tạm trong phiên này, đến khi tải lại trang.')) return;
      const token = generation;
      sessionRequestGeneration += 1;
      sessionLoading = false;
      logoutButton.disabled = true;
      try {
        const data = await request('/api/logout', { method: 'POST', body: '{}' });
        if (!alive(token)) return;
        syncSession(data);
        password.value = '';
        showGate('Hộp thư đã được khóa.');
        updateGateControls();
        password.focus({ preventScroll: true });
      } catch (error) { await handlePrivateError(error, token); }
      finally { if (alive(token)) logoutButton.disabled = false; }
    });

    window.addEventListener('beforeunload', (event) => {
      if (state.draft?.dirty || state.saving) { event.preventDefault(); event.returnValue = ''; }
    });

    column.addEventListener('click', (event) => {
      if (forwarding || state.open || document.querySelector('dialog[open]')) return;
      if (!heart.contains(event.target)) {
        forwarding = true;
        try { heart.click(); } finally { forwarding = false; }
      }
      const now = performance.now();
      if (!tapCount || now - tapStarted > SECRET_CONFIG.windowMs) {
        tapCount = 0;
        tapStarted = now;
        window.clearTimeout(tapTimer);
        tapTimer = window.setTimeout(() => { tapCount = 0; tapStarted = 0; }, SECRET_CONFIG.windowMs);
      }
      tapCount += 1;
      if (tapCount < SECRET_CONFIG.clicks) return;
      tapCount = 0;
      tapStarted = 0;
      window.clearTimeout(tapTimer);
      column.classList.add('secret-heart-unlock');
      window.setTimeout(() => column.classList.remove('secret-heart-unlock'), 850);
      openDialog();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initializeLetters, { once: true });
  else initializeLetters();
})();
