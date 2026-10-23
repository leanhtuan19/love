(() => {
  'use strict';

  // Cập nhật thông tin tại đây; các mục để trống sẽ không xuất hiện trong popup.
  const profiles = {
    tuan: {
      name: 'Lê Anh Tuấn',
      partner: 'Anh Thư',
      introduction: '',
      birthday: '19/06/2007',
      gender: 'Nam',
      hometown: 'Hà Tĩnh',
      hobbies: ''
    },
    thu: {
      name: 'Lê Phạm Anh Thư',
      partner: 'Anh Tuấn',
      introduction: '',
      birthday: '10/01/2004',
      gender: 'Nữ',
      hometown: 'Hà Tĩnh',
      hobbies: ''
    }
  };

  function initializeProfiles() {
    const dialog = document.getElementById('profile-dialog');
    const closeButton = document.getElementById('profile-close');
    const avatar = document.getElementById('profile-avatar');
    const role = document.getElementById('profile-role');
    const name = document.getElementById('profile-name');
    const bio = document.getElementById('profile-bio');
    const details = document.getElementById('profile-details');

    if (!dialog || typeof dialog.showModal !== 'function' || !closeButton || !avatar || !name || !bio || !details) return;
    if (dialog.parentElement !== document.body) document.body.append(dialog);

    let activeTrigger = null;
    let backdropPointer = null;

    function lockScroll() {
      window.LoveDaysViewport.lock(dialog);
    }

    function unlockScroll() {
      window.LoveDaysViewport.unlock(dialog);
    }

    function addDetail(label, value) {
      if (!value) return;
      const term = document.createElement('dt');
      const description = document.createElement('dd');
      term.textContent = label;
      description.textContent = value;
      details.append(term, description);
    }

    function renderProfile(trigger, profile) {
      const originalAvatar = trigger.querySelector('.avt');
      const imageSource = originalAvatar?.getAttribute('src');
      if (imageSource) avatar.setAttribute('src', imageSource);
      else avatar.removeAttribute('src');
      avatar.hidden = !imageSource;
      avatar.alt = originalAvatar?.alt || `Ảnh đại diện của ${profile.name}`;

      name.textContent = profile.name;
      if (role) role.textContent = `Người đồng hành của ${profile.partner}`;
      bio.textContent = profile.introduction || 'Một nửa trong câu chuyện của chúng mình.';
      details.replaceChildren();
      addDetail('Ngày sinh', profile.birthday);
      addDetail('Giới tính', profile.gender);
      addDetail('Quê quán', profile.hometown);
      addDetail('Sở thích', profile.hobbies);

      const anniversary = document.getElementById('anniversary');
      const startDateValue = anniversary?.getAttribute('datetime');
      const startDate = startDateValue ? new Date(`${startDateValue}T00:00:00+07:00`) : null;
      if (startDate && Number.isFinite(startDate.getTime())) {
        addDetail('Ngày bắt đầu', anniversary.textContent.trim());
        const days = Math.max(0, Math.floor((Date.now() - startDate.getTime()) / 86400000));
        addDetail('Đã bên nhau', `${new Intl.NumberFormat('vi-VN').format(days)} ngày`);
      }
    }

    document.querySelectorAll('.profile[data-profile]').forEach((trigger) => {
      const profile = profiles[trigger.dataset.profile];
      if (!profile) return;
      trigger.addEventListener('click', (event) => {
        event.preventDefault();
        if (dialog.open) return;
        activeTrigger = trigger;
        backdropPointer = null;
        renderProfile(trigger, profile);
        lockScroll();
        try {
          dialog.showModal();
          closeButton.focus({ preventScroll: true });
          window.LoveDaysViewport.refresh();
        } catch (error) {
          unlockScroll();
          activeTrigger = null;
          throw error;
        }
      });
      trigger.disabled = false;
    });

    document.addEventListener('lovedays:site-updated', (event) => {
      Object.entries(event.detail?.profiles || {}).forEach(([id, values]) => {
        if (!profiles[id] || !values || typeof values !== 'object') return;
        ['name', 'partner', 'introduction', 'gender', 'hometown', 'hobbies'].forEach((key) => {
          if (typeof values[key] === 'string') profiles[id][key] = values[key];
        });
        if (typeof values.birthday === 'string') profiles[id].birthday = /^\d{4}-\d{2}-\d{2}$/.test(values.birthday)
          ? values.birthday.split('-').reverse().join('/') : values.birthday;
      });
      if (dialog.open && activeTrigger) renderProfile(activeTrigger, profiles[activeTrigger.dataset.profile]);
    });

    closeButton.addEventListener('click', () => dialog.close());

    dialog.addEventListener('keydown', (event) => {
      if (event.key !== 'Tab') return;
      const focusable = Array.from(dialog.querySelectorAll('a[href], area[href], button, input, select, textarea, iframe, object, embed, [contenteditable], [tabindex]'))
        .filter((element) => element.tabIndex >= 0 && !element.matches(':disabled') &&
          !element.closest('[hidden], [inert]') && element.getClientRects().length > 0 &&
          !['hidden', 'collapse'].includes(window.getComputedStyle(element).visibility))
        .sort((first, second) => (first.tabIndex || Infinity) - (second.tabIndex || Infinity));
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (!first) {
        event.preventDefault();
        dialog.focus({ preventScroll: true });
      } else if (event.shiftKey && (active === first || active === dialog || !dialog.contains(active))) {
        event.preventDefault();
        last.focus({ preventScroll: true });
      } else if (!event.shiftKey && (active === last || active === dialog || !dialog.contains(active))) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      }
    });

    function isOutsideDialog(event) {
      const bounds = dialog.getBoundingClientRect();
      return event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom;
    }

    dialog.addEventListener('pointerdown', (event) => {
      backdropPointer = event.button === 0 && isOutsideDialog(event) ? event.pointerId : null;
    });
    dialog.addEventListener('pointerup', (event) => {
      const shouldClose = backdropPointer === event.pointerId && isOutsideDialog(event);
      backdropPointer = null;
      if (shouldClose) dialog.close();
    });
    dialog.addEventListener('pointercancel', () => { backdropPointer = null; });
    dialog.addEventListener('close', () => {
      if (dialog.open) return;
      backdropPointer = null;
      unlockScroll();
      activeTrigger?.focus({ preventScroll: true });
      activeTrigger = null;
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeProfiles, { once: true });
  } else {
    initializeProfiles();
  }
})();
