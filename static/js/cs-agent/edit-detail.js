/**
 * [수정하기] '왜 고쳤나요(자세히) · 사진' 칸(설계서 17.6.1 (a) — templates/cs/cs_agent_send.html 의 [data-cs-detail]).
 *
 * 보내기를 막지 않는다 — 이유 · 사진은 화면에만 두었다가 send-screen.js 가 보냄을 굳히고 쏘는 'cs-send:sent' 를 받은 뒤에
 * 이유(JSON) → 사진(한 장씩 multipart)을 차례로 올린다. 결과는 [보내기] 위 알림 칸의 [data-cs-detail-status] 줄에만 보이고,
 * 실패한 것은 '이유 · 사진 다시 저장' 단추로 다시 올린다(보낸 글은 그대로). 사진은 고르기 · 찍기(input file) · 끌어놓기 ·
 * 붙여넣기(칸이 펼쳐져 있을 때 화면 어디서든 Ctrl+V — 클립보드의 그림 파일만, 글은 글 칸으로) 세 길로 받는다.
 * 받은 사진은 원본 15MB 넘으면 거절, 브라우저에서 긴 변 2,048px · JPEG(투명 칸이 있으면 PNG)로 다시 그려 올린다 — EXIF ·
 * 위치 정보는 이때 빠진다(서버가 한 번 더 다시 그린다). 미리보기는 URL.createObjectURL 만(서버 주소는 쓰지 않는다).
 * fetch 는 try/catch + data.success 검사, 글은 textContent 만. CSRF 는 공용 csrf_bootstrap 의 fetch 래퍼가 붙인다.
 * 순수 함수(admit · fitBox · outType · photoBody)는 window.FOMS_CS_EDIT_DETAIL 로 내놓는다 — node 시험.
 */
