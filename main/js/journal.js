(() => {
  'use strict';

  const PAGE_SIZE = 9;
  const appUrl = (path) => new URL(path.replace(/^\/+/, ''), new URL('.', document.baseURI)).href;
  const dateFormatter = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
  const dateText = (value) => { const date = new Date(value); return Number.isFinite(date.getTime()) ? dateFormatter.format(date).replace(', ', ' ') : ''; };
  const node = (tag, className, text) => { const item = document.createElement(tag); if (className) item.className = className; if (text !== undefined) item.textContent = String(text); return item; };
  const button = (text, className, action) => { const item = node('button', className, text); item.type = 'button'; if (action) item.addEventListener('click', action); return item; };
  const announce = (target, text, error = false) => { target.textContent = text; target.classList.toggle('is-error', error); };

  function initialize() {
    const card = document.querySelector('.love-card');
    if (!card || !window.HTMLDialogElement) return;
    const section = node('section', 'journal-section');
    section.id = 'journal';
    section.setAttribute('aria-labelledby', 'journal-heading');
    // Templates contain fixed interface text only. All server/user data uses textContent/value.
    section.innerHTML = `
      <header class="journal-header"><div><p class="eyebrow">NHỮNG ĐIỀU MÌNH MUỐN GIỮ</p><h2 id="journal-heading">Nhật ký &amp; Kỷ niệm <span aria-hidden="true">♡</span></h2><p class="journal-intro">Gom những ngày bình thường, thành câu chuyện của chúng mình.</p></div></header>
      <div class="journal-toolbar"><button type="button" class="journal-primary" id="journal-new">＋ Đăng nhật ký / kỷ niệm</button><button type="button" class="journal-text-button" id="journal-history">Lịch sử chỉnh sửa</button></div>
      <p class="journal-public-note">Bài đăng, ảnh và video trong phần này hiển thị công khai. Hãy giữ những điều riêng tư trong hộp thư bí mật.</p>
      <form id="journal-search" class="journal-search" role="search"><label class="journal-search-wide">Tìm một kỷ niệm<input name="q" type="search" placeholder="ID, tên người đăng, ngày, tiêu đề, nội dung…" maxlength="200"></label><label>Từ ngày<input name="from" type="date"></label><label>Đến ngày<input name="to" type="date"></label><button class="journal-secondary" type="submit">Tìm kiếm</button><button class="journal-text-button" type="reset">Xóa bộ lọc</button></form>
      <p id="journal-status" class="journal-status" role="status" aria-live="polite"></p><div id="journal-list" class="journal-list"></div><button id="journal-more" class="journal-secondary journal-more" type="button" hidden>Tải thêm kỷ niệm</button>`;
    card.after(section);

    const fragment = document.createElement('template');
    fragment.innerHTML = `
      <dialog id="journal-dialog" class="journal-dialog" aria-labelledby="journal-dialog-title"><div class="journal-modal-shell"><button class="journal-modal-close" type="button" aria-label="Đóng nhật ký" data-journal-close>×</button><p class="eyebrow">MỘT MẢNH TRONG CÂU CHUYỆN</p><h2 id="journal-dialog-title" tabindex="-1">Nhật ký của chúng mình</h2><div id="journal-dialog-body"></div><p id="journal-dialog-status" class="journal-status" role="status" aria-live="polite"></p></div></dialog>
      <dialog id="journal-history-dialog" class="journal-dialog" aria-labelledby="journal-history-title"><div class="journal-modal-shell"><button class="journal-modal-close" type="button" aria-label="Đóng lịch sử" data-journal-close>×</button><p class="eyebrow">NHỮNG LẦN CÂU CHUYỆN ĐỔI THAY</p><h2 id="journal-history-title">Lịch sử chỉnh sửa</h2><div id="journal-history-body"></div><p id="journal-history-status" class="journal-status" role="status" aria-live="polite"></p></div></dialog>
      <dialog id="journal-image-dialog" class="journal-dialog journal-lightbox" aria-label="Xem ảnh kỷ niệm"><button class="journal-modal-close" type="button" aria-label="Đóng ảnh" data-journal-close>×</button><img id="journal-large-image" alt=""><p id="journal-image-status" class="journal-status" role="status"></p></dialog>
      <dialog id="journal-map-dialog" class="journal-dialog journal-map-dialog" aria-labelledby="journal-map-title"><div class="journal-modal-shell"><button class="journal-modal-close" type="button" aria-label="Đóng lựa chọn bản đồ" data-journal-close>×</button><p class="eyebrow">NƠI MÌNH LƯU KỶ NIỆM</p><h2 id="journal-map-title">Mở địa điểm</h2><div id="journal-map-body"></div></div></dialog>
      <button id="admin-settings-toggle" class="admin-settings-toggle" type="button" aria-haspopup="dialog" aria-controls="admin-dialog" aria-label="Mở cài đặt quản trị" title="Cài đặt quản trị"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m9 3-.6 2a8 8 0 0 0-1.7 1L4.6 5.5l-2 3.5 1.5 1.5a8 8 0 0 0 0 2l-1.5 1.5 2 3.5 2.1-.5a8 8 0 0 0 1.7 1L9 21h4l.6-2a8 8 0 0 0 1.7-1l2.1.5 2-3.5-1.5-1.5a8 8 0 0 0 0-2L19.4 9l-2-3.5-2.1.5a8 8 0 0 0-1.7-1L13 3Z"/><circle cx="11" cy="12" r="3"/></svg></button>
      <dialog id="admin-dialog" class="journal-dialog admin-dialog" aria-labelledby="admin-title"><div class="journal-modal-shell"><button class="journal-modal-close" type="button" aria-label="Đóng cài đặt" data-journal-close>×</button><p class="eyebrow">CHĂM CHÚT CHO CHUYỆN CHÚNG MÌNH</p><h2 id="admin-title">Cài đặt quản trị</h2><div id="admin-body"></div><p id="admin-status" class="journal-status" role="status" aria-live="polite"></p></div></dialog>`;
    document.body.append(fragment.content);
    const get = (id) => document.getElementById(id);
    const list = get('journal-list');
    const search = get('journal-search');
    const listStatus = get('journal-status');
    const more = get('journal-more');
    const modal = get('journal-dialog');
    const modalBody = get('journal-dialog-body');
    const modalStatus = get('journal-dialog-status');
    const historyDialog = get('journal-history-dialog');
    const historyBody = get('journal-history-body');
    const historyStatus = get('journal-history-status');
    const imageDialog = get('journal-image-dialog');
    const mapDialog = get('journal-map-dialog');
    const adminDialog = get('admin-dialog');
    const adminBody = get('admin-body');
    const adminStatus = get('admin-status');
    const state = { csrf: '', posts: [], page: 0, hasMore: false, loading: false, listGeneration: 0, modalGeneration: 0, adminGeneration: 0, historyGeneration: 0, passwordConfigured: false, draft: null, saving: false, adminBusy: false, historyPage: 0, historyLoading: false };
    const dialogs = [modal, historyDialog, imageDialog, mapDialog, adminDialog];
    const opened = new Map();
    const adminAlive = (generation) => adminDialog.open && generation === state.adminGeneration;
    const historyAlive = (generation) => historyDialog.open && generation === state.historyGeneration;

    async function request(path, options = {}) {
      const method = options.method || 'GET';
      const headers = new Headers(options.headers || {});
      if (method !== 'GET') {
        // Mailbox login can rotate the browser CSRF token; get the current value before every write.
        const session = await request('/api/session');
        state.csrf = session.csrfToken || state.csrf;
        headers.set('X-CSRF-Token', state.csrf);
      }
      if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
      const response = await fetch(appUrl(path), { ...options, method, headers, credentials: 'same-origin', cache: 'no-store' });
      let data = {};
      try { data = await response.json(); } catch (_) { /* An upstream HTML error has no JSON payload. */ }
      if (data.csrfToken) state.csrf = data.csrfToken;
      if (!response.ok) {
        const error = new Error(data.message || (response.status === 404 ? 'Máy chủ chưa có chức năng này. Hãy cập nhật mã và Reload ứng dụng.' : 'Chưa xử lý được yêu cầu. Vui lòng thử lại.'));
        error.status = response.status;
        error.data = data;
        throw error;
      }
      return data;
    }

    function openDialog(dialog, allowStack = false) {
      if (dialog.open) return true;
      if (!allowStack && document.querySelector('dialog[open]')) return false;
      opened.set(dialog, document.activeElement);
      if (dialog === adminDialog) state.adminGeneration += 1;
      if (dialog === historyDialog) state.historyGeneration += 1;
      window.LoveDaysViewport.lock(dialog);
      try { dialog.showModal(); } catch (_) { opened.delete(dialog); window.LoveDaysViewport.unlock(dialog); return false; }
      dialog.querySelector('input:not([type="hidden"]), [data-journal-close]')?.focus({ preventScroll: true });
      window.LoveDaysViewport.refresh();
      return true;
    }

    function closeDialog(dialog) {
      const focused = document.activeElement;
      if (dialog.contains(focused) && focused.matches('input, textarea, select, [contenteditable]')) focused.blur();
      dialog.close();
    }

    dialogs.forEach((dialog) => {
      const close = () => {
        if ((dialog === modal && state.saving) || (dialog === adminDialog && state.adminBusy)) return;
        closeDialog(dialog);
      };
      dialog.querySelector('[data-journal-close]').addEventListener('click', close);
      dialog.addEventListener('cancel', (event) => { event.preventDefault(); close(); });
      dialog.addEventListener('keydown', (event) => {
        if (event.key !== 'Tab') return;
        const focusable = [...dialog.querySelectorAll('button,input,select,textarea,a[href],[tabindex]')].filter((item) => item.tabIndex >= 0 && !item.disabled && item.getClientRects().length && !item.closest('[hidden]'));
        const first = focusable[0]; const last = focusable[focusable.length - 1];
        if (!first) { event.preventDefault(); dialog.focus(); }
        else if (event.shiftKey && (document.activeElement === first || !focusable.includes(document.activeElement))) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || !focusable.includes(document.activeElement))) { event.preventDefault(); first.focus(); }
      });
      dialog.addEventListener('close', () => {
        if (dialog.open) return;
        dialog.querySelectorAll('video').forEach((video) => video.pause());
        // Closing drops private DOM immediately. Late results must match the next
        // opening's generation before they are allowed to render anything.
        dialog.querySelectorAll('input[type="password"]').forEach((input) => { input.value = ''; });
        if (dialog === modal) { state.modalGeneration += 1; modalBody.replaceChildren(); modalStatus.textContent = ''; }
        if (dialog === historyDialog) { state.historyGeneration += 1; state.historyLoading = false; historyBody.replaceChildren(); historyStatus.textContent = ''; }
        if (dialog === adminDialog) { state.adminGeneration += 1; adminBody.replaceChildren(); adminStatus.textContent = ''; }
        if (dialog === imageDialog) get('journal-large-image').removeAttribute('src');
        if (dialog === mapDialog) get('journal-map-body').replaceChildren();
        const trigger = opened.get(dialog);
        opened.delete(dialog);
        window.LoveDaysViewport.unlock(dialog);
        if (trigger?.isConnected && !trigger.disabled) trigger.focus({ preventScroll: true });
      });
    });

    function imageUrl(image) { return appUrl(`api/journal/images/${encodeURIComponent(image.id)}`); }
    function locationCredit(location) {
      const credit = node('p', 'journal-help journal-location-attribution');
      if (location?.source !== 'geoapify') return credit;
      if (location.attribution) credit.append(document.createTextNode(`${location.attribution} · `));
      const geoapify = node('a', '', 'Geoapify'); geoapify.href = 'https://www.geoapify.com/'; geoapify.target = '_blank'; geoapify.rel = 'noopener noreferrer';
      const osm = node('a', '', '© OpenStreetMap'); osm.href = 'https://www.openstreetmap.org/copyright'; osm.target = '_blank'; osm.rel = 'noopener noreferrer';
      credit.append(geoapify, document.createTextNode(' · '), osm); return credit;
    }
    function validCoordinates(location) {
      if (!location || location.latitude === null || location.longitude === null || location.latitude === '' || location.longitude === '' || location.latitude === undefined || location.longitude === undefined) return false;
      const lat = Number(location.latitude); const lon = Number(location.longitude);
      return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
    }
    function openLocation(location) {
      if (!openDialog(mapDialog, true)) return;
      const body = get('journal-map-body'); body.replaceChildren(node('p', 'journal-map-label', location.label || location.lookupAddress || 'Địa điểm kỷ niệm'));
      if (!validCoordinates(location)) { body.append(node('p', 'journal-help', 'Địa điểm này được nhập thủ công, chưa có tọa độ để mở chính xác trên bản đồ. Bạn có thể bổ sung tọa độ khi chỉnh sửa bài.')); return; }
      const coordinates = `${Number(location.latitude)},${Number(location.longitude)}`;
      const google = new URL('https://www.google.com/maps/search/'); google.searchParams.set('api', '1'); google.searchParams.set('query', coordinates);
      // Apple unified Maps URLs pin the original coordinate; the name is only a label.
      const apple = new URL('https://maps.apple.com/place'); apple.searchParams.set('coordinate', coordinates); if (location.label) apple.searchParams.set('name', location.label);
      const links = node('div', 'journal-map-actions');
      [['Mở bằng Google Maps', google], ['Mở bằng Apple Maps', apple]].forEach(([label, url]) => { const link = node('a', 'journal-secondary', label); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; links.append(link); });
      body.append(node('p', 'journal-help', `Tọa độ gốc: ${coordinates}`), links, node('p', 'journal-help', 'Liên kết mở ứng dụng bản đồ khi thiết bị hỗ trợ, hoặc mở bản web. Nếu Apple Maps trên thiết bị cũ chưa nhận liên kết, dùng lựa chọn tương thích bên dưới.'));
      const fallback = new URL('https://maps.apple.com/'); fallback.searchParams.set('ll', coordinates); fallback.searchParams.set('q', location.label || coordinates);
      const legacy = node('a', 'journal-text-button', 'Apple Maps cho thiết bị cũ'); legacy.href = fallback.href; legacy.target = '_blank'; legacy.rel = 'noopener noreferrer'; body.append(legacy);
    }
    function openImage(image) {
      if (!openDialog(imageDialog, true)) return;
      const img = get('journal-large-image'); const status = get('journal-image-status');
      img.alt = image.alt || image.originalName || 'Ảnh kỷ niệm';
      announce(status, 'Đang tải ảnh…');
      img.onload = () => announce(status, '');
      img.onerror = () => announce(status, 'Không tải được ảnh. Hãy đóng và thử lại.', true);
      img.src = imageUrl(image);
    }

    function imageNode(image, clickable = true) {
      if (image.kind === 'video' || image.mimeType?.startsWith('video/')) {
        const wrapper = node('div', 'journal-image-button journal-video-wrap'); const video = node('video', 'journal-video');
        video.controls = true; video.playsInline = true; video.preload = 'none'; video.setAttribute('aria-label', image.alt || image.originalName || 'Video kỷ niệm'); video.src = imageUrl(image);
        const status = node('span', 'journal-image-error'); status.hidden = true;
        const download = node('a', 'journal-text-button', 'Tải video gốc'); download.href = imageUrl(image); download.download = image.originalName || 'video-ky-niem'; download.hidden = true;
        video.addEventListener('error', () => { status.hidden = download.hidden = false; status.textContent = 'Không phát được video. Trình duyệt có thể chưa hỗ trợ codec của tệp này; bạn có thể tải tệp gốc.'; }); wrapper.append(video, status, download); return wrapper;
      }
      const wrapper = clickable ? button('', 'journal-image-button', () => openImage(image)) : node('div', 'journal-image-button');
      if (clickable) wrapper.setAttribute('aria-label', `Xem lớn ${image.alt || image.originalName || 'ảnh kỷ niệm'}`);
      const img = node('img');
      img.loading = 'lazy'; img.decoding = 'async'; img.alt = image.alt || image.originalName || 'Ảnh kỷ niệm';
      wrapper.classList.add('is-loading');
      img.addEventListener('load', () => wrapper.classList.remove('is-loading'), { once: true });
      img.addEventListener('error', () => { wrapper.classList.remove('is-loading'); img.hidden = true; wrapper.append(node('span', 'journal-image-error', 'Không tải được ảnh')); }, { once: true });
      img.src = imageUrl(image); wrapper.append(img); return wrapper;
    }

    function postCard(post) {
      const article = node('article', 'journal-card');
      if (post.images?.length) { const cover = imageNode(post.images[0], false); cover.classList.add('journal-cover'); article.append(cover); }
      const body = node('div', 'journal-card-body');
      body.append(node('p', 'journal-card-date', dateText(post.createdAt)), node('h3', '', post.title), node('p', 'journal-card-author', post.authorName), node('p', 'journal-card-excerpt', post.content));
      if (post.location?.label) body.append(node('p', 'journal-card-location', `⌖ ${post.location.label}`));
      if (post.location?.source === 'geoapify') body.append(locationCredit(post.location));
      body.append(node('span', 'journal-id', `ID: ${post.id}`), button('Xem bài →', 'journal-text-button journal-view', () => showPost(post.id)));
      article.append(body);
      article.addEventListener('click', (event) => { if (!event.target.closest('button,a,video')) showPost(post.id); });
      return article;
    }

    function query(page) {
      const values = new FormData(search); const params = new URLSearchParams({ page: String(page), pageSize: String(PAGE_SIZE) });
      ['q', 'from', 'to'].forEach((key) => { const value = String(values.get(key) || '').trim(); if (value) params.set(key, value); });
      return params.toString();
    }

    async function loadPosts(reset = true) {
      if (state.loading && !reset) return;
      const generation = ++state.listGeneration;
      const page = reset ? 1 : state.page + 1;
      state.loading = true; more.disabled = true; search.querySelector('[type="submit"]').disabled = true;
      list.setAttribute('aria-busy', 'true'); announce(listStatus, 'Đang tìm những kỷ niệm…');
      if (reset) { list.replaceChildren(); more.hidden = true; }
      try {
        const data = await request(`/api/journal?${query(page)}`);
        if (generation !== state.listGeneration) return;
        const posts = Array.isArray(data.posts) ? data.posts : [];
        state.passwordConfigured = Boolean(data.journalPasswordConfigured);
        state.posts = reset ? posts : [...state.posts, ...posts]; state.page = page; state.hasMore = Boolean(data.hasMore);
        if (reset) list.replaceChildren();
        posts.forEach((post) => list.append(postCard(post)));
        if (!state.posts.length) {
          const hasFilter = ['q', 'from', 'to'].some((key) => search.elements[key].value);
          list.append(node('p', 'journal-empty', hasFilter ? 'Chưa tìm thấy kỷ niệm phù hợp. Thử một từ khóa hoặc khoảng ngày khác nhé.' : 'Một trang giấy còn trắng, chờ kỷ niệm đầu tiên của chúng mình. ♡'));
        }
        announce(listStatus, `${data.total ?? state.posts.length} kỷ niệm${data.hasMore ? ` · đang hiển thị ${state.posts.length}` : ''}`);
        more.hidden = !state.hasMore;
      } catch (error) { if (generation === state.listGeneration) announce(listStatus, error.message, true); }
      finally { if (generation === state.listGeneration) { state.loading = false; more.disabled = false; search.querySelector('[type="submit"]').disabled = false; list.removeAttribute('aria-busy'); } }
    }
    search.addEventListener('submit', (event) => { event.preventDefault(); if (search.elements.from.value && search.elements.to.value && search.elements.from.value > search.elements.to.value) { announce(listStatus, 'Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.', true); return; } loadPosts(); });
    search.addEventListener('reset', () => { window.setTimeout(() => loadPosts(), 0); });
    more.addEventListener('click', () => loadPosts(false));

    async function showPost(id) {
      if (!modal.open && !openDialog(modal)) return;
      modalBody.querySelectorAll('video').forEach((video) => video.pause());
      const generation = ++state.modalGeneration;
      modalBody.replaceChildren(); get('journal-dialog-title').textContent = 'Một kỷ niệm của chúng mình'; announce(modalStatus, 'Đang mở kỷ niệm…');
      try {
        const data = await request(`/api/journal/${encodeURIComponent(id)}`);
        if (!modal.open || generation !== state.modalGeneration) return;
        renderPost(data.post); announce(modalStatus, '');
      } catch (error) { if (modal.open && generation === state.modalGeneration) announce(modalStatus, error.message, true); }
    }

    function renderPost(post) {
      modalBody.querySelectorAll('video').forEach((video) => video.pause());
      modalBody.replaceChildren(); get('journal-dialog-title').textContent = post.title;
      const meta = node('div', 'journal-post-meta');
      meta.append(node('span', 'journal-post-author', post.authorName), node('time', '', dateText(post.createdAt)));
      modalBody.append(meta, node('p', 'journal-id', `ID: ${post.id}`));
      if (post.updatedAt && post.updatedAt !== post.createdAt) modalBody.append(node('p', 'journal-updated', `Cập nhật: ${dateText(post.updatedAt)}`));
      if (post.location?.label || validCoordinates(post.location)) modalBody.append(button(`⌖ ${post.location.label || post.location.lookupAddress || 'Địa điểm kỷ niệm'} ↗`, 'journal-post-location', () => openLocation(post.location)));
      if (post.location?.source === 'geoapify') modalBody.append(locationCredit(post.location));
      const content = node('div', 'journal-post-content', post.content); modalBody.append(content);
      if (post.images?.length) { const gallery = node('div', 'journal-gallery'); post.images.forEach((image) => gallery.append(imageNode(image))); modalBody.append(gallery); }
      const actions = node('div', 'journal-actions');
      const edit = button('Chỉnh sửa', 'journal-secondary', () => startEditor(post));
      const remove = button('Xóa bài', 'journal-danger', () => confirmDelete(post));
      edit.disabled = remove.disabled = !state.passwordConfigured;
      actions.append(edit, remove); modalBody.append(actions);
      modalBody.append(node('p', 'journal-help', state.passwordConfigured ? 'Mỗi lần sửa hoặc xóa đều cần mật khẩu bảo vệ nhật ký.' : 'Quản trị viên cần thiết lập mật khẩu nhật ký trong Cài đặt → Bảo mật trước khi sửa hoặc xóa.'));
      get('journal-dialog-title').focus({ preventScroll: true });
    }

    function field(label, name, value = '', options = {}) {
      const wrapper = node('label', options.wide ? 'journal-field journal-wide' : 'journal-field');
      wrapper.append(node('span', '', label));
      const input = node(options.multiline ? 'textarea' : 'input'); input.name = name; input.value = value ?? '';
      if (!options.multiline) input.type = options.type || 'text'; else input.rows = options.rows || 4;
      if (options.required) input.required = true;
      if (options.maxLength) input.maxLength = options.maxLength;
      if (options.minLength) input.minLength = options.minLength;
      if (options.min !== undefined) input.min = options.min;
      if (options.max !== undefined) input.max = options.max;
      if (options.step) input.step = options.step;
      if (options.autocomplete) input.autocomplete = options.autocomplete;
      if (options.placeholder) input.placeholder = options.placeholder;
      wrapper.append(input); return wrapper;
    }

    function passwordGate(parent, label, submitLabel, onSubmit) {
      const form = node('form', 'journal-auth-form');
      form.append(node('p', 'journal-help', label), field('Mật khẩu', 'password', '', { type: 'password', required: true, autocomplete: 'current-password', maxLength: 256 }));
      const submit = button(submitLabel, 'journal-primary'); submit.type = 'submit'; form.append(submit); parent.append(form);
      form.addEventListener('submit', async (event) => { event.preventDefault(); if (!form.reportValidity() || submit.disabled) return; submit.disabled = true; const password = form.elements.password.value; try { await onSubmit(password); } finally { form.elements.password.value = ''; submit.disabled = false; } });
      return form;
    }

    function clearDraft(discard = true) { state.draft?.media?.dispose({ discard }); state.draft = null; }
    function startEditor(post = null) {
      if (state.saving) return;
      if (!modal.open && !openDialog(modal)) return;
      if (state.draft && state.draft.id !== (post?.id || null)) {
        if (state.draft.dirty && !window.confirm('Bỏ bản nháp chưa lưu để mở bài này?')) return;
        clearDraft();
      }
      if (!state.draft) {
        const draft = { id: post?.id || null, authorName: post?.authorName || '', title: post?.title || '', content: post?.content || '', location: { ...(post?.location || {}), label: post?.location?.label || '', latitude: post?.location?.latitude ?? '', longitude: post?.location?.longitude ?? '' }, keepImages: [...(post?.images || [])], updatedAt: post?.updatedAt, dirty: false };
        draft.media = new window.LoveDaysMedia.Queue({ scope: 'journal', onChange: () => { if (state.draft === draft) draft.dirty = true; } }); state.draft = draft;
      }
      renderEditor();
    }

    function renderEditor() {
      const draft = state.draft; if (!draft) return;
      modalBody.querySelectorAll('video').forEach((video) => video.pause());
      state.modalGeneration += 1;
      modalBody.replaceChildren(); get('journal-dialog-title').textContent = draft.id ? 'Viết tiếp một kỷ niệm' : 'Giữ lại một ngày thương'; announce(modalStatus, '');
      const form = node('form', 'journal-editor'); form.id = 'journal-compose';
      const fields = node('fieldset', 'journal-fieldset');
      const grid = node('div', 'journal-form-grid');
      grid.append(field('Tên người đăng', 'authorName', draft.authorName, { required: true, maxLength: 80 }), field('Tiêu đề', 'title', draft.title, { required: true, maxLength: 160 }), field('Nội dung', 'content', draft.content, { multiline: true, required: true, maxLength: 20000, rows: 8, wide: true }));
      grid.append(field('Địa điểm (có thể nhập thủ công)', 'locationLabel', draft.location.label, { maxLength: 240, wide: true }));
      const locationStatus = node('p', 'journal-help journal-wide'); locationStatus.setAttribute('role', 'status');
      const locationAttribution = node('p', 'journal-help journal-wide journal-location-attribution');
      let locationGeneration = 0; let manualRevision = 0; let reverseController = null;
      let manualLabel = Boolean(draft.location.label && draft.location.label !== draft.location.lookupAddress);
      function renderLocationSource() {
        locationAttribution.replaceChildren();
        if (Number.isFinite(draft.location.accuracy)) locationAttribution.append(document.createTextNode(`Độ chính xác GPS: khoảng ${Math.round(draft.location.accuracy)} m. `));
        if (Number.isFinite(draft.location.lookupDistanceMeters)) locationAttribution.append(document.createTextNode(`Khoảng cách đến địa chỉ tra cứu: ${Math.round(draft.location.lookupDistanceMeters)} m. `));
        if (draft.location.approximate) locationAttribution.append(document.createTextNode('Địa chỉ khu vực gần đúng. '));
        if (draft.location.source === 'geoapify') {
          locationAttribution.append(document.createTextNode(`${draft.location.attribution || 'Địa chỉ'}: `));
          const credit = node('a', '', 'Geoapify'); credit.href = 'https://www.geoapify.com/'; credit.target = '_blank'; credit.rel = 'noopener noreferrer';
          const osm = node('a', '', '© OpenStreetMap'); osm.href = 'https://www.openstreetmap.org/copyright'; osm.target = '_blank'; osm.rel = 'noopener noreferrer'; locationAttribution.append(credit, document.createTextNode(' · '), osm);
        }
      }
      renderLocationSource();
      const locate = button('⌖ Lấy vị trí hiện tại', 'journal-secondary', () => {
        if (!navigator.geolocation) { announce(locationStatus, 'Trình duyệt chưa hỗ trợ định vị. Bạn vẫn có thể nhập địa điểm thủ công.', true); return; }
        const generation = ++locationGeneration; const revision = manualRevision; const allowLabel = !manualLabel; reverseController?.abort(); reverseController = new AbortController();
        // Keep the button available: a newer explicit lookup supersedes the old one.
        announce(locationStatus, 'Đang lấy vị trí…');
        navigator.geolocation.getCurrentPosition(async (position) => {
          if (state.draft !== draft || !form.isConnected || generation !== locationGeneration) return;
          const lat = position.coords.latitude; const lon = position.coords.longitude;
          if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) { announce(locationStatus, 'Thiết bị trả tọa độ không hợp lệ. Hãy thử lấy vị trí lại hoặc nhập thủ công.', true); return; }
          form.elements.latitude.value = lat; form.elements.longitude.value = lon;
          draft.location = { ...draft.location, accuracy: Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : null, lookupAddress: '', lookupDistanceMeters: null, source: 'geolocation', approximate: false, attribution: '' };
          capture(); renderLocationSource(); announce(locationStatus, 'Đã lấy tọa độ. Đang tìm địa chỉ gần nhất…');
          try {
            const data = await request('/api/location/reverse', { method: 'POST', body: JSON.stringify({ latitude: lat, longitude: lon, accuracy: draft.location.accuracy }), signal: reverseController.signal });
            if (state.draft !== draft || !form.isConnected || generation !== locationGeneration) return;
            const resolved = data.location || {};
            // The service can describe a nearby address; it must never move the GPS pin.
            ['lookupAddress', 'lookupDistanceMeters', 'source', 'attribution', 'approximate'].forEach((key) => { if (key in resolved) draft.location[key] = resolved[key]; });
            if (allowLabel && revision === manualRevision && resolved.lookupAddress) form.elements.locationLabel.value = resolved.lookupAddress.slice(0, 240);
            capture(); renderLocationSource(); announce(locationStatus, `${data.message || 'Đã tra cứu địa chỉ. Bạn có thể kiểm tra và sửa tên địa điểm trước khi đăng.'}${revision !== manualRevision ? ' Tên địa điểm bạn đang nhập được giữ nguyên.' : ''}`);
          } catch (error) { if (error.name !== 'AbortError' && state.draft === draft && form.isConnected && generation === locationGeneration) announce(locationStatus, 'Đã giữ tọa độ GPS. Chưa tra cứu được địa chỉ; hãy nhập tên địa điểm thủ công.', true); }
        }, () => { if (state.draft === draft && form.isConnected && generation === locationGeneration) announce(locationStatus, 'Không lấy được vị trí hoặc quyền định vị bị từ chối. Hãy nhập địa điểm thủ công.', true); }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 });
      });
      const coordinates = node('details', 'journal-coordinates journal-wide'); coordinates.append(node('summary', '', 'Tọa độ (tùy chọn)'));
      const coordinateGrid = node('div', 'journal-form-grid'); coordinateGrid.append(field('Vĩ độ', 'latitude', draft.location.latitude, { type: 'number', min: -90, max: 90, step: 'any' }), field('Kinh độ', 'longitude', draft.location.longitude, { type: 'number', min: -180, max: 180, step: 'any' })); coordinates.append(coordinateGrid);
      grid.append(locate, locationStatus, locationAttribution, coordinates);
      const imageField = field('Ảnh / video kỷ niệm (JPEG, PNG, WebP, MP4, WebM)', 'images', '', { type: 'file', wide: true });
      const fileInput = imageField.querySelector('input'); fileInput.accept = window.LoveDaysMedia.accept; fileInput.multiple = true;
      const previews = node('div', 'journal-previews journal-wide');
      const uploadPreviews = node('div', 'journal-previews journal-wide');
      grid.append(imageField, previews, uploadPreviews, node('p', 'journal-help journal-wide', 'Có thể chọn bổ sung nhiều lần. Tệp được chia phần và tải lần lượt theo hàng đợi; tệp lỗi có thể thử lại. Khả năng lưu phụ thuộc dung lượng còn lại của hosting.'));
      if (draft.id) { grid.append(field('Mật khẩu bảo vệ nhật ký (bắt buộc mỗi lần lưu)', 'password', '', { type: 'password', required: true, maxLength: 256, autocomplete: 'current-password', wide: true })); }
      else grid.append(node('p', 'journal-help journal-wide', 'Đăng bài cần phiên hộp thư hoặc quản trị hợp lệ. Bài và ảnh sau khi đăng sẽ được hiển thị công khai.'));
      fields.append(grid); form.append(fields);
      const authArea = node('div', 'journal-inline-auth');
      const actions = node('div', 'journal-actions');
      const submit = button(draft.id ? 'Lưu thay đổi ♡' : 'Đăng kỷ niệm ♡', 'journal-primary'); submit.type = 'submit';
      const cancel = button('Bỏ bản nháp', 'journal-text-button', () => { if (state.saving || (draft.dirty && !window.confirm('Bỏ nội dung và ảnh chưa lưu?'))) return; const id = draft.id; clearDraft(); if (id) showPost(id); else closeDialog(modal); });
      actions.append(submit, cancel); form.append(actions); modalBody.append(form, authArea);
      function capture() {
        draft.authorName = form.elements.authorName.value; draft.title = form.elements.title.value; draft.content = form.elements.content.value;
        draft.location = { ...draft.location, label: form.elements.locationLabel.value, latitude: form.elements.latitude.value, longitude: form.elements.longitude.value }; draft.dirty = true;
      }
      form.addEventListener('input', (event) => {
        if (event.target.name === 'locationLabel') { manualRevision += 1; manualLabel = true; }
        if (['latitude', 'longitude'].includes(event.target.name)) { locationGeneration += 1; reverseController?.abort(); draft.location = { ...draft.location, accuracy: null, lookupAddress: '', lookupDistanceMeters: null, source: 'manual', attribution: '', approximate: false }; renderLocationSource(); }
        if (event.target.type !== 'password' && event.target.type !== 'file') capture();
      });
      function previewsRender() {
        previews.replaceChildren();
        draft.keepImages.forEach((image) => {
          const figure = node('figure', 'journal-preview'); const name = image.originalName || 'Tệp đã lưu';
          const preview = imageNode(image, false);
          const remove = button('×', 'journal-preview-remove', () => { if (state.saving) return; draft.keepImages = draft.keepImages.filter((item) => item.id !== image.id); draft.dirty = true; previewsRender(); });
          remove.setAttribute('aria-label', `Bỏ tệp ${name}`); figure.append(preview, node('figcaption', '', name), remove); previews.append(figure);
        });
      }
      previewsRender(); draft.media.render(uploadPreviews);
      fileInput.addEventListener('change', () => {
        const errors = draft.media.addFiles(fileInput.files); fileInput.value = ''; announce(modalStatus, [...new Set(errors)].join(' '), errors.length > 0);
      });
      form.addEventListener('submit', async (event) => {
        event.preventDefault(); if (state.saving || !form.reportValidity()) return;
        capture();
        if (!draft.authorName.trim() || !draft.title.trim() || !draft.content.trim()) { announce(modalStatus, 'Hãy điền tên người đăng, tiêu đề và nội dung.', true); return; }
        if ((draft.location.latitude === '') !== (draft.location.longitude === '')) { announce(modalStatus, 'Hãy điền cả vĩ độ và kinh độ, hoặc để trống cả hai.', true); return; }
        const payload = { authorName: draft.authorName.trim(), title: draft.title.trim(), content: draft.content, location: { ...draft.location, label: draft.location.label.trim(), latitude: draft.location.latitude === '' ? null : Number(draft.location.latitude), longitude: draft.location.longitude === '' ? null : Number(draft.location.longitude) }, keepImageIds: draft.keepImages.map((image) => image.id) };
        if (draft.id) { payload.password = form.elements.password.value; payload.expectedUpdatedAt = draft.updatedAt; }
        state.saving = true; fields.disabled = true; submit.disabled = cancel.disabled = true; draft.media.setDisabled(true); announce(modalStatus, 'Đang lưu kỷ niệm…');
        try {
          if (!draft.id) { const permissions = await request('/api/journal?pageSize=1'); if (!permissions.canPost) { const error = new Error('Cần mở khóa hộp thư hoặc đăng nhập quản trị trước khi đăng.'); error.status = 401; throw error; } }
          // A fresh journal password grants upload access for editing without
          // requiring a separate mailbox/admin login; PUT verifies it again.
          if (draft.id && draft.media.entries.some((entry) => entry.status !== 'complete')) await request('/api/journal/history/unlock', { method: 'POST', body: JSON.stringify({ password: payload.password }) });
          payload.uploadIds = await draft.media.uploadAll();
          const data = await request(draft.id ? `/api/journal/${encodeURIComponent(draft.id)}` : '/api/journal', { method: draft.id ? 'PUT' : 'POST', body: JSON.stringify(payload) });
          clearDraft(false); renderPost(data.post); announce(modalStatus, 'Đã lưu kỷ niệm của chúng mình.'); loadPosts();
        } catch (error) {
          announce(modalStatus, `${error.message} Nội dung bản nháp vẫn được giữ.`, true);
          if (error.status === 401 && (!draft.id || error.data?.error !== 'incorrect_password')) {
            authArea.replaceChildren();
            passwordGate(authArea, 'Phiên đăng bài chưa mở khóa. Nhập mật khẩu hộp thư rồi bấm Đăng kỷ niệm lần nữa; hoặc đóng cửa sổ và đăng nhập quản trị.', 'Mở quyền đăng bài', async (password) => {
              try { await request('/api/auth', { method: 'POST', body: JSON.stringify({ password }) }); authArea.replaceChildren(); announce(modalStatus, 'Đã mở quyền đăng bài. Bấm Đăng kỷ niệm để lưu bản nháp.'); }
              catch (authError) { announce(modalStatus, authError.message, true); }
            });
          }
          if (error.status === 409 && draft.id) {
            announce(modalStatus, 'Bài đã được cập nhật ở nơi khác. Hãy xem phiên bản mới trước khi lưu bản nháp.', true);
            authArea.replaceChildren();
            const review = button('Xem phiên bản mới, giữ bản nháp', 'journal-secondary', async () => {
              if (review.disabled || state.saving) return;
              review.disabled = true;
              try {
                const latest = (await request(`/api/journal/${encodeURIComponent(draft.id)}`)).post;
                if (state.draft !== draft || !form.isConnected) return;
                const preview = node('details', 'journal-history-diff'); preview.open = true;
                preview.append(node('summary', '', `Phiên bản mới · ${dateText(latest.updatedAt)}`), node('h4', '', latest.title), node('p', 'journal-history-content', latest.content));
                const apply = button('Dùng bản nháp trên phiên bản này', 'journal-secondary', () => {
                  if (!window.confirm('Sau khi bấm Lưu, nội dung bản nháp sẽ thay thế phiên bản vừa xem. Bạn đã đối chiếu và muốn tiếp tục?')) return;
                  draft.updatedAt = latest.updatedAt;
                  draft.keepImages = draft.keepImages.filter((image) => latest.images.some((current) => current.id === image.id));
                  previewsRender(); authArea.replaceChildren();
                  announce(modalStatus, 'Đã cập nhật mốc phiên bản. Kiểm tra bản nháp, nhập lại mật khẩu và bấm Lưu khi sẵn sàng.');
                });
                authArea.replaceChildren(preview, apply);
              } catch (reviewError) { announce(modalStatus, reviewError.message, true); }
              finally { review.disabled = false; }
            });
            authArea.append(review);
          }
        } finally { state.saving = false; fields.disabled = false; submit.disabled = cancel.disabled = false; draft.media.setDisabled(false); if (form.elements.password) form.elements.password.value = ''; }
      });
      form.elements.authorName.focus({ preventScroll: true });
    }
    get('journal-new').addEventListener('click', () => startEditor());

    function confirmDelete(post) {
      modalBody.querySelectorAll('video').forEach((video) => video.pause());
      modalBody.replaceChildren(); get('journal-dialog-title').textContent = 'Xóa kỷ niệm này?'; announce(modalStatus, '');
      modalBody.append(node('p', 'journal-help', `“${post.title}” sẽ biến mất khỏi danh sách công khai. Lịch sử được giữ riêng trên máy chủ.`));
      const form = passwordGate(modalBody, 'Nhập mật khẩu bảo vệ nhật ký để xác nhận xóa.', 'Xác nhận xóa', async (password) => {
        if (state.saving) return;
        state.saving = true;
        try { await request(`/api/journal/${encodeURIComponent(post.id)}`, { method: 'DELETE', body: JSON.stringify({ password }) }); if (state.draft?.id === post.id) clearDraft(); closeDialog(modal); loadPosts(); }
        catch (error) { announce(modalStatus, error.message, true); }
        finally { state.saving = false; }
      });
      form.append(button('Giữ lại kỷ niệm', 'journal-text-button', () => { if (!state.saving) renderPost(post); }));
      form.elements.password.focus({ preventScroll: true });
    }

    function historyDiff(entry) {
      const wrapper = node('details', 'journal-history-diff'); wrapper.append(node('summary', '', 'Xem nội dung trước / sau'));
      const grid = node('div', 'journal-history-columns');
      [['Trước thay đổi', entry.before], ['Sau thay đổi', entry.after]].forEach(([label, post]) => {
        const column = node('div'); column.append(node('h4', '', label));
        if (!post) column.append(node('p', '', 'Không còn bài đăng.'));
        else {
          column.append(node('p', '', `Tên người đăng: ${post.authorName || ''}`), node('p', '', `Tiêu đề: ${post.title || ''}`), node('p', 'journal-history-content', post.content || ''), node('p', '', `Địa điểm: ${post.location?.label || 'Không có'}`), node('p', '', `Tọa độ: ${post.location?.latitude ?? '—'}, ${post.location?.longitude ?? '—'}`), node('p', '', `Ảnh: ${(post.images || []).map((image) => `${image.originalName} (${image.id})`).join(', ') || 'Không có'}`));
          if (post.deletedAt) column.append(node('strong', '', 'Bài đã bị xóa'));
        }
        grid.append(column);
      }); wrapper.append(grid); return wrapper;
    }

    async function loadHistory(reset = true) {
      if (state.historyLoading) return;
      const generation = state.historyGeneration;
      state.historyLoading = true; announce(historyStatus, 'Đang tải lịch sử riêng tư…');
      const page = reset ? 1 : state.historyPage + 1;
      try {
        const data = await request(`/api/journal/history?page=${page}&pageSize=15`);
        if (!historyAlive(generation)) return;
        if (reset) historyBody.replaceChildren(); else historyBody.querySelector('[data-history-more]')?.remove();
        state.historyPage = page;
        (data.entries || []).forEach((entry) => {
          const item = node('article', 'journal-history-entry');
          item.append(node('h3', '', entry.action === 'delete' ? 'Đã xóa bài' : 'Đã chỉnh sửa bài'), node('p', 'journal-help', `${dateText(entry.createdAt)} · ${entry.actor?.type === 'admin' ? 'Quản trị viên' : entry.actor?.type === 'mailbox' ? 'Phiên hộp thư' : 'Mật khẩu nhật ký'}`), node('p', 'journal-id', `ID bài: ${entry.postId}`), node('p', 'journal-id', `ID người thực hiện / phiên: ${entry.actor?.id || '—'}`), historyDiff(entry)); historyBody.append(item);
        });
        if (!data.entries?.length && reset) historyBody.append(node('p', 'journal-empty', 'Chưa có lần sửa hoặc xóa nào.'));
        if (data.hasMore) { const next = button('Tải thêm lịch sử', 'journal-secondary', () => loadHistory(false)); next.dataset.historyMore = ''; historyBody.append(next); }
        announce(historyStatus, 'Lịch sử được bảo vệ; mật khẩu không được ghi vào lịch sử.');
      } catch (error) {
        if (!historyAlive(generation)) return;
        if (error.status === 401 || error.status === 403) {
          historyBody.replaceChildren();
          const gate = passwordGate(historyBody, 'Nhập mật khẩu bảo vệ nhật ký hoặc đăng nhập quản trị để xem lịch sử.', 'Mở lịch sử', async (password) => { try { await request('/api/journal/history/unlock', { method: 'POST', body: JSON.stringify({ password }) }); if (!historyAlive(generation)) return; state.historyLoading = false; await loadHistory(); } catch (unlockError) { if (historyAlive(generation)) announce(historyStatus, unlockError.message, true); } });
          gate.elements.password.focus({ preventScroll: true });
          announce(historyStatus, 'Lịch sử có thể chứa nội dung đã xóa và chỉ hiển thị sau khi xác thực.');
        } else announce(historyStatus, error.message, true);
      } finally { if (generation === state.historyGeneration) state.historyLoading = false; }
    }
    get('journal-history').addEventListener('click', () => { if (openDialog(historyDialog)) loadHistory(); });

    async function showAdmin() {
      if (!openDialog(adminDialog)) return;
      const generation = state.adminGeneration;
      adminBody.replaceChildren(); announce(adminStatus, 'Đang kiểm tra phiên quản trị…');
      try {
        const data = await request('/api/admin/session'); if (!adminAlive(generation)) return;
        if (!data.authenticated) renderAdminLogin(data.configured, generation); else await renderAdminSettings(data.account, generation);
      } catch (error) { if (adminAlive(generation)) announce(adminStatus, error.message, true); }
    }
    get('admin-settings-toggle').addEventListener('click', showAdmin);

    function renderAdminLogin(configured = true, generation = state.adminGeneration) {
      if (!adminAlive(generation)) return;
      adminBody.replaceChildren();
      if (!configured) { adminBody.append(node('p', 'journal-help', 'Máy chủ chưa khởi tạo tài khoản quản trị. Hãy chạy lệnh setup theo hướng dẫn triển khai trên máy chủ.')); announce(adminStatus, ''); return; }
      const form = node('form', 'admin-login');
      form.append(field('Tên đăng nhập', 'username', '', { required: true, maxLength: 80, autocomplete: 'username' }), field('Mật khẩu', 'password', '', { type: 'password', required: true, maxLength: 256, autocomplete: 'current-password' }));
      const submit = button('Đăng nhập quản trị', 'journal-primary'); submit.type = 'submit'; form.append(submit); adminBody.append(form); announce(adminStatus, 'Quyền quản trị được xác thực riêng với hộp thư.');
      form.addEventListener('submit', async (event) => {
        event.preventDefault(); if (state.adminBusy || !form.reportValidity()) return;
        state.adminBusy = true; submit.disabled = true;
        try { const data = await request('/api/admin/login', { method: 'POST', body: JSON.stringify({ username: form.elements.username.value.trim(), password: form.elements.password.value }) }); if (adminAlive(generation)) await renderAdminSettings(data.account, generation); }
        catch (error) { if (adminAlive(generation)) announce(adminStatus, error.message, true); }
        finally { state.adminBusy = false; submit.disabled = false; form.elements.password.value = ''; }
      }); form.elements.username.focus({ preventScroll: true });
    }

    async function renderAdminSettings(account, generation = state.adminGeneration) {
      if (!adminAlive(generation)) return;
      announce(adminStatus, 'Đang tải cài đặt…');
      const [settings, accountData] = await Promise.all([request('/api/admin/settings'), request('/api/admin/accounts')]);
      if (!adminAlive(generation)) return;
      adminBody.replaceChildren(); announce(adminStatus, '');
      const header = node('div', 'admin-session'); header.append(node('span', '', `Đang đăng nhập: ${account?.username || 'Quản trị viên'}`), button('Đăng xuất', 'journal-text-button', async () => {
        if (state.adminBusy) return; state.adminBusy = true;
        try { await request('/api/admin/logout', { method: 'POST', body: '{}' }); if (adminAlive(generation)) renderAdminLogin(true, generation); loadPosts(); } catch (error) { if (adminAlive(generation)) announce(adminStatus, error.message, true); } finally { state.adminBusy = false; }
      })); adminBody.append(header);
      const groups = node('div', 'admin-groups'); adminBody.append(groups);
      function group(title, open = false) { const details = node('details', 'admin-group'); details.open = open; details.append(node('summary', '', title)); const body = node('div', 'admin-group-body'); details.append(body); groups.append(details); return body; }
      const profilesBody = group('Thông tin cá nhân', true);
      const profilesForm = node('form', 'admin-form'); profilesForm.dataset.group = 'profiles';
      const profilesFieldset = node('fieldset', 'journal-fieldset');
      Object.entries(settings.profiles || {}).forEach(([id, profile]) => {
        const person = node('section', 'admin-person'); person.dataset.personId = id;
        person.append(node('h3', '', profile.name || 'Thông tin cá nhân'));
        const grid = node('div', 'journal-form-grid');
        [['name', 'Họ và tên'], ['displayName', 'Tên hiển thị'], ['partner', 'Tên người đồng hành'], ['birthday', 'Ngày sinh'], ['gender', 'Giới tính'], ['hometown', 'Quê quán'], ['hobbies', 'Sở thích'], ['introduction', 'Giới thiệu'], ['avatar', 'Đường dẫn ảnh đại diện']].forEach(([key, label]) => grid.append(field(label, `${id}__${key}`, profile[key], { type: key === 'birthday' ? 'date' : 'text', required: ['name', 'displayName', 'birthday', 'avatar'].includes(key), maxLength: ['avatar', 'introduction', 'hobbies'].includes(key) ? 1000 : 80, wide: key === 'introduction' || key === 'avatar' })));
        person.append(grid); profilesFieldset.append(person);
      }); profilesForm.append(profilesFieldset); profilesBody.append(profilesForm);
      bindSettingsForm(profilesForm, 'profiles', () => { const payload = {}; Object.keys(settings.profiles || {}).forEach((id) => { payload[id] = {}; profilesForm.querySelectorAll(`[data-person-id="${id}"] input`).forEach((input) => { payload[id][input.name.split('__')[1]] = input.value.trim(); }); }); return payload; });

      const contentBody = group('Nội dung website'); const contentForm = node('form', 'admin-form');
      const contentFields = node('fieldset', 'journal-fieldset journal-form-grid');
      const labels = { title: 'Tiêu đề tab trình duyệt', heading: 'Tiêu đề chính', kicker: 'Dòng chữ phía trên tiêu đề', introduction: 'Lời giới thiệu', anniversary: 'Ngày bắt đầu bên nhau', loveNote: 'Lời yêu thương trên thẻ', heartMessage: 'Lời nhắn mặc định', heartMessages: 'Các lời nhắn khi nhấn tim (mỗi dòng một câu)', musicTitle: 'Tiêu đề nhạc', musicDescription: 'Mô tả nhạc', musicEyebrow: 'Dòng chữ nhỏ phần nhạc', musicSrc: 'Đường dẫn tệp nhạc', backgroundImage: 'Đường dẫn ảnh nền (tùy chọn)', footer: 'Nội dung cuối trang', loaderText: 'Lời nhắn lúc tải trang', loaderCaption: 'Mô tả lúc tải trang', clockLabel: 'Nhãn bộ đếm ngày', profileNote: 'Ghi chú popup hồ sơ', profileEyebrow: 'Dòng chữ đầu popup hồ sơ' };
      labels.recordLabel = 'Nhãn trên đĩa nhạc';
      Object.entries(labels).forEach(([key, label]) => contentFields.append(field(label, key, key === 'heartMessages' ? (settings.content?.[key] || []).join('\n') : settings.content?.[key] || '', { type: key === 'anniversary' ? 'date' : 'text', multiline: key === 'heartMessages' || key === 'musicTitle', rows: key === 'heartMessages' ? 6 : 3, required: key !== 'backgroundImage', maxLength: key === 'heartMessages' ? 12030 : ['backgroundImage', 'musicSrc'].includes(key) ? 1000 : 2000, wide: ['heartMessages', 'loveNote', 'introduction', 'musicSrc', 'backgroundImage', 'profileNote'].includes(key) })));
      contentForm.append(contentFields); contentBody.append(contentForm);
      bindSettingsForm(contentForm, 'content', () => { const payload = {}; Object.keys(labels).forEach((key) => { payload[key] = key === 'heartMessages' ? contentForm.elements[key].value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean) : contentForm.elements[key].value.trim(); }); if (!payload.heartMessages.length || payload.heartMessages.length > 30 || payload.heartMessages.some((message) => message.length > 400)) throw new Error('Cần từ 1 đến 30 lời nhắn, tối đa 400 ký tự mỗi lời nhắn.'); return payload; });

      const securityBody = group('Bảo mật'); const securityForm = node('form', 'admin-form');
      const securityFields = node('fieldset', 'journal-fieldset journal-form-grid');
      securityFields.append(node('p', 'journal-help journal-wide', 'Để trống mật khẩu nếu giữ nguyên. Đổi mật khẩu sẽ thu hồi các phiên/quyền liên quan.'));
      securityFields.append(node('p', 'journal-help journal-wide', 'Phiên hộp thư vẫn có giới hạn tuyệt đối 30 phút kể từ khi mở khóa, kể cả khi thời gian không sử dụng được đặt dài hơn.'));
      securityFields.append(field('Tự khóa hộp thư khi không sử dụng (30–86400 giây)', 'mailboxIdleSeconds', settings.security?.mailboxIdleSeconds ?? 300, { type: 'number', required: true, min: 30, max: 86400 }), field('Khóa sau khi đóng hộp thư (0–3600 giây)', 'mailboxCloseSeconds', settings.security?.mailboxCloseSeconds ?? 30, { type: 'number', required: true, min: 0, max: 3600 }));
      [['newMailboxPassword', 'Mật khẩu hộp thư mới'], ['confirmMailboxPassword', 'Xác nhận mật khẩu hộp thư mới'], ['newJournalPassword', 'Mật khẩu sửa/xóa nhật ký mới'], ['confirmJournalPassword', 'Xác nhận mật khẩu nhật ký mới']].forEach(([key, label]) => securityFields.append(field(label, key, '', { type: 'password', minLength: 8, maxLength: 256, autocomplete: 'new-password' })));
      securityFields.append(node('p', 'journal-help journal-wide', `Mật khẩu hộp thư: ${settings.security?.mailboxPasswordConfigured ? 'đã thiết lập' : 'chưa thiết lập'} · Mật khẩu nhật ký: ${settings.security?.journalPasswordConfigured ? 'đã thiết lập' : 'chưa thiết lập'}`));
      securityForm.append(securityFields); securityBody.append(securityForm);
      bindSettingsForm(securityForm, 'security', () => {
        const payload = { mailboxIdleSeconds: Number(securityForm.elements.mailboxIdleSeconds.value), mailboxCloseSeconds: Number(securityForm.elements.mailboxCloseSeconds.value) };
        [['newMailboxPassword', 'confirmMailboxPassword'], ['newJournalPassword', 'confirmJournalPassword']].forEach(([key, confirm]) => { const value = securityForm.elements[key].value; const confirmation = securityForm.elements[confirm].value; if (value !== confirmation) throw new Error('Mật khẩu mới và phần xác nhận phải giống nhau.'); if (value && value.length < 8) throw new Error('Mật khẩu mới cần ít nhất 8 ký tự.'); if (value) { payload[key] = value; payload[confirm] = confirmation; } }); return payload;
      });
      const accountsBody = group('Tài khoản quản trị');
      accountsBody.append(node('p', 'journal-help', 'Đổi username hoặc mật khẩu cần nhập lại mật khẩu của tài khoản đang đăng nhập. Sau khi đổi, bạn phải đăng nhập lại.'));
      (accountData.accounts || []).forEach((item) => {
        const form = node('form', 'admin-account-form'); const fieldset = node('fieldset', 'journal-fieldset journal-form-grid');
        fieldset.append(node('h3', 'journal-wide', item.username), field('Tên đăng nhập mới', 'username', item.username, { required: true, minLength: 3, maxLength: 80, autocomplete: 'off', wide: true }), field('Mật khẩu hiện tại của bạn', 'currentPassword', '', { type: 'password', required: true, maxLength: 256, autocomplete: 'current-password', wide: true }), field('Mật khẩu mới (để trống để giữ nguyên)', 'newPassword', '', { type: 'password', minLength: 8, maxLength: 256, autocomplete: 'new-password' }), field('Xác nhận mật khẩu mới', 'confirmPassword', '', { type: 'password', minLength: 8, maxLength: 256, autocomplete: 'new-password' }));
        const submit = button('Lưu tài khoản', 'journal-primary'); submit.type = 'submit'; const status = node('p', 'journal-status'); status.setAttribute('role', 'status');
        form.append(fieldset, submit, status); accountsBody.append(form);
        form.addEventListener('submit', async (event) => {
          event.preventDefault(); if (state.adminBusy || !form.reportValidity()) return;
          if (form.elements.newPassword.value !== form.elements.confirmPassword.value) { announce(status, 'Mật khẩu mới và phần xác nhận phải giống nhau.', true); return; }
          state.adminBusy = true; fieldset.disabled = submit.disabled = true; announce(status, 'Đang lưu tài khoản…');
          try { const result = await request(`/api/admin/accounts/${encodeURIComponent(item.id)}`, { method: 'PUT', body: JSON.stringify({ currentPassword: form.elements.currentPassword.value, username: form.elements.username.value.trim(), newPassword: form.elements.newPassword.value, confirmPassword: form.elements.confirmPassword.value }) }); if (!adminAlive(generation)) return; if (result.reauthenticate) { renderAdminLogin(true, generation); announce(adminStatus, 'Đã cập nhật tài khoản và thu hồi phiên cũ. Hãy đăng nhập lại.'); } else { await renderAdminSettings(account, generation); if (adminAlive(generation)) announce(adminStatus, 'Đã cập nhật tài khoản quản trị.'); } }
          catch (error) { if (!adminAlive(generation)) return; announce(status, error.message, true); if (error.status === 401 && error.data?.error === 'admin_required') { renderAdminLogin(true, generation); announce(adminStatus, error.message, true); } }
          finally { state.adminBusy = false; fieldset.disabled = submit.disabled = false; form.querySelectorAll('input[type="password"]').forEach((input) => { input.value = ''; }); }
        });
      });
    }

    function bindSettingsForm(form, group, payloadGetter) {
      const generation = state.adminGeneration;
      const submit = button('Lưu thay đổi', 'journal-primary'); submit.type = 'submit'; const status = node('p', 'journal-status'); status.setAttribute('role', 'status'); form.append(submit, status);
      form.addEventListener('submit', async (event) => {
        event.preventDefault(); if (state.adminBusy || !form.reportValidity()) return;
        let payload; try { payload = payloadGetter(); } catch (error) { announce(status, error.message, true); return; }
        state.adminBusy = true; submit.disabled = true; form.querySelector('fieldset').disabled = true; announce(status, 'Đang lưu thay đổi…');
        try {
          const settings = await request(`/api/admin/settings/${group}`, { method: 'PUT', body: JSON.stringify(payload) });
          if (!adminAlive(generation)) return;
          announce(status, 'Đã lưu thay đổi.');
          if (group === 'security') { state.passwordConfigured = Boolean(settings.security?.journalPasswordConfigured); form.querySelectorAll('input[type="password"]').forEach((input) => { input.value = ''; }); document.dispatchEvent(new CustomEvent('lovedays:mailbox-settings-changed')); }
          if (window.LoveDaysSite?.refresh) await window.LoveDaysSite.refresh();
          else { const site = await request('/api/site'); document.dispatchEvent(new CustomEvent('lovedays:site-updated', { detail: site })); }
          loadPosts();
        } catch (error) { if (!adminAlive(generation)) return; announce(status, error.message, true); if (error.status === 401 && error.data?.error === 'admin_required') { renderAdminLogin(true, generation); announce(adminStatus, 'Phiên quản trị đã hết hạn. Hãy đăng nhập lại.', true); } }
        finally { state.adminBusy = false; submit.disabled = false; form.querySelector('fieldset').disabled = false; }
      });
    }

    window.addEventListener('beforeunload', (event) => { if (state.draft?.dirty || state.saving) { event.preventDefault(); event.returnValue = ''; } });
    loadPosts();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true }); else initialize();
})();
