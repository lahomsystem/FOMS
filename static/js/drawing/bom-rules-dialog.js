/**
 * 도면 마법사 — 자재표 계산 규칙 창(계산 칸 밖에 뜨는 대화 상자).
 *
 * 보고서 2026-10-25 보통-4·큼-3: 규칙 18칸이 계산 칸 맨 아래에 펼쳐져 칸 길이가 2,030px 까지 늘고,
 * 가장 눈에 띄는 파란 [규칙 저장]을 잘못 누르기 쉬웠다. 그래서 칸에는 '규칙 2판 · 도면팀·관리자만 고침
 * [규칙 창 열기]' 한 줄만 두고, 편집은 이 창에서 한다(편집 칸은 bom-rules.js 의 renderEditor 를 그대로 쓴다).
 * - 창이 열린 동안 키 입력이 뒤의 그림 단축키(Delete·숫자키·Ctrl+Z 등)로 새지 않게 막는다. 초점이 창 밖(body)으로
 *   빠져도 막는다(window 잡는 단계). Ctrl+S 는 도면을 저장하지 않고 '[규칙 저장] 단추로' 안내만 한다 — 실화면 QA
 *   2026-10-25 V1: 창을 연 채 Ctrl+S 를 누르면 도면 저장이 초점을 창 밖으로 빼서 그 뒤 Ctrl+Z 가 흐린 바탕 뒤 그림을
 *   되돌렸고, 규칙을 고치다 습관처럼 누른 Ctrl+S 로 규칙이 아니라 도면이 전달 대기함에 들어가 헷갈렸다.
 * - 저장하면 창을 닫는다. 남이 먼저 고쳐 새 값을 다시 받았으면 창을 연 채로 새 값을 보여 준다.
 *
 * window.FomsBomRulesDialog = { open(info, onSaved(next), toast, refocus?) }
 *   refocus: 창을 닫을 때 연 단추가 다시 그려져 없어졌으면 부른다(새 단추로 포커스를 돌린다).
 */
(function () {
  'use strict';
  if (window.FomsBomRulesDialog) { return; }

  var dlg = null, title = null, body = null, returnFocus = null, refocusFn = null, toastFn = null, canEdit = false;
  var SAVE_NOTE = '규칙은 [규칙 저장] 단추로 저장합니다. 도면 저장(Ctrl+S)은 규칙 창을 닫은 뒤에 해 주세요.';
  var SAVE_NOTE_VIEW = '규칙 창이 열려 있어 도면을 저장하지 않았습니다. 창을 닫은 뒤 Ctrl+S 를 눌러 주세요.';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text != null) { e.textContent = text; }
    return e;
  }

  function close() {
    if (!dlg) { return; }
    if (dlg.close) { try { dlg.close(); } catch (_) { dlg.removeAttribute('open'); } } else { dlg.removeAttribute('open'); }
    if (!dlg.close) { restoreFocus(); }   // close 이벤트가 없는 옛 브라우저
  }
  function restoreFocus() {
    if (returnFocus && returnFocus.isConnected !== false && typeof returnFocus.focus === 'function') { returnFocus.focus(); }
    else if (refocusFn) { refocusFn(); }
    returnFocus = null;
  }

  function isSaveKey(e) { return (e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S' || e.code === 'KeyS'); }   // 한글 자판은 code
  /** 창이 열린 채 누른 Ctrl+S — 도면 저장(마법사 save)까지 가지 않게 막고 안내만 한다(꾹 누름 반복은 안내 한 번). */
  function blockSave(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!e.repeat && toastFn) { toastFn(canEdit ? SAVE_NOTE : SAVE_NOTE_VIEW); }
  }
  /** window 잡는 단계(문서 단축키보다 먼저) — 초점이 창 밖(body)으로 빠진 채 누른 키도 뒤 그림에 닿지 않게.
      창 안의 키는 창의 keydown 이 맡는다(입력 칸 글자·Esc 닫기는 그대로). */
  function guardOutside(e) {
    if (!dlg || !dlg.open || dlg.contains(e.target)) { return; }
    if (isSaveKey(e)) { blockSave(e); return; }
    e.stopPropagation();
  }

  function build() {
    dlg = el('dialog', 'dws-dialog dws-calc-rules-dialog dws-ui');
    dlg.id = 'dws-calc-rules-dialog';
    dlg.setAttribute('aria-labelledby', 'dws-calc-rules-title');
    var wrap = dlg.appendChild(el('div', 'dws-dialog-body'));
    var head = wrap.appendChild(el('div', 'dws-calc-rules-head'));
    title = head.appendChild(el('h2', 'dws-dialog-title', '계산 규칙 숫자'));
    title.id = 'dws-calc-rules-title';
    var x = head.appendChild(el('button', 'dws-calc-close', '✕'));
    x.type = 'button';
    x.title = '닫기 (Esc)';
    x.setAttribute('aria-label', '규칙 창 닫기');
    x.addEventListener('click', close);
    body = wrap.appendChild(el('div', 'dws-calc-rules-body'));
    dlg.addEventListener('keydown', function (e) {
      if (isSaveKey(e)) { blockSave(e); return; }
      e.stopPropagation();   // 뒤 캔버스 단축키로 새지 않게(Esc 닫기는 대화 상자 기본 동작)
    });
    if (typeof window.addEventListener === 'function') { window.addEventListener('keydown', guardOutside, true); }
    dlg.addEventListener('close', restoreFocus);
    (document.getElementById('dws-root') || document.body).appendChild(dlg);
  }

  function fill(info, onSaved, toast) {
    toastFn = toast || null;
    canEdit = !!info.can_edit;
    title.textContent = '계산 규칙 숫자 · ' + window.FomsBomRules.labelName(info.label);
    var row = window.FomsBomRules.renderEditor(body, info, function (next, conflict) {
      onSaved(next);
      if (conflict) { fill(next, onSaved, toast); } else { close(); }
    }, toast);
    var done = el('button', 'dws-btn', '닫기');
    done.type = 'button';
    done.addEventListener('click', close);
    row.insertBefore(done, row.firstChild);
  }

  /** 규칙 창 열기 — info 는 계산 칸이 받아 둔 규칙(GET bom-rules). */
  function open(info, onSaved, toast, refocus) {
    if (!info || !window.FomsBomRules) { return false; }
    if (!dlg) { build(); }
    returnFocus = document.activeElement;
    refocusFn = refocus || null;
    fill(info, onSaved, toast);
    if (dlg.showModal) { try { dlg.showModal(); } catch (_) { dlg.setAttribute('open', ''); } } else { dlg.setAttribute('open', ''); }
    return true;
  }

  window.FomsBomRulesDialog = { open: open };
})();
