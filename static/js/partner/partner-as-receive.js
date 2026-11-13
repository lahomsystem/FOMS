/**
 * 협력사 AS 접수 · 재접수 · 고치기 창(PARTNER-AS-02, 사용자 2026-11-13).
 *
 * 창 모양 · 글은 본사 주문 상세 "AS 접수" 창과 같다(partials/as_receive_modal.html). 열 때 GET {base} 로 할 일과 칸 값을 받는다.
 * 보내기: 파일이 없으면 접수 한 번(서버가 바로 AS방 PUSH). 파일이 있으면 defer_push 로 접수 → 파일을 한 개씩 {base}/files →
 * {base}/push. AS방 전송이 실패해도 접수는 남는다 — [AS방 다시 보내기].
 * 사진 · 동영상 고르기는 본사 photo-capture.js 의 카메라 · 갤러리 단추와 같은 동작이다. 그 파일은 화면의 모든 사진 칸에 카메라를
 * 강제로 붙이므로(협력사 다른 칸이 갤러리를 못 연다) 불러오지 않고 이 창 안에서만 같은 일을 한다. 순서 정하기 = as-attachment-order.js.
 * CSRF 헤더는 partials/shared/csrf_bootstrap.html 이 fetch 에 싣는다. 설계서 docs/specs/2026-11-13-partner-as-intake-edit-push_SPEC.md
 */
