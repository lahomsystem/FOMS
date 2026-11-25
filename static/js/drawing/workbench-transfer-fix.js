/**
 * 도면 작업실 [도면 전달]/[수정본 전달] 창 — 생산 · 시공 단계 수정본 화면(설계서 docs/specs/2026-11-25-production-stage-drawing-revision_SPEC.md
 * §2-3, D2). 창 안 [data-dfx-changed] 가 있을 때만(생산 · 시공 단계 — 템플릿이 그때만 그린다) 움직인다.
 *
 * - '바뀐 도면' 줄: 고른 전달 대기 시트 · 방식 · 교체 대상 · 파일 고르기가 바뀔 때마다 R1 미리 보기(drawing-fix-send.js)로 다시 그린다.
 * - 파일로 올린 도면: 파일마다 [도면 1 … n] [새 도면] 고르기(사장님 답 Q14 — 안 고르면 못 보냄, 서버도 400 PICK_TARGET).
 *   고름은 차례가 아니라 **파일마다** 묶는다 — 미리 보기 [x]로 파일을 빼면 그 파일 고름만 사라진다(D2 검토 A). 다른 파일이 이미 고른
 *   도면 · 고른 전달 대기 시트의 새 판이 바꾸는 도면은 단추를 끈다(검토 D). 창을 열 때마다 · 주문이 바뀌면 고름을 비운다(검토 B).
 * - 확인 글은 '바뀐 도면' 계산(R1 = 서버 계획) 하나로만 말한다(검토 C).
 * - 인라인 submitTransfer 가 check(메모 · 고르기) · confirmSend(확인 한 번) · attachPicks · send(409 안전띠)를 부른다.
 * 자료(주문 · 확정 도면 · 도면 상태)는 지금 페이지의 #erp-drawing-workbench-config 를 읽는다.
 */
