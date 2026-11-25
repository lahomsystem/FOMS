/**
 * 도면 작업실 [도면 전달]/[수정본 전달] 창 — 생산 · 시공 단계 수정본 화면(설계서 docs/specs/2026-11-25-production-stage-drawing-revision_SPEC.md
 * §2-3, D2). 창 안 [data-dfx-changed] 가 있을 때만(생산 · 시공 단계 — 템플릿이 그때만 그린다) 움직인다.
 *
 * - '바뀐 도면' 줄: 고른 전달 대기 시트 · 방식 · 교체 대상 · 파일 고르기가 바뀔 때마다 R1 미리 보기(drawing-fix-send.js)로 다시 그린다.
 * - 파일로 올린 도면: 파일마다 [도면 1 … n] [새 도면] 고르기(사장님 답 Q14 — 안 고르면 못 보냄, 서버도 400 PICK_TARGET).
 * - 인라인 submitTransfer 가 check(메모 · 고르기) · confirmSend(확인 한 번) · attachPicks · send(409 안전띠)를 부른다.
 * 자료(주문 · 확정 도면 · 도면 상태)는 지금 페이지의 #erp-drawing-workbench-config 를 읽는다.
 */
(function () {
  'use strict';

  if (window.FomsWorkbenchFix) { return; }   // ERP 셸 조각이 다시 읽어도 한 번만(G4)

  var NEW = 'NEW';
  var picks = [];
  var timer = null;

  function modal() { return document.getElementById('dwTransferModal'); }
  function changedEl() { var m = modal(); return m ? m.querySelector('[data-dfx-changed]') : null; }
  function active() { return !!(changedEl() && window.FomsFixSend); }

  function cfg() {
    try {
      var el = document.getElementById('erp-drawing-workbench-config');
      return (el && JSON.parse(el.textContent || '{}')) || {};
    } catch (e) {
      return {};
    }
  }

  function currentKeys() {
    return (cfg().drawing_files || []).map(function (f) { return (f && f.key) || ''; });
  }

  function chosenFiles() {
    var input = document.getElementById('dw-transfer-files');
    return input && input.files ? Array.prototype.slice.call(input.files) : [];
  }

  function checkedValues(selector) {
    return Array.prototype.map.call(document.querySelectorAll(selector), function (cb) { return cb.value; });
  }

  /** 지금 창에서 고른 것 → R1 질의 값(인라인 submitTransfer 가 서버에 보낼 값과 같은 규칙). */
  function sendPlan() {
    var mode = String((document.getElementById('dw-transfer-mode') || {}).value || 'APPEND').toUpperCase();
    return {
      sheets: checkedValues('#dw-transfer-pending-cards .dw-pending-checkbox:checked'),
      picks: chosenFiles().map(function (_f, i) { return picks[i] || ''; }),
      mode: mode,
      targets: mode === 'REPLACE' ? checkedValues('#dw-transfer-target-cards .drawing-target-checkbox:checked') : [],
      retransfer: String(cfg().drawing_status) === 'RETURNED' || mode === 'REPLACE' || mode === 'REPLACE_ALL'
    };
  }

  function refresh() {
    if (!active()) { return; }
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      window.FomsFixSend.preview(cfg().order_id, sendPlan()).then(function (plan) {
        window.FomsFixSend.setChanged(changedEl(), plan);
      });
    }, 200);
  }

  function chip(label, value, index) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'dfx-chip' + (picks[index] === value ? ' is-on' : '');
    btn.textContent = label;
    btn.setAttribute('aria-pressed', picks[index] === value ? 'true' : 'false');
    btn.addEventListener('click', function () {
      picks[index] = value;
      renderPicks();
      refresh();
    });
    return btn;
  }

  /** 파일마다 바꿀 도면 고르기 줄(파일 이름 + 도면 1 … n + 새 도면). 파일이 없으면 숨김. */
  function renderPicks() {
    var m = modal();
    var wrap = m ? m.querySelector('[data-dfx-picks]') : null;
    var rows = wrap ? wrap.querySelector('[data-dfx-pick-rows]') : null;
    if (!rows) { return; }
    var files = chosenFiles();
    var keys = currentKeys();
    picks = picks.slice(0, files.length);
    rows.textContent = '';
    files.forEach(function (file, i) {
      var row = document.createElement('div');
      row.className = 'dfx-pick-row';
      var name = document.createElement('div');
      name.className = 'dfx-pick-name';
      name.textContent = file.name;
      var chips = document.createElement('div');
      chips.className = 'dfx-pick-chips';
      keys.forEach(function (key, k) { if (key) { chips.appendChild(chip('도면 ' + (k + 1), key, i)); } });
      chips.appendChild(chip('새 도면', NEW, i));
      row.appendChild(name);
      row.appendChild(chips);
      rows.appendChild(row);
    });
    wrap.hidden = !files.length;
  }

  function noteError(show) {
    var m = modal();
    var err = m ? m.querySelector('[data-dfx-note-error]') : null;
    var note = document.getElementById('dw-transfer-note');
    if (err) { err.hidden = !show; }
    if (note) { note.classList.toggle('dfx-note-invalid', !!show); }
  }

  /** 보내기 전 화면 검사 — 메모 꼭 적기 · 파일마다 바꿀 도면. 막히면 글, 아니면 빈 글. */
  function check(note, fileCount) {
    if (!String(note || '').trim()) {
      noteError(true);
      return window.FomsFixSend.NOTE_MSG;
    }
    for (var i = 0; i < fileCount; i += 1) {
      if (!picks[i]) { return window.FomsFixSend.PICK_MSG; }
    }
    return '';
  }

  /** 확인 한 번 — 경고가 있으면 보내기 전 확인 창, 없으면 지금 확인 글. {ok, ack}. */
  function confirmSend(fallbackText) {
    return window.FomsFixSend.gate(cfg().order_id, sendPlan(), fallbackText, modal());
  }

  /** 올린 파일마다 고른 도면(replace_of)을 붙인다 — 모두 올라갔으면 차례로, 실패한 파일이 빠졌으면 이름으로 짝을 짓는다. */
  function attachPicks(created, originals) {
    var used = {};
    if ((created || []).length === (originals || []).length) {
      return created.map(function (f, i) { return Object.assign({}, f, { replace_of: picks[i] || '' }); });
    }
    return (created || []).map(function (f) {
      var index = Array.prototype.findIndex.call(originals || [], function (o, i) {
        return !used[i] && o && f && o.name === f.filename;
      });
      if (index < 0) { return f; }
      used[index] = true;
      return Object.assign({}, f, { replace_of: picks[index] || '' });
    });
  }

  function send(url, payload) {
    return window.FomsFixSend.post(url, payload, modal());
  }

  if (!window.__FOMS_DFX_WB_BOUND) {
    window.__FOMS_DFX_WB_BOUND = true;
    document.addEventListener('change', function (e) {
      var t = e.target;
      if (!t || !active()) { return; }
      if (t.id === 'dw-transfer-files') { renderPicks(); refresh(); }
      else if (t.id === 'dw-transfer-mode' || (t.classList && t.classList.contains('dw-pending-checkbox'))) { refresh(); }
    });
    document.addEventListener('click', function (e) {
      if (active() && e.target && e.target.closest && e.target.closest('#dw-transfer-target-cards .drawing-target-card')) {
        refresh();
      }
    });
    document.addEventListener('input', function (e) {
      if (e.target && e.target.id === 'dw-transfer-note' && String(e.target.value || '').trim()) { noteError(false); }
    });
    document.addEventListener('shown.bs.modal', function (e) {
      if (e.target && e.target.id === 'dwTransferModal' && active()) { renderPicks(); refresh(); }
    });
  }

  window.FomsWorkbenchFix = {
    active: active,
    check: check,
    confirmSend: confirmSend,
    attachPicks: attachPicks,
    send: send,
    refresh: refresh
  };
})();