(function () {
  'use strict';

  var TYPES = { 'image/jpeg': 'jpeg', 'image/jpg': 'jpeg', 'image/png': 'png', 'image/webp': 'webp' };
  var SOURCE_MAX = 15 * 1024 * 1024;  // 원본 상한 — 넘으면 화면이 거절
  var LONG_EDGE = 2048;

  /** 받을 사진인가 — 꼴(JPEG · PNG · WebP) · 원본 15MB · 개수. 받으면 '' , 아니면 까닭 코드. */
  function admit(meta, count, limits) {
    if (count >= (limits.maxPhotos || 5)) return 'photo_full';
    if (!TYPES[String(meta.type || '').toLowerCase()]) return 'photo_format';
    if (!(meta.size > 0)) return 'photo_empty';
    if (meta.size > SOURCE_MAX) return 'photo_source';
    return '';
  }

  /** 줄인 크기 — 긴 변이 longEdge 를 넘으면 비율대로 줄이고(정수), 아니면 그대로. */
  function fitBox(width, height, longEdge) {
    var edge = longEdge || LONG_EDGE;
    var w = Math.max(1, Math.round(width || 1));
    var h = Math.max(1, Math.round(height || 1));
    var scale = Math.min(1, edge / Math.max(w, h));
    return { width: Math.max(1, Math.round(w * scale)), height: Math.max(1, Math.round(h * scale)) };
  }

  /** 올릴 꼴 — 투명 칸이 있으면 PNG, 아니면 JPEG. */
  function outType(hasAlpha) {
    return hasAlpha ? 'image/png' : 'image/jpeg';
  }

  /** 사진 한 장 multipart 칸 — no_personal 은 '1' · '0'. */
  function photoBody(item) {
    return { field: 'photo', name: item.type === 'image/png' ? 'photo.png' : 'photo.jpg', no_personal: item.noPersonal ? '1' : '0' };
  }

  var REASONS = {
    photo_full: '사진은 5장까지예요.', photo_format: 'JPEG · PNG · WebP 사진만 돼요(HEIC · GIF · PDF 안 됨).',
    photo_empty: '빈 파일이에요.', photo_source: '원본이 15MB 를 넘어요.', photo_size: '줄여도 5MB 를 넘어요.',
    photo_read: '사진을 열지 못했어요.'
  };

  window.FOMS_CS_EDIT_DETAIL = { admit: admit, fitBox: fitBox, outType: outType, photoBody: photoBody, reasons: REASONS };
  if (window.__FOMS_CS_EDIT_DETAIL_BOUND) return;
  window.__FOMS_CS_EDIT_DETAIL_BOUND = true;

  var root = document.querySelector('[data-cs-detail]');
  var screen = document.querySelector('[data-cs-send]');
  if (!root || !screen) return;

  function safeJsonParse(value, fallback) {
    try { return JSON.parse(value); } catch (err) { return fallback; }
  }

  var limits = safeJsonParse(root.getAttribute('data-limits'), null) || { maxDetail: 1000, maxPhotos: 5, maxBytes: 5242880 };
  var photosOn = root.getAttribute('data-photos') === '1';
  var text = root.querySelector('[data-cs-detail-text]');
  var list = root.querySelector('[data-cs-detail-photos]');
  var again = root.querySelector('[data-cs-detail-save]');
  var items = [];
  var sent = false;
  var saving = false;
  var savedText = null;

  function status(kind, words) {
    var line = screen.querySelector('[data-cs-detail-status]');
    if (!line) return;
    line.className = 'small cs-detail__status cs-detail__status--' + kind;
    line.textContent = words;
  }

  function alive() {
    return items.filter(function (item) { return item.state !== 'gone'; });
  }

  function render() {
    if (!list) return;
    while (list.firstChild) list.removeChild(list.firstChild);
    alive().forEach(function (item) {
      var li = document.createElement('li');
      li.className = 'cs-detail__photo';
      var img = document.createElement('img');
      img.className = 'cs-detail__thumb';
      img.alt = '붙인 사진 미리보기';
      img.src = item.url;
      var label = document.createElement('label');
      label.className = 'small cs-detail__check';
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.className = 'form-check-input me-1';
      box.checked = item.noPersonal;
      box.disabled = item.state === 'saved' || item.state === 'saving';
      box.addEventListener('change', function () { item.noPersonal = box.checked; });
      label.appendChild(box);
      label.appendChild(document.createTextNode('손님 얼굴 · 이름 · 전화 · 주소가 안 보여요'));
      var state = document.createElement('span');
      state.className = 'small text-muted';
      state.textContent = { ready: '', saving: '올리는 중…', saved: '저장함', failed: '실패(다시 저장)' }[item.state] || '';
      var drop = document.createElement('button');
      drop.type = 'button';
      drop.className = 'btn btn-outline-danger btn-sm';
      drop.textContent = '빼기';
      drop.disabled = item.state === 'saving';
      drop.addEventListener('click', function () { remove(item); });
      [img, label, state, drop].forEach(function (el) { li.appendChild(el); });
      list.appendChild(li);
    });
  }

  async function call(url, init) {
    var response;
    var payload = null;
    try {
      response = await fetch(url, Object.assign({ credentials: 'same-origin', headers: { 'Accept': 'application/json' } }, init));
    } catch (err) {
      return { ok: false, data: null, error: '서버에 연결하지 못했어요. 네트워크를 확인해 주세요.' };
    }
    try {
      payload = await response.json();
    } catch (err) {
      return { ok: false, data: null, error: '응답을 읽지 못했어요.' };
    }
    if (!payload || typeof payload !== 'object') return { ok: false, data: null, error: '응답을 읽지 못했어요.' };
    return { ok: payload.success === true, data: payload.data || null, error: payload.error || '' };
  }

  function hasAlpha(ctx, width, height) {
    var pixels = ctx.getImageData(0, 0, width, height).data;
    for (var i = 3; i < pixels.length; i += 4) { if (pixels[i] < 255) return true; }
    return false;
  }

  async function decode(file) {
    if (typeof createImageBitmap === 'function') {
      try { return await createImageBitmap(file, { imageOrientation: 'from-image' }); } catch (err) { /* 아래 길로 */ }
    }
    return new Promise(function (resolve, reject) {
      var img = new Image();
      var url = URL.createObjectURL(file);
      img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('decode')); };
      img.src = url;
    });
  }

  async function shrink(file) {
    var picture = await decode(file);
    var size = fitBox(picture.width, picture.height, LONG_EDGE);
    var canvas = document.createElement('canvas');
    canvas.width = size.width;
    canvas.height = size.height;
    var ctx = canvas.getContext('2d');
    ctx.drawImage(picture, 0, 0, size.width, size.height);
    var type = outType(TYPES[file.type] !== 'jpeg' && hasAlpha(ctx, size.width, size.height));
    return new Promise(function (resolve, reject) {
      canvas.toBlob(function (blob) { return blob ? resolve(blob) : reject(new Error('encode')); }, type, 0.88);
    });
  }

  async function addFiles(files) {
    if (!photosOn) return;
    for (var i = 0; i < files.length; i += 1) {
      var why = admit(files[i], alive().length, limits);
      if (why) { status('warning', REASONS[why]); continue; }
      try {
        var blob = await shrink(files[i]);
        if (blob.size > limits.maxBytes) { status('warning', REASONS.photo_size); continue; }
        items.push({ blob: blob, type: blob.type, url: URL.createObjectURL(blob), noPersonal: false, state: 'ready', seq: null });
      } catch (err) {
        status('warning', REASONS.photo_read);
      }
    }
    render();
    if (sent) saveAll();
  }

  async function remove(item) {
    if (item.seq) {
      var res = await call(root.getAttribute('data-photo-url') + '/' + item.seq, { method: 'DELETE' });
      if (!res.ok) { status('warning', (res.data && res.data.message) || res.error || '사진을 지우지 못했어요.'); return; }
      status('secondary', res.data.message);
    }
    item.state = 'gone';
    URL.revokeObjectURL(item.url);
    render();
  }

  async function saveText() {
    var value = text ? text.value : '';
    if (value === (savedText === null ? '' : savedText)) return true;
    status('info', '이유 저장 중…');
    var res = await call(root.getAttribute('data-detail-url'), {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ detail: value })
    });
    if (!res.ok) { status('warning', (res.data && res.data.message) || res.error || '이유를 저장하지 못했어요.'); return false; }
    savedText = value;
    return true;
  }

  async function savePhoto(item) {
    var form = new FormData();
    var part = photoBody(item);
    form.append(part.field, item.blob, part.name);
    form.append('no_personal', part.no_personal);
    item.state = 'saving';
    render();
    var res = await call(root.getAttribute('data-photo-url'), { method: 'POST', body: form });
    item.state = res.ok ? 'saved' : 'failed';
    if (res.ok) item.seq = res.data.seq;
    render();
    return res;
  }

  async function saveAll() {
    if (saving) return;
    saving = true;
    var textOk = await saveText();
    var failed = 0;
    var last = '';
    var todo = alive().filter(function (item) { return item.state === 'ready' || item.state === 'failed'; });
    for (var i = 0; i < todo.length; i += 1) {
      var res = await savePhoto(todo[i]);
      if (!res.ok) { failed += 1; last = (res.data && res.data.message) || res.error; }
    }
    saving = false;
    var bad = !textOk || failed > 0;
    if (failed) status('warning', '사진 ' + failed + '장 실패(다시 저장) — ' + last);
    else if (textOk && (savedText || todo.length)) status('success', '저장했어요.');
    if (again) again.classList.toggle('d-none', !bad && sent && !dirty());
  }

  function dirty() {
    return text && text.value !== (savedText === null ? '' : savedText);
  }

  function onPaste(event) {
    if (!root.open || !photosOn || !event.clipboardData) return;
    var files = [];
    Array.prototype.forEach.call(event.clipboardData.items || [], function (entry) {
      if (entry.kind === 'file' && /^image\//.test(entry.type)) files.push(entry.getAsFile());
    });
    if (!files.length) return;  // 글은 글 칸으로(기본 붙여넣기)
    event.preventDefault();
    addFiles(files.filter(Boolean));
  }

  var drop = root.querySelector('[data-cs-detail-drop]');
  if (drop) {
    drop.addEventListener('dragover', function (event) { event.preventDefault(); drop.classList.add('is-over'); });
    drop.addEventListener('dragleave', function () { drop.classList.remove('is-over'); });
    drop.addEventListener('drop', function (event) {
      event.preventDefault();
      drop.classList.remove('is-over');
      addFiles(Array.prototype.slice.call((event.dataTransfer && event.dataTransfer.files) || []));
    });
  }
  var picker = root.querySelector('[data-cs-detail-file]');
  if (picker) {
    picker.addEventListener('change', function () {
      addFiles(Array.prototype.slice.call(picker.files || []));
      picker.value = '';
    });
  }
  document.addEventListener('paste', onPaste);
  root.addEventListener('toggle', function () {  // 접힌 칸은 높이를 못 잰다 — 펼칠 때 다시 잰다(send-screen.js 의 autosize)
    if (root.open && text) text.dispatchEvent(new Event('input'));
  });
  if (text) {
    text.addEventListener('input', function () {
      if (again && sent) again.classList.toggle('d-none', !dirty());
    });
  }
  if (again) again.addEventListener('click', saveAll);
  screen.addEventListener('cs-send:sent', function () {
    sent = true;
    saveAll();
  });
})();