(function () {
  'use strict';

  var modal = document.querySelector('[data-pp-asm]');
  if (!modal) return;
  var $ = function (sel) { return modal.querySelector(sel); };
  var content = $('#ppAsContent');
  var note = $('#ppAsChangeNote');
  var recurrence = $('#ppAsRecurrence');
  var status = $('[data-pp-asm-status]');
  var submitBtn = $('[data-pp-asm-submit]');
  var retryBtn = $('[data-pp-asm-retry]');
  var preview = $('#ppAsPreview');
  var ctl = window.fomsAsAttachmentOrder ? window.fomsAsAttachmentOrder.mount(preview) : null;
  var state = { base: '', view: null, busy: false, retryNote: '' };
  var TITLES = { new: 'AS 접수', reintake: 'AS 재접수', edit: 'AS 접수 수정' };

  function say(text, isError) {
    status.textContent = text || '';
    status.classList.toggle('pp-status--error', !!isError);
  }

  async function call(url, options) {
    var resp = await fetch(url, Object.assign({ credentials: 'same-origin' }, options || {}));
    var data = null;
    try { data = await resp.json(); } catch (e) { data = null; }
    if (!data || !data.success) {
      var err = new Error((data && data.error) || '지금은 처리할 수 없습니다. 잠시 뒤 다시 시도해 주세요.');
      err.data = data && data.data;
      throw err;
    }
    return data.data || {};
  }

  function postJson(url, body) {
    return call(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  }

  function addFiles(files) {
    if (!files || !files.length) return;
    if (ctl) ctl.addFiles(Array.prototype.slice.call(files));
  }

  function pickedFiles() { return ctl ? ctl.getFiles() : []; }

  function showFor(mode) {
    Array.prototype.forEach.call(modal.querySelectorAll('[data-pp-asm-show]'), function (el) {
      el.hidden = el.getAttribute('data-pp-asm-show').split(' ').indexOf(mode) < 0;
    });
  }

  function fillPrev(prev) {
    var values = prev ? {
      ordinal: prev.ordinal ? prev.ordinal + '번째 AS' : '', received: prev.received, completed: prev.completed,
      symptom: prev.symptom, rounds: prev.rounds ? prev.rounds + '차까지 처리' : ''
    } : {};
    Array.prototype.forEach.call(modal.querySelectorAll('[data-pp-asm-prev]'), function (row) {
      var value = values[row.getAttribute('data-pp-asm-prev')] || '';
      row.querySelector('[data-pp-asm-val]').textContent = value;
      row.hidden = !value;
    });
  }

  function fillPicks(photos) {
    var wrap = $('[data-pp-asm-picks]');
    var list = $('[data-pp-asm-pick-list]');
    list.textContent = '';
    (photos || []).forEach(function (p) {
      var li = document.createElement('li');
      li.className = 'pp-photo';
      var label = document.createElement('label');
      label.className = 'pp-photo__pick';
      if (p.is_image) {
        var img = document.createElement('img');
        img.src = p.thumb_url;
        img.alt = p.filename;
        img.loading = 'lazy';
        label.appendChild(img);
      } else {
        var name = document.createElement('span');
        name.className = 'pp-photo__file';
        name.textContent = p.filename;
        label.appendChild(name);
      }
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.value = String(p.id);
      box.setAttribute('aria-label', p.filename + ' 를 AS 에 붙이기');
      label.appendChild(box);
      li.appendChild(label);
      list.appendChild(li);
    });
    wrap.hidden = !(photos && photos.length);
    countPicks();
  }

  function countPicks() {
    var n = modal.querySelectorAll('[data-pp-asm-pick-list] input:checked').length;
    $('[data-pp-asm-pick-count]').textContent = n ? '· ' + n + '장 고름' : '';
  }

  function fill(view) {
    var mode = view.mode;
    $('[data-pp-asm-title]').textContent = TITLES[mode] + (mode === 'reintake' && view.cycle_no > 1 ? ' · ' + view.cycle_no + '번째 AS' : '');
    $('[data-pp-asm-order]').textContent = '#' + view.order_id + ' ' + (view.customer_name || '') + (view.product ? ' · ' + view.product : '');
    $('[data-pp-asm-pushed]').textContent = view.push && view.push.sent_label ? 'AS방에는 ' + view.push.sent_label + ' 에 보냈어요.' : '';
    $('[data-pp-asm-submit-label]').textContent = mode === 'edit' ? '고친 내용 저장' : 'AS 접수 확인';
    $('[data-pp-asm-load-hint]').hidden = true;
    showFor(mode);
    content.value = mode === 'edit' ? (view.content || '') : '';
    note.value = '';
    recurrence.checked = false;
    fillPrev(view.prev);
    fillPicks(view.construction_photos);
    if (ctl) ctl.clear();
    retryBtn.hidden = true;
    submitBtn.disabled = false;
    say('');
  }

  function open(base) {
    if (state.busy) return;
    state.base = base;
    say('');
    call(base).then(function (view) {
      if (!view.mode) { window.alert('지금은 AS 를 접수할 수 없습니다. 시공이 끝난 주문만 받습니다.'); return; }
      state.view = view;
      fill(view);
      modal.hidden = false;
      document.body.classList.add('pp-asm-open');
      try { content.focus({ preventScroll: true }); } catch (e) { content.focus(); }
    }).catch(function (err) { window.alert(err.message); });
  }

  function close() {
    if (state.busy) return;
    modal.hidden = true;
    document.body.classList.remove('pp-asm-open');
    if (state.done) window.location.reload();
  }

  function key() { return 'pp-as-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8); }

  async function uploadAll(receptionId, files) {
    var failed = [];
    for (var i = 0; i < files.length; i += 1) {
      say('파일 올리는 중 ' + (i + 1) + ' / ' + files.length + ' …');
      var f = files[i];
      try {
        var small = window.PartnerShrink ? await window.PartnerShrink.file(f) : f;
        var body = new FormData();
        body.append('file', small, small.name || f.name);
        body.append('as_log_id', receptionId);
        body.append('sort_order', String(i));
        await call(state.base + '/files', { method: 'POST', body: body });
      } catch (err) {
        failed.push((f.name || '파일') + ' — ' + (f.size > 50 * 1024 * 1024 ? '50MB 를 넘습니다' : err.message));
      }
    }
    return failed;
  }

  async function push(changeNote) {
    say('AS방으로 보내는 중…');
    try {
      var data = await postJson(state.base + '/push', { change_note: changeNote });
      return { ok: true, note: data.push_note };
    } catch (err) {
      return { ok: false, note: err.message };
    }
  }

  function finish(result, failed) {
    state.done = true;
    var lines = [];
    if (failed.length) lines.push('못 올린 파일: ' + failed.join(', '));
    lines.push(result.note || '');
    say(lines.join('\n'), !result.ok || failed.length > 0);
    retryBtn.hidden = !!result.ok;
    submitBtn.disabled = true;
    if (result.ok && !failed.length) window.setTimeout(function () { window.location.reload(); }, 900);
  }

  async function submit() {
    if (state.busy || !state.view) return;
    var mode = state.view.mode;
    var text = content.value.trim();
    if (!text) { say('AS 내용을 적어 주세요.', true); content.focus(); return; }
    var changeNote = note.value.trim();
    if (mode === 'edit' && !changeNote) { say('바뀐 내용을 한 줄 적어 주세요.', true); note.focus(); return; }
    var files = pickedFiles();
    state.busy = true;
    submitBtn.disabled = true;
    say(mode === 'edit' ? '고친 내용을 저장하는 중…' : '접수하는 중…');
    var body = new FormData();
    body.append('content', text);
    body.append('idempotency_key', key());
    if (mode === 'edit') body.append('change_note', changeNote);
    if (mode === 'reintake' && recurrence.checked) body.append('recurrence', '1');
    Array.prototype.forEach.call(modal.querySelectorAll('[data-pp-asm-pick-list] input:checked'), function (box) {
      body.append('construction_photo_ids', box.value);
    });
    if (files.length) body.append('defer_push', '1');
    try {
      var done = await call(state.base + (mode === 'edit' ? '/edit' : ''), { method: 'POST', body: body });
      state.retryNote = changeNote;
      if (!files.length) {
        finish({ ok: done.push_sent === true, note: done.push_note || '' }, done.photo_error ? [done.photo_error] : []);
      } else {
        var failed = await uploadAll(done.reception_log_id, files);
        finish(await push(changeNote), failed);
      }
    } catch (err) {
      say(err.message, true);
      submitBtn.disabled = false;
    } finally {
      state.busy = false;
    }
  }

  async function retry() {
    if (state.busy) return;
    state.busy = true;
    retryBtn.disabled = true;
    var result = await push(state.retryNote);
    state.busy = false;
    retryBtn.disabled = false;
    finish(result, []);
  }

  function clipboardImages(ev) {
    var items = (ev.clipboardData && ev.clipboardData.items) || [];
    var out = [];
    for (var i = 0; i < items.length; i += 1) {
      if (items[i].kind === 'file' && /^image\//.test(items[i].type)) {
        var f = items[i].getAsFile();
        if (f) out.push(new File([f], f.name && f.name !== 'image.png' ? f.name : 'paste-' + Date.now() + '-' + i + '.png', { type: f.type }));
      }
    }
    return out;
  }

  var camera = $('#ppAsFiles');
  var gallery = $('.foms-photo-capture__gallery-input');
  $('[data-action="camera"]').addEventListener('click', function () { camera.click(); });
  $('[data-action="gallery"]').addEventListener('click', function () { gallery.click(); });
  [camera, gallery].forEach(function (input) {
    input.addEventListener('change', function () { addFiles(input.files); input.value = ''; });
  });
  modal.addEventListener('paste', function (ev) {
    var active = document.activeElement;
    if (active && (active === content || active === note)) return;
    var files = clipboardImages(ev);
    if (!files.length) return;
    ev.preventDefault();
    addFiles(files);
  });
  modal.addEventListener('change', function (ev) { if (ev.target.closest('[data-pp-asm-pick-list]')) countPicks(); });
  modal.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') close(); });
  modal.addEventListener('click', function (ev) { if (ev.target.closest('[data-pp-asm-close]')) close(); });
  $('[data-pp-asm-load-prev]').addEventListener('click', function () {
    var prev = state.view && state.view.prev;
    if (!prev || !prev.symptom) return;
    content.value = prev.symptom;
    $('[data-pp-asm-load-hint]').hidden = false;
    content.focus();
  });
  submitBtn.addEventListener('click', submit);
  retryBtn.addEventListener('click', retry);
  if (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) $('[data-pp-asm-paste]').hidden = true;

  document.addEventListener('click', function (ev) {
    var opener = ev.target.closest('[data-pp-as-open]');
    if (opener) { ev.preventDefault(); ev.stopPropagation(); open(opener.getAttribute('data-pp-as-open')); return; }
    var pusher = ev.target.closest('[data-pp-as-push]');
    if (!pusher || state.busy) return;
    ev.preventDefault();
    pusher.disabled = true;
    postJson(pusher.getAttribute('data-pp-as-push'), {}).then(function (data) {
      window.alert(data.push_note || 'AS방에 보냈습니다.');
      window.location.reload();
    }).catch(function (err) { window.alert(err.message); pusher.disabled = false; });
  });
})();