(function () {
  'use strict';

  if (window.FomsWorkbenchFix) { return; }   // ERP 셸 조각이 다시 읽어도 한 번만(G4)

  var NEW = 'NEW';
  var picks = {};          // 파일 열쇠(이름 · 크기 · 고친 때 · 같은 파일 차례) → 고른 값(도면 key | 'NEW')
  var pickOrder = null;    // 고름이 속한 주문
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

  function reset() { picks = {}; pickOrder = cfg().order_id; }
  function sameOrder() { if (pickOrder !== cfg().order_id) { reset(); } }

  function currentFiles() { return (cfg().drawing_files || []).filter(function (f) { return f && f.key; }); }

  function chosenFiles() {
    var input = document.getElementById('dw-transfer-files');
    return input && input.files ? Array.prototype.slice.call(input.files) : [];
  }

  /** 파일마다 열쇠 — 같은 파일이 두 번 올라오면 차례(#n)로 가른다. */
  function fileKeys(files) {
    var seen = {};
    return files.map(function (f) {
      var base = [f.name, f.size, f.lastModified].join('|');
      seen[base] = (seen[base] || 0) + 1;
      return base + '#' + seen[base];
    });
  }

  function pickList() { return fileKeys(chosenFiles()).map(function (k) { return picks[k] || ''; }); }

  function checkedValues(selector) {
    return Array.prototype.map.call(document.querySelectorAll(selector), function (cb) { return cb.value; });
  }

  /** 지금 창에서 고른 것 → R1 질의 값(인라인 submitTransfer 가 서버에 보낼 값과 같은 규칙). */
  function sendPlan() {
    var mode = String((document.getElementById('dw-transfer-mode') || {}).value || 'APPEND').toUpperCase();
    return {
      sheets: checkedValues('#dw-transfer-pending-cards .dw-pending-checkbox:checked'),
      picks: pickList(),
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

  /** 이 파일이 못 고르는 도면 — 다른 파일이 고른 도면 · 고른 전달 대기 시트의 새 판이 바꾸는 도면. */
  function takenFor(fileKey) {
    var sheets = checkedValues('#dw-transfer-pending-cards .dw-pending-checkbox:checked');
    var taken = {};
    currentFiles().forEach(function (f) { if (f.sheet_id && sheets.indexOf(f.sheet_id) >= 0) { taken[f.key] = true; } });
    Object.keys(picks).forEach(function (k) { if (k !== fileKey && picks[k] !== NEW) { taken[picks[k]] = true; } });
    return taken;
  }

  function chip(label, value, fileKey, taken) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'dfx-chip' + (picks[fileKey] === value ? ' is-on' : '');
    btn.textContent = label;
    btn.disabled = value !== NEW && !!taken[value];
    btn.setAttribute('aria-pressed', picks[fileKey] === value ? 'true' : 'false');
    btn.addEventListener('click', function () {
      picks[fileKey] = value;
      renderPicks();
      refresh();
    });
    return btn;
  }

  /** 파일마다 바꿀 도면 고르기 줄(파일 이름 + 도면 1 … n + 새 도면). 빠진 파일의 고름 · 이제 못 고르는 고름은 지운다. */
  function renderPicks() {
    var m = modal();
    var wrap = m ? m.querySelector('[data-dfx-picks]') : null;
    var rows = wrap ? wrap.querySelector('[data-dfx-pick-rows]') : null;
    if (!rows) { return; }
    sameOrder();
    var files = chosenFiles();
    var keys = fileKeys(files);
    Object.keys(picks).forEach(function (k) { if (keys.indexOf(k) < 0) { delete picks[k]; } });
    keys.forEach(function (k) { if (picks[k] && picks[k] !== NEW && takenFor(k)[picks[k]]) { delete picks[k]; } });
    rows.textContent = '';
    files.forEach(function (file, i) {
      var taken = takenFor(keys[i]);
      var row = document.createElement('div');
      row.className = 'dfx-pick-row';
      var name = document.createElement('div');
      name.className = 'dfx-pick-name';
      name.textContent = file.name;
      var chips = document.createElement('div');
      chips.className = 'dfx-pick-chips';
      currentFiles().forEach(function (f, n) { chips.appendChild(chip('도면 ' + (n + 1), f.key, keys[i], taken)); });
      chips.appendChild(chip('새 도면', NEW, keys[i], taken));
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
  function check(note) {
    if (!String(note || '').trim()) {
      noteError(true);
      return window.FomsFixSend.NOTE_MSG;
    }
    sameOrder();
    return pickList().some(function (p) { return !p; }) ? window.FomsFixSend.PICK_MSG : '';
  }

  /** 확인 한 번 — 작업된 도면 · 시공 대기면 보내기 전 확인 창, 아니면 '바뀐 도면' 줄 + 생산 확인 글. {ok, ack}. */
  function confirmSend() {
    var hotfix = window.FomsFixSend.HOTFIX_TEXT;
    return window.FomsFixSend.gate(cfg().order_id, sendPlan(), function (plan) {
      return [plan.changed_line, hotfix].filter(Boolean).join('\n\n');
    }, modal());
  }

  /** 올린 파일마다 고른 도면(replace_of)을 붙인다 — 모두 올라갔으면 차례로, 실패한 파일이 빠졌으면 이름으로 짝을 짓는다. */
  function attachPicks(created, originals) {
    var list = Array.prototype.slice.call(originals || []);
    var keys = fileKeys(list);
    var used = {};
    return (created || []).map(function (f, i) {
      var index = (created.length === list.length) ? i : list.findIndex(function (o, j) {
        return !used[j] && o && f && o.name === f.filename;
      });
      if (index < 0) { return f; }
      used[index] = true;
      return Object.assign({}, f, { replace_of: picks[keys[index]] || '' });
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
      if (t.id === 'dw-transfer-files' || (t.classList && t.classList.contains('dw-pending-checkbox'))) { renderPicks(); refresh(); }
      else if (t.id === 'dw-transfer-mode') { refresh(); }
    });
    document.addEventListener('click', function (e) {
      var t = e.target && e.target.closest ? e.target : null;
      if (!t || !active()) { return; }
      // 미리 보기 [x](removeFileFromPreview)는 change 를 안 낸다 — 붙잡는 단계에서 보고, 지운 뒤 다시 그린다
      if (t.closest('#dw-transfer-preview [data-file-index]')) { window.setTimeout(function () { renderPicks(); refresh(); }, 0); }
      else if (t.closest('#dw-transfer-target-cards .drawing-target-card')) { refresh(); }
    }, true);
    document.addEventListener('input', function (e) {
      if (e.target && e.target.id === 'dw-transfer-note' && String(e.target.value || '').trim()) { noteError(false); }
    });
    document.addEventListener('show.bs.modal', function (e) {
      if (e.target && e.target.id === 'dwTransferModal' && active()) { reset(); renderPicks(); refresh(); }
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
