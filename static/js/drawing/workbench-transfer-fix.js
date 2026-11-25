/**
 * 도면 작업실 [도면 전달]/[수정본 전달] 창 — 생산 · 시공 단계 수정본 화면(설계서 docs/specs/2026-11-25-production-stage-drawing-revision_SPEC.md
 * §2-3, D2). 창 안 [data-dfx-changed] 가 있을 때만(생산 · 시공 단계 — 템플릿이 그때만 그린다) 움직인다.
 *
 * - '바뀐 도면' 줄: 고른 전달 대기 시트 · 방식 · 교체 대상 · 파일 고르기가 바뀔 때마다 R1 미리 보기(drawing-fix-send.js)로 다시 그린다.
 * - 파일로 올린 도면: 파일마다 [도면 1 … n] [새 도면] 고르기(공용 drawing-fix-picks.js — 고름은 파일마다, 다른 파일이 고른 도면 ·
 *   고른 전달 대기 시트의 새 판이 바꾸는 도면은 단추 꺼짐). 창을 열 때마다 · 주문이 바뀌면 고름을 비운다(D2 검토 A · B · D).
 * - 확인 글은 '바뀐 도면' 계산(R1 = 서버 계획) 하나로만 말한다(검토 C).
 * - 인라인 submitTransfer 가 check(메모 · 고르기) · confirmSend(확인 한 번) · attachPicks · send(409 안전띠)를 부른다.
 * 자료(주문 · 확정 도면 · 도면 상태)는 지금 페이지의 #erp-drawing-workbench-config 를 읽는다.
 */
(function () {
  'use strict';

  if (window.FomsWorkbenchFix) { return; }   // ERP 셸 조각이 다시 읽어도 한 번만(G4)

  var pickOrder = null;    // 고름이 속한 주문
  var timer = null;

  function modal() { return document.getElementById('dwTransferModal'); }
  function changedEl() { var m = modal(); return m ? m.querySelector('[data-dfx-changed]') : null; }
  function active() { return !!(changedEl() && window.FomsFixSend && window.FomsFixPicks); }

  function cfg() {
    try {
      var el = document.getElementById('erp-drawing-workbench-config');
      return (el && JSON.parse(el.textContent || '{}')) || {};
    } catch (e) {
      return {};
    }
  }

  function chosenFiles() {
    var input = document.getElementById('dw-transfer-files');
    return input && input.files ? Array.prototype.slice.call(input.files) : [];
  }

  function checkedValues(selector) {
    return Array.prototype.map.call(document.querySelectorAll(selector), function (cb) { return cb.value; });
  }

  var picks = null;
  function pickBox() {
    if (!picks && window.FomsFixPicks) {
      picks = window.FomsFixPicks.create({
        rows: function () { var w = pickWrap(); return w ? w.querySelector('[data-dfx-pick-rows]') : null; },
        wrap: pickWrap,
        files: chosenFiles,
        currents: function () { return (cfg().drawing_files || []).filter(function (f) { return f && f.key; }); },
        blockedSheets: function () { return checkedValues('#dw-transfer-pending-cards .dw-pending-checkbox:checked'); },
        onChange: function () { refresh(); }
      });
    }
    if (picks && pickOrder !== cfg().order_id) { picks.reset(); pickOrder = cfg().order_id; }
    return picks;
  }
  function pickWrap() { var m = modal(); return m ? m.querySelector('[data-dfx-picks]') : null; }
  function renderPicks() { if (pickBox()) { picks.render(); } }

  /** 지금 창에서 고른 것 → R1 질의 값(인라인 submitTransfer 가 서버에 보낼 값과 같은 규칙). */
  function sendPlan() {
    var mode = String((document.getElementById('dw-transfer-mode') || {}).value || 'APPEND').toUpperCase();
    return {
      sheets: checkedValues('#dw-transfer-pending-cards .dw-pending-checkbox:checked'),
      picks: pickBox() ? picks.list() : [],
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
    return pickBox() && picks.missing() ? window.FomsFixSend.PICK_MSG : '';
  }

  /** 확인 한 번 — 작업된 도면 · 시공 대기면 보내기 전 확인 창, 아니면 '바뀐 도면' 줄 + 생산 확인 글. {ok, ack}. */
  function confirmSend() {
    var hotfix = window.FomsFixSend.HOTFIX_TEXT;
    return window.FomsFixSend.gate(cfg().order_id, sendPlan(), function (plan) {
      return [plan.changed_line, hotfix].filter(Boolean).join('\n\n');
    }, modal());
  }

  function attachPicks(created, originals) { return pickBox() ? picks.attach(created, originals) : created; }

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
      if (e.target && e.target.id === 'dwTransferModal' && active()) {
        if (pickBox()) { picks.reset(); }
        renderPicks();
        refresh();
      }
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
