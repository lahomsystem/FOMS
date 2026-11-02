/**
 * FOMS 공지 쓰기 · 고치기 — "사진" 칸(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §8).
 * - 끌어놓기 · 고르기 → 한 장씩 POST /api/admin/notices/images (multipart image)
 *   → {success, data:{key, thumb_key, name, width, height, size, preview_url, thumb_url}, error}.
 * - 썸네일 줄: 지우기(X) · 순서 바꾸기(좌우 화살표). 최대 data-max 장(5), 한 장 15MB, JPG · PNG · WEBP · HEIC.
 * - 오른쪽 휴대폰 미리보기의 썸네일 줄([data-preview-images])도 바로 바꾼다 — 누르면 받는 사람과 같은 사진 창
 *   (static/js/foms/foms-notice-gallery.js).
 * - 저장은 notices-form.js 가 window.FomsNoticeImages.payload() 를 페이로드 images 로 싣는다(올리는 중이면 막는다).
 * 고치기 화면의 지금 사진은 data-notice(JSON)의 images 로 받는다. CSRF 는 공용 csrf_bootstrap fetch 래퍼가 붙인다.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-notice-form]');
  var field = root && root.querySelector('[data-notice-images-field]');
  if (!field) return;
  var input = field.querySelector('[data-images-input]');
  var drop = field.querySelector('[data-images-drop]');
  var listBox = field.querySelector('[data-images-list]');
  var statusBox = field.querySelector('[data-images-status]');
  var countBox = field.querySelector('[data-images-count]');
  var uploadUrl = field.getAttribute('data-upload-url') || '/api/admin/notices/images';
  var max = Number(field.getAttribute('data-max')) || 5;
  var MAX_BYTES = 15 * 1024 * 1024;
  var OK_EXT = /\.(jpe?g|png|webp|heic|heif)$/i;
  var items = []; // {key, thumb_key, name, width, height, size, preview_url, thumb_url} | {pending:true, name, id}
  var seq = 0;

  function safeJsonParse(val, fb) {
    try {
      var text = String(val || '').trim();
      return text ? JSON.parse(text) : fb;
    } catch (err) {
      return fb;
    }
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function say(text, kind) {
    if (!statusBox) return;
    statusBox.textContent = text || '';
    statusBox.classList.toggle('is-error', kind === 'error');
  }

  function saved() { return items.filter(function (it) { return !it.pending; }); }

  function galleryItems() {
    return saved().map(function (it) { return { url: it.preview_url, thumb_url: it.thumb_url, name: it.name }; });
  }

  function iconButton(label, iconName, action, index, disabled) {
    var button = el('button', 'foms-notice-upload__btn');
    button.type = 'button';
    button.setAttribute('aria-label', label);
    button.setAttribute('data-image-action', action);
    button.setAttribute('data-image-index', String(index));
    button.disabled = !!disabled;
    var icon = el('i', 'fas ' + iconName);
    icon.setAttribute('aria-hidden', 'true');
    button.appendChild(icon);
    return button;
  }

  function renderList() {
    while (listBox.firstChild) listBox.removeChild(listBox.firstChild);
    var done = saved();
    items.forEach(function (it) {
      var li = el('li', 'foms-notice-upload' + (it.pending ? ' is-pending' : ''));
      if (it.pending) {
        li.appendChild(el('span', 'foms-notice-upload__spinner', '올리는 중…'));
        li.appendChild(el('span', 'foms-notice-upload__name', it.name));
        listBox.appendChild(li);
        return;
      }
      var at = done.indexOf(it);
      var thumbWrap = el('div', 'foms-notice-thumbs foms-notice-upload__thumb');
      thumbWrap.setAttribute('data-foms-notice-images', '');
      var thumb = el('button', 'foms-notice-thumb');
      thumb.type = 'button';
      thumb.setAttribute('data-foms-notice-thumb', '');
      thumb.setAttribute('data-index', String(at));
      thumb.setAttribute('aria-label', '사진 ' + (at + 1) + ' 크게 보기');
      var img = el('img', 'foms-notice-thumb__img');
      img.alt = '';
      img.src = it.thumb_url;
      thumb.appendChild(img);
      thumbWrap.appendChild(thumb);
      thumbWrap.__fomsImages = galleryItems();
      li.appendChild(thumbWrap);
      li.appendChild(el('span', 'foms-notice-upload__name', it.name));
      var tools = el('span', 'foms-notice-upload__tools');
      tools.appendChild(iconButton('앞으로', 'fa-arrow-left', 'left', at, at === 0));
      tools.appendChild(iconButton('뒤로', 'fa-arrow-right', 'right', at, at === done.length - 1));
      tools.appendChild(iconButton('사진 빼기', 'fa-xmark', 'remove', at, false));
      li.appendChild(tools);
      listBox.appendChild(li);
    });
    if (countBox) countBox.textContent = items.length + ' / ' + max;
    if (drop) drop.classList.toggle('is-full', items.length >= max);
    renderPreview();
  }

  function renderPreview() {
    var gallery = window.FomsNoticeGallery;
    root.querySelectorAll('[data-preview-images]').forEach(function (box) {
      if (gallery) gallery.render(box, galleryItems());
      else box.hidden = true;
    });
  }

  async function uploadOne(file, placeholder) {
    var body = new FormData();
    body.append('image', file, file.name);
    var data = null;
    try {
      var response = await fetch(uploadUrl, { method: 'POST', credentials: 'same-origin', body: body,
        headers: { 'Accept': 'application/json' } });
      try { data = await response.json(); } catch (err) { data = null; }
      if (!response.ok || !data || !data.success || !data.data) {
        throw new Error((data && data.error) || ('사진을 올리지 못했어요(' + response.status + ').'));
      }
      var at = items.indexOf(placeholder);
      if (at >= 0) items[at] = data.data;
      return '';
    } catch (err) {
      var idx = items.indexOf(placeholder);
      if (idx >= 0) items.splice(idx, 1);
      return file.name + ': ' + (err && err.message ? err.message : '사진을 올리지 못했어요.');
    }
  }

  async function addFiles(fileList) {
    var files = Array.prototype.slice.call(fileList || []);
    if (!files.length) return;
    var problems = [];
    var jobs = [];
    files.forEach(function (file) {
      if (items.length >= max) { problems.push('사진은 ' + max + '장까지 올릴 수 있어요.'); return; }
      if (!OK_EXT.test(file.name || '') && !/^image\//.test(file.type || '')) {
        problems.push(file.name + ': JPG · PNG · WEBP · HEIC 사진만 올릴 수 있어요.');
        return;
      }
      if (file.size > MAX_BYTES) { problems.push(file.name + ': 한 장에 15MB 까지 올릴 수 있어요.'); return; }
      var placeholder = { pending: true, name: file.name, id: ++seq };
      items.push(placeholder);
      jobs.push({ file: file, placeholder: placeholder });
    });
    renderList();
    say(jobs.length ? '사진을 올리는 중이에요…' : '', '');
    for (var i = 0; i < jobs.length; i += 1) {
      var why = await uploadOne(jobs[i].file, jobs[i].placeholder);
      if (why) problems.push(why);
      renderList();
    }
    var unique = problems.filter(function (p, i) { return problems.indexOf(p) === i; });
    say(unique.length ? unique.join(' ') : (jobs.length ? '사진을 올렸어요. 저장을 눌러야 공지에 붙어요.' : ''),
      unique.length ? 'error' : '');
    if (input) input.value = '';
  }

  function onAction(button) {
    var action = button.getAttribute('data-image-action');
    var done = saved();
    var target = done[Number(button.getAttribute('data-image-index'))];
    var at = items.indexOf(target);
    if (at < 0) return;
    if (action === 'remove') {
      items.splice(at, 1);
      say('사진을 뺐어요. 저장을 눌러야 반영돼요.', '');
    } else {
      var step = action === 'left' ? -1 : 1;
      var other = done[done.indexOf(target) + step];
      var to = items.indexOf(other);
      if (to < 0) return;
      items[to] = target;
      items[at] = other;
    }
    renderList();
  }

  field.addEventListener('click', function (ev) {
    var button = ev.target.closest('[data-image-action]');
    if (button) onAction(button);
  });
  if (input) input.addEventListener('change', function () { addFiles(input.files); });
  if (drop) {
    ['dragenter', 'dragover'].forEach(function (name) {
      drop.addEventListener(name, function (ev) { ev.preventDefault(); drop.classList.add('is-dragover'); });
    });
    ['dragleave', 'drop'].forEach(function (name) {
      drop.addEventListener(name, function () { drop.classList.remove('is-dragover'); });
    });
    drop.addEventListener('drop', function (ev) {
      ev.preventDefault();
      addFiles(ev.dataTransfer && ev.dataTransfer.files);
    });
  }

  var current = safeJsonParse(root.getAttribute('data-notice'), {}) || {};
  items = (Array.isArray(current.images) ? current.images : []).filter(function (it) {
    return it && it.key && it.thumb_url && it.preview_url;
  }).slice(0, max);

  window.FomsNoticeImages = {
    payload: function () {
      return saved().map(function (it) {
        return { key: it.key, thumb_key: it.thumb_key, name: it.name, width: it.width, height: it.height, size: it.size };
      });
    },
    busy: function () { return items.some(function (it) { return it.pending; }); },
    refresh: renderPreview
  };
  renderList();
})();
