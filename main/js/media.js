(() => {
  'use strict';
  const CONCURRENT_UPLOADS = 2;
  const FALLBACK_CHUNK_BYTES = 1024 * 1024;
  const ACCEPT = 'image/jpeg,image/png,image/webp,video/mp4,video/webm';
  const TYPES = new Set(ACCEPT.split(','));
  const appUrl = (path) => new URL(path.replace(/^\/+/, ''), new URL('.', document.baseURI)).href;
  const node = (tag, className, text) => { const item = document.createElement(tag); if (className) item.className = className; if (text !== undefined) item.textContent = text; return item; };
  const formatBytes = (bytes) => { if (bytes < 1024) return `${bytes} B`; const unit = Math.min(3, Math.floor(Math.log(bytes) / Math.log(1024))); return `${(bytes / (1024 ** unit)).toFixed(unit > 1 ? 1 : 0)} ${['B', 'KB', 'MB', 'GB'][unit]}`; };
  async function responseData(response) {
    let data = {}; try { data = await response.json(); } catch (_) { /* Hosting errors may return HTML. */ }
    if (!response.ok) { const error = new Error(data.message || (response.status === 413 ? 'Máy chủ từ chối phần tải lên. Hãy kiểm tra cấu hình proxy hoặc hosting.' : 'Tải tệp chưa thành công. Bạn có thể thử lại.')); error.status = response.status; error.data = data; throw error; }
    return data;
  }
  async function csrfToken() { return (await responseData(await fetch(appUrl('/api/session'), { credentials: 'same-origin', cache: 'no-store' }))).csrfToken; }
  async function request(path, method = 'GET', data) {
    const headers = {}; if (method !== 'GET') { headers['X-CSRF-Token'] = await csrfToken(); headers['Content-Type'] = 'application/json'; }
    return responseData(await fetch(appUrl(path), { method, headers, body: data === undefined ? undefined : JSON.stringify(data), credentials: 'same-origin', cache: 'no-store' }));
  }
  let sequence = 0;
  class Queue {
    constructor({ scope, onChange = () => {} }) { this.scope = scope; this.onChange = onChange; this.entries = []; this.container = null; this.busy = false; this.disabled = false; this.disposed = false; this.paused = false; this.xhrs = new Set(); }
    addFiles(files) {
      const errors = [];
      for (const file of files || []) {
        // MIME from a picker is an early usability check only; the server verifies bytes.
        const extension = file.name.split('.').pop().toLowerCase();
        const suppliedType = file.type === 'application/octet-stream' ? '' : file.type;
        if ((!TYPES.has(suppliedType) && suppliedType) || (!suppliedType && !['jpg', 'jpeg', 'png', 'webp', 'mp4', 'webm'].includes(extension))) { errors.push(`${file.name}: hỗ trợ JPEG, PNG, WebP, MP4 và WebM.`); continue; }
        if (!file.size) { errors.push(`${file.name}: tệp đang trống.`); continue; }
        this.entries.push({ id: `media-${++sequence}`, file, name: file.name, kind: file.type.startsWith('video/') || ['mp4', 'webm'].includes(extension) ? 'video' : 'image', url: URL.createObjectURL(file), status: 'waiting', offset: 0, loaded: 0, uploadId: null, error: '', view: null });
      }
      this.render(this.container); this.onChange(this); return errors;
    }
    setDisabled(value) { this.disabled = Boolean(value); this.entries.forEach((entry) => this.update(entry)); }
    stopPreviews() { this.container?.querySelectorAll('video').forEach((video) => video.pause()); }
    render(container) {
      this.stopPreviews();
      if (container) this.container = container; if (!this.container) return;
      this.container.replaceChildren(); this.container.classList.add('love-media-queue');
      this.entries.forEach((entry) => {
        if (!entry.url) entry.url = URL.createObjectURL(entry.file);
        const figure = node('figure', 'love-media-item journal-preview');
        const preview = node(entry.kind === 'video' ? 'video' : 'img', 'love-media-preview');
        preview.src = entry.url;
        if (entry.kind === 'video') { preview.controls = true; preview.playsInline = true; preview.preload = 'none'; preview.setAttribute('aria-label', entry.name); }
        else { preview.alt = entry.name; preview.loading = 'lazy'; }
        const status = node('p', 'love-media-status'); status.setAttribute('role', 'status');
        const progress = node('progress', 'love-media-progress'); progress.max = entry.file.size; progress.value = entry.loaded; progress.setAttribute('aria-label', `Tiến trình ${entry.name}`);
        const remove = node('button', 'journal-preview-remove', '×'); remove.type = 'button'; remove.setAttribute('aria-label', `Bỏ tệp ${entry.name}`); remove.addEventListener('click', () => this.remove(entry));
        const retry = node('button', 'journal-secondary love-media-retry', 'Thử lại tệp'); retry.type = 'button'; retry.addEventListener('click', () => this.uploadEntries([entry]).catch(() => {}));
        figure.append(preview, node('figcaption', '', `${entry.name} · ${formatBytes(entry.file.size)}`), progress, status, retry, remove); this.container.append(figure); entry.view = { status, progress, retry, remove }; this.update(entry);
      });
    }
    update(entry) {
      if (!entry.view) return;
      const { status, progress, retry, remove } = entry.view;
      const percent = Math.min(100, Math.floor((entry.loaded / entry.file.size) * 100));
      status.textContent = entry.status === 'complete' ? 'Đã tải xong · chờ lưu bài' : entry.status === 'uploading' ? `Đang tải ${percent}%` : entry.status === 'error' ? entry.error : 'Sẵn sàng tải khi lưu';
      status.classList.toggle('is-error', entry.status === 'error'); progress.value = entry.loaded; progress.hidden = entry.status === 'waiting'; retry.hidden = entry.status !== 'error'; retry.disabled = this.busy || this.disabled; remove.disabled = this.busy || this.disabled;
    }
    remove(entry) {
      if (this.busy || this.disabled) return;
      this.entries = this.entries.filter((item) => item !== entry); URL.revokeObjectURL(entry.url);
      if (entry.uploadId) request(`/api/uploads/${encodeURIComponent(entry.uploadId)}`, 'DELETE', {}).catch(() => {});
      this.render(this.container); this.onChange(this);
    }
    async sendChunk(entry, blob, offset) {
      const token = await csrfToken(); if (this.disposed || this.paused) throw new Error('Đã dừng hàng đợi.');
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest(); this.xhrs.add(xhr); xhr.open('PUT', appUrl(`/api/uploads/${encodeURIComponent(entry.uploadId)}`)); xhr.withCredentials = true; xhr.timeout = 90000; xhr.setRequestHeader('X-CSRF-Token', token); xhr.setRequestHeader('Content-Type', 'application/octet-stream'); xhr.setRequestHeader('Upload-Offset', String(offset));
        xhr.upload.onprogress = (event) => { entry.loaded = offset + event.loaded; this.update(entry); };
        const fail = (message) => { this.xhrs.delete(xhr); reject(new Error(message)); };
        xhr.onerror = () => fail('Mất kết nối khi tải tệp. Bấm thử lại để tiếp tục phần còn lại.'); xhr.ontimeout = () => fail('Phần tải lên hết thời gian chờ. Bấm thử lại để tiếp tục.'); xhr.onabort = () => fail('Đã dừng tải tệp.');
        xhr.onload = () => { this.xhrs.delete(xhr); let data = {}; try { data = JSON.parse(xhr.responseText); } catch (_) { /* Proxy failure. */ } if (xhr.status >= 200 && xhr.status < 300) resolve(data); else { const error = new Error(data.message || (xhr.status === 413 ? 'Hosting từ chối phần tải lên; kiểm tra giới hạn request.' : 'Tải tệp lỗi. Hãy thử lại để tiếp tục.')); error.status = xhr.status; error.data = data; reject(error); } };
        // Blob.slice streams a bounded chunk; never turn a whole video into Base64/ArrayBuffer.
        xhr.send(blob);
      });
    }
    async uploadEntry(entry) {
      if (entry.status === 'complete') return;
      entry.status = 'uploading'; entry.error = ''; this.update(entry);
      try {
        let upload;
        if (entry.uploadId) { try { upload = await request(`/api/uploads/${encodeURIComponent(entry.uploadId)}`); } catch (error) { if (error.status !== 404 && error.status !== 410) throw error; entry.uploadId = null; } }
        if (!entry.uploadId) { upload = await request('/api/uploads', 'POST', { scope: this.scope, name: entry.name, size: entry.file.size, mimeType: entry.file.type, lastModified: entry.file.lastModified }); entry.uploadId = upload.id; }
        entry.offset = Number(upload.offset || 0); const chunkBytes = Number(upload.chunkSize) > 0 ? Number(upload.chunkSize) : FALLBACK_CHUNK_BYTES;
        entry.loaded = entry.offset; this.update(entry);
        while (entry.offset < entry.file.size) {
          if (this.disposed || this.paused) throw new Error('Đã dừng hàng đợi.');
          const end = Math.min(entry.offset + chunkBytes, entry.file.size); const data = await this.sendChunk(entry, entry.file.slice(entry.offset, end), entry.offset); const next = Number(data.offset);
          if (!Number.isSafeInteger(next) || next <= entry.offset || next > entry.file.size) throw new Error('Máy chủ trả tiến trình không hợp lệ. Hãy thử lại.');
          entry.offset = next; entry.loaded = next; this.update(entry);
        }
        if (this.disposed || this.paused) throw new Error('Đã dừng hàng đợi.');
        await request(`/api/uploads/${encodeURIComponent(entry.uploadId)}/finish`, 'POST', {});
        entry.status = 'complete'; entry.loaded = entry.file.size;
      } catch (error) { entry.status = 'error'; entry.error = error.message; entry.failure = error; }
      this.update(entry);
    }
    async uploadEntries(entries) {
      if (this.busy) throw new Error('Các tệp đang được tải.');
      this.paused = false; this.busy = true; this.entries.forEach((entry) => this.update(entry));
      let cursor = 0;
      try { await Promise.all(Array.from({ length: Math.min(CONCURRENT_UPLOADS, entries.length) }, async () => { while (cursor < entries.length && !this.disposed && !this.paused) { const entry = entries[cursor++]; await this.uploadEntry(entry); } })); }
      finally { this.busy = false; this.entries.forEach((entry) => this.update(entry)); }
      if (this.disposed) throw new Error('Đã hủy hàng đợi.');
      const failed = entries.filter((entry) => entry.status !== 'complete');
      if (failed.length) { const error = new Error(`${failed.length} tệp chưa tải xong. Các tệp đã thành công và bản nháp vẫn được giữ. ${failed[0].error || ''}`); error.status = failed[0].failure?.status; error.data = failed[0].failure?.data; throw error; }
      return this.entries.map((entry) => entry.uploadId);
    }
    uploadAll() { return this.uploadEntries(this.entries.filter((entry) => entry.status !== 'complete')); }
    pause() { this.paused = true; this.xhrs.forEach((xhr) => xhr.abort()); }
    detach() { this.pause(); this.stopPreviews(); this.entries.forEach((entry) => { if (entry.url) URL.revokeObjectURL(entry.url); entry.url = null; entry.view = null; }); this.container = null; }
    dispose({ discard = true } = {}) { this.disposed = true; this.stopPreviews(); this.xhrs.forEach((xhr) => xhr.abort()); this.entries.forEach((entry) => { if (entry.url) URL.revokeObjectURL(entry.url); entry.view = null; if (discard && entry.uploadId) request(`/api/uploads/${encodeURIComponent(entry.uploadId)}`, 'DELETE', {}).catch(() => {}); }); this.entries = []; this.container = null; }
  }
  window.LoveDaysMedia = { Queue, accept: ACCEPT, concurrentUploads: CONCURRENT_UPLOADS };
})();
