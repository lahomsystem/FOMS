/**
 * ERP 대시보드 [도면 전달] 창 — 생산 · 시공 단계 주문의 수정본 보내기(설계서 docs/specs/2026-11-25-production-stage-drawing-revision_SPEC.md
 * §2-3, D2 — 사장님 "두 곳 모두 되게 만들기"). 작업실 전달 창과 같은 규칙 · 같은 글 · 같은 함수:
 *
 * - 창을 열면 R1(GET /api/orders/<id>/drawing/fix/progress)로 단계를 묻고, 생산 · 시공 단계일 때만 '바뀐 도면' 줄 · 메모 "꼭 적기" ·
 *   파일마다 바꿀 도면 고르기(공용 drawing-fix-picks.js)를 켠다. 그 밖 단계는 아무것도 안 바뀐다(창 그대로).
 * - 생산 · 시공 단계에서는 전달 모드의 '교체할 기존 도면 선택' 칸을 숨긴다 — 파일마다 고른 도면이 자리다(서버도 교체 대상을 안 씀).
 * - 화면 검사(메모 · 고르기)와 확인 한 번(drawing-fix-send.js gate)은 파일을 올리기 **전에** — erp-dashboard-drawing.js 가 부른다.
 * - 보내기는 drawing-fix-send.js post(409 → 보내기 전 확인 창 → 물어본 도면 열쇠 ack 로 다시).
 */
(function () {
  'use strict';

  if (window.FomsDashboardFix) { return; }   // 셸 탭 전환으로 다시 읽어도 한 번만(G4)

  var state = { orderId: null, hotfix: false, drawings: [], retransfer: false };
  var timer = null;
  var picks = null;

  function modal() { return document.getElementById('erpDrawingTransferModal'); }
  function q(sel) { var m = modal(); return m ? m.querySelector(sel) : null; }
  function filesInput() { return document.getElementById('drawing-transfer-files'); }
  function chosenFiles() { var input = filesInput(); return input && input.files ? Array.prototype.slice.call(input.files) : []; }

  function pickBox() {
    if (!picks && window.FomsFixPicks) {
      picks = window.FomsFixPicks.create({
        rows: function () { return q('[data-dfx-dash-picks] [data-dfx-pick-rows]'); },
        wrap: function () { return q('[data-dfx-dash-picks]'); },
        files: chosenFiles,
        currents: function () { return state.drawings; },
        onChange: function () { refresh(); }
      });
    }
    return picks;
  }

  function active(orderId) {
    return !!(state.hotfix && window.FomsFixSend && pickBox() && (orderId == null || String(orderId) === String(state.orderId)));
  }

  /** 생산 · 시공 단계 칸 켜고 끄기 — 끄면 창은 전과 같다. */
  function show(on) {
    var m = modal();
    if (!m) { return; }
    Array.prototype.forEach.call(m.querySelectorAll('[data-dfx-dash-only]'), function (el) { el.hidden = !on; });
    if (!on) {
      var changed = q('[data-dfx-dash-changed]');
      if (changed) { changed.hidden = true; changed.textContent = ''; }
      var wrap = q('[data-dfx-dash-picks]');
      if (wrap) { wrap.hidden = true; }
      noteError(false);
      return;
    }
    var replaceWrap = document.getElementById('drawing-transfer-replace-wrap');
    if (replaceWrap) { replaceWrap.style.display = 'none'; }
  }

  function sendPlan() {
    return { sheets: [], picks: pickBox() ? picks.list() : [], mode: '', targets: [], retransfer: state.retransfer };
  }

  function refresh() {
    if (!active()) { return; }
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      window.FomsFixSend.preview(state.orderId, sendPlan()).then(function (plan) {
        window.FomsFixSend.setChanged(q('[data-dfx-dash-changed]'), plan);
      });
    }, 200);
  }

  /** 창을 열 때(openTransferDrawingModal) — 고름을 비우고 R1 로 단계 · 지금 도면을 받는다. */
  function open(orderId, isRetransfer) {
    state = { orderId: orderId, hotfix: false, drawings: [], retransfer: !!isRetransfer };
    if (pickBox()) { picks.reset(); }
    show(false);
    if (!window.FomsFixSend) { return Promise.resolve(false); }
    return window.fetch('/api/orders/' + orderId + '/drawing/fix/progress', { credentials: 'same-origin',
      headers: { 'Accept': 'application/json' } }).then(function (resp) { return resp.json(); }).then(function (data) {
      if (String(state.orderId) !== String(orderId) || !data || data.success !== true || !data.data || !data.data.hotfix) { return false; }
      state.hotfix = true;
      state.drawings = (data.data.drawings || []).map(function (d) { return { key: d.key, sheet_id: null }; });
      show(true);
      picks.render();
      refresh();
      return true;
    }).catch(function (err) {
      console.warn('[dashboard-fix] progress', err);   // 못 받으면 지금 창 그대로 — 서버가 400 · 409 로 막는다
      return false;
    });
  }

  function noteError(on) {
    var err = q('[data-dfx-dash-note-error]');
    var note = document.getElementById('drawing-transfer-note');
    if (err) { err.hidden = !on; }
    if (note) { note.classList.toggle('dfx-note-invalid', !!on); }
  }

  /** 올리기 전 화면 검사 — 메모 꼭 적기 · 파일마다 바꿀 도면. 막히면 글, 아니면 빈 글. */
  function check(note) {
    if (!String(note || '').trim()) {
      noteError(true);
      return window.FomsFixSend.NOTE_MSG;
    }
    return picks.missing() ? window.FomsFixSend.PICK_MSG : '';
  }

  function confirmSend() {
    var hotfix = window.FomsFixSend.HOTFIX_TEXT;
    return window.FomsFixSend.gate(state.orderId, sendPlan(), function (plan) {
      return [plan.changed_line, hotfix].filter(Boolean).join('\n\n');
    }, modal());
  }

  if (!window.__FOMS_DFX_DASH_BOUND) {
    window.__FOMS_DFX_DASH_BOUND = true;
    document.addEventListener('change', function (e) {
      if (e.target && e.target.id === 'drawing-transfer-files' && active()) { picks.render(); refresh(); }
    });
    document.addEventListener('input', function (e) {
      if (e.target && e.target.id === 'drawing-transfer-note' && String(e.target.value || '').trim()) { noteError(false); }
    });
  }

  window.FomsDashboardFix = {
    open: open,
    active: active,
    check: check,
    confirmSend: confirmSend,
    attach: function (created, originals) { return picks.attach(created, originals); },
    send: function (url, body) { return window.FomsFixSend.post(url, body, modal()); }
  };
})();
