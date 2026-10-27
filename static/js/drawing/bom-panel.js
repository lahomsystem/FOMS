/**
 * 도면 마법사 — 자재표 계산 칸(오른쪽에 여닫는 칸, 그림자 판 — 화면 글은 '참고용').
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.6
 * - 시트마다 전체 폭·깊이·천장 높이·제품 종류·손잡이·모듈 목록을 받아 [SR][EP][DOOR][옷봉][마이다]
 *   줄을 계산해 보여 주고, 시트에 사람이 친 자재표와 줄마다 맞춰 본다.
 * - 그림자 판(calc.mode 'shadow'): 도면팀이 규칙을 확인하기 전에는 시트에 넣지도, 복사하게 하지도 않는다.
 *   사람이 따로 친 자재표와 계산을 맞춰 본 기록(시트 calc)이 규칙을 검증하는 자료이기 때문이다.
 * - 입력을 처음 바꿀 때 시트에 calc 를 만든다(열어 보기만 해서는 시트가 바뀌지 않는다).
 * - 배치(보고서 2026-10-25 '계산 칸 배치 안 A'): 제목 아래 '계산 결과'를 고정하고(bom-results.js)
 *   그 아래만 스크롤한다 — 모듈(펼침) · 제품·치수(값이 차면 한 줄 요약) · 계산식 보기(접힘) · 규칙 한 줄.
 *   입력 묶음은 bom-form.js, 규칙 편집은 칸 밖 규칙 창(bom-rules-dialog.js)이 맡는다.
 * - 화면 글은 짧게, 하는 일로 쓴다(사용자 피드백 2026-10-27 '머리 글이 어색하다'): '시험 계산' → '참고용',
 *   '결과 · 맞춰 보기' → '계산 결과', '줄마다 계산 근거' → '계산식 보기', 규칙 줄 '규칙 2판 사용 중 [규칙 고치기]'.
 * - 칸 폭은 왼쪽 가장자리 손잡이로 280~420px 사이에서 바꾼다(이 브라우저에만 기억, 없으면 340).
 *
 * window.FomsBomPanel = { init(opts), sync(), toggle(), roomPlan(o) }
 *   opts: { host, button, getSheet(), getProduct(sheet), canSave(), onChange(), toast(msg), onOpenChange(open)? }
 *   roomPlan: 칸을 연 뒤 시트가 칸에 가리면 폭 맞춤·제품 목록 접기를 정한다(마법사 onOpenChange 가 쓴다).
 */
(function () {
  'use strict';
  if (window.FomsBomPanel) { return; }

  var NOTE = '참고용 계산입니다. 자재표는 지금처럼 시트에 직접 쳐 주세요. 둘을 맞춰 본 기록으로 계산 규칙을 다듬고, ' +
    '도면팀이 규칙을 확인하면 시트에 넣는 단추를 엽니다.';
  var WIDTH_KEY = 'dws-calc-width', W_MIN = 280, W_MAX = 420, W_DEF = 340;
  var C = null, R = null, F = null, B = null, D = null, ctx = null, info = null, loading = null, isOpen = false;
  var els = {}, inp = null, lastSheetId = null, lastCalc;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text != null) { e.textContent = text; }
    return e;
  }
  function editable() { return !!(ctx && ctx.canSave()); }

  /** 입력 한 칸이 바뀜 — 처음이면 시트에 calc 를 붙이고, 다시 계산하고, 저장할 것으로 표시한다. */
  function edit(key, value) {
    var s = ctx.getSheet();
    if (!s || !editable()) { return; }
    inp[key] = value;
    if (!s.calc || s.calc.in !== inp) { s.calc = { in: inp, mode: 'shadow' }; }
    lastCalc = s.calc;
    refresh();
    ctx.onChange();
  }

  /** 시트 글자 상자에서 [SR]·[DOOR] 머리글 아래 줄을 읽는다(맞춰 보기 재료). */
  function sheetRows(s) {
    var texts = (s.objects || []).filter(function (o) { return o.type === 'text'; }).map(function (o) { return o.text; });
    return C.parseBom(texts);
  }

  /** 다시 계산 — 시트에 calc 가 있으면 계산 글자·규칙 판도 갱신한다(저장 때 같이 나간다). */
  function refresh() {
    var s = ctx.getSheet();
    if (!s || !info || !inp || !els.why) { return; }
    var lines = C.calc(inp, info.rules);
    if (s.calc && s.calc.in === inp) { s.calc.out = C.toText(lines); s.calc.rules = info.label; }
    B.renderTop(els.top, lines, sheetRows(s), C);
    B.renderWhy(els.why, lines);
    F.refresh();
    // 위 결과 칸이 자라면 아래 스크롤 구역이 줄어 치던 칸이 가려질 수 있다 — 치는 칸을 보이는 곳에 둔다
    var ae = document.activeElement;
    if (ae && ae !== els.body && els.body.contains(ae) && ae.scrollIntoView) { ae.scrollIntoView({ block: 'nearest' }); }
  }

  /** 규칙 한 줄 — '규칙 2판 사용 중 [규칙 고치기]'. 고칠 수 없는 사람(도면팀·관리자 밖)은 [규칙 보기].
      편집은 칸 밖 규칙 창에서(규칙 창이 보기만 하는 사람에게 '도면팀·관리자만 고칠 수 있습니다'를 보인다). */
  function renderRulesRow() {
    var row = els.body.appendChild(el('div', 'dws-calc-rules-row'));
    row.appendChild(el('span', 'dws-calc-rules-text', (R.labelName(info.label) || '계산 규칙') + ' 사용 중'));
    var btn = els.rulesBtn = row.appendChild(el('button', 'dws-btn dws-calc-small', info.can_edit ? '규칙 고치기' : '규칙 보기'));
    btn.type = 'button';
    btn.title = info.can_edit ? '고친 숫자는 도면팀 전체 계산에 바로 적용됩니다' : '규칙은 도면팀·관리자만 고칠 수 있습니다';
    btn.addEventListener('click', function () {
      D.open(info, function (next) { info = next; render(); }, ctx.toast, function () { if (els.rulesBtn) { els.rulesBtn.focus(); } });
    });
  }

  function message(text) {
    els.top.hidden = true;
    els.body.appendChild(el('p', 'dws-calc-empty', text));
  }

  function render() {
    var s = ctx.getSheet();
    els.body.textContent = '';
    els.why = null;
    els.rulesBtn = null;
    lastSheetId = s ? s.id : null;
    lastCalc = s ? s.calc : undefined;
    if (!info) { message(loading ? '계산 규칙을 불러오는 중입니다…' : '계산 규칙을 불러오지 못했습니다. 칸을 닫았다가 다시 열어 주세요.'); return; }
    if (!s) { message('왼쪽에서 제품을 골라 시트를 먼저 여세요.'); return; }
    var product = ctx.getProduct(s);
    inp = (s.calc && s.calc.in) ? s.calc.in : C.emptyInputs(info.rules, product);
    if (!Array.isArray(inp.mods)) { inp.mods = []; }
    els.top.hidden = false;
    F.build(els.body, { C: C, inp: inp, rules: info.rules, product: product, editable: editable(), edit: edit, render: render, sheetId: s.id });
    var why = F.fold(els.body, 'why');
    why.label.textContent = '계산식 보기';
    els.why = why.body;
    renderRulesRow();
    refresh();
  }

  /** 칸 폭(280~420px)은 CSS 변수 --dws-calc-w 로만 바꾼다. keep 이면 이 브라우저에 기억한다. */
  function setWidth(w, keep) {
    w = Math.max(W_MIN, Math.min(W_MAX, Math.round(w) || W_DEF));
    ctx.host.style.setProperty('--dws-calc-w', w + 'px');
    els.grip.setAttribute('aria-valuenow', String(w));
    if (keep) { try { window.localStorage.setItem(WIDTH_KEY, String(w)); } catch (_) { /* 기억 못 해도 이번 폭은 쓴다 */ } }
    return w;
  }
  /** 칸 왼쪽 가장자리 손잡이 — 끌거나 ←/→ 키로 폭을 바꾼다. */
  function initGrip() {
    var grip = els.grip = ctx.host.appendChild(el('div', 'dws-calc-grip'));
    grip.tabIndex = 0;
    grip.title = '끌어서 칸 폭 바꾸기(280~420)';
    grip.setAttribute('role', 'separator');
    grip.setAttribute('aria-orientation', 'vertical');
    grip.setAttribute('aria-label', '계산 칸 폭');
    grip.setAttribute('aria-valuemin', String(W_MIN));
    grip.setAttribute('aria-valuemax', String(W_MAX));
    var saved = W_DEF;
    try { saved = Number(window.localStorage.getItem(WIDTH_KEY)) || W_DEF; } catch (_) { saved = W_DEF; }
    var cur = setWidth(saved, false), startX = 0, startW = cur, drag = false;
    grip.addEventListener('pointerdown', function (e) {
      drag = true; startX = e.clientX; startW = cur;
      if (grip.setPointerCapture) { try { grip.setPointerCapture(e.pointerId); } catch (_) { /* 잡지 못해도 끌기는 된다 */ } }
      e.preventDefault();
    });
    grip.addEventListener('pointermove', function (e) { if (drag) { cur = setWidth(startW + (startX - e.clientX), false); } });
    function end() { if (drag) { drag = false; cur = setWidth(cur, true); } }
    grip.addEventListener('pointerup', end);
    grip.addEventListener('pointercancel', end);
    grip.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') { return; }
      e.preventDefault();
      e.stopPropagation();   // 뒤 캔버스의 '고른 그림 1px 옮기기'로 새지 않게
      cur = setWidth(cur + (e.key === 'ArrowLeft' ? 10 : -10), true);
    });
  }

  /** 칸 열기·닫기. 처음 열 때 규칙 숫자를 받는다(성능 가드 G2: 쓸 때 받기). */
  function setOpen(on) {
    if (on === isOpen) { return; }
    isOpen = on;
    ctx.host.hidden = !on;
    if (ctx.button) { ctx.button.setAttribute('aria-expanded', String(on)); ctx.button.classList.toggle('dws-btn-on', on); }
    if (on) {
      if (!info && !loading) {
        loading = R.load().then(function (d) { info = d; loading = null; if (isOpen) { render(); } });
      }
      render();
    }
    if (ctx.onOpenChange) { ctx.onOpenChange(on); }   // 칸이 보인 뒤 — 마법사가 roomPlan 으로 폭 맞춤·제품 목록 접기(큼-2)
  }
  function toggle() { setOpen(!isOpen); }

  /* 칸을 연 뒤 시트를 보이게 할 일(보고서 큼-2 · 실화면 QA 2026-10-25) — 화면 폭(1600)이 아니라 '시트 오른쪽이
     칸에 가리는가'로 정한다(1920 배율 100% 에서도 [마이다]가 '[마'로 잘렸다). 폭 맞춤만으로 배율이 FOLD_BELOW
     (80% — 100% 에서 20px 인 시트 자재표 글자가 16px) 아래로 떨어질 때만 왼쪽 제품 목록도 접는다
     (1920: 목록은 두고 89% · 1680/1600/1366: 접고 85/80/64%).
     o: { zoom, avail(캔버스 폭 − 좌우 여백), stageW, productsOpen } → null(가리지 않음) | { zoom(맞춤만 했을 때), fold } */
  var FOLD_BELOW = 0.8;
  function roomPlan(o) {
    if (!o || !(o.avail > 0) || !(o.stageW > 0) || o.stageW * o.zoom <= o.avail + 1) { return null; }
    var fit = Math.min(1, o.avail / o.stageW);
    return { zoom: fit, fold: !!o.productsOpen && fit < FOLD_BELOW };
  }

  /** 마법사가 시트를 다시 그릴 때마다 부른다 — 시트·calc 가 바뀌었으면 새로 그리고, 아니면 맞춰 보기만 갱신. */
  function sync() {
    if (!isOpen || !ctx) { return; }
    var s = ctx.getSheet();
    if (!s || s.id !== lastSheetId || s.calc !== lastCalc) { render(); return; }
    refresh();
  }

  function init(opts) {
    C = window.FomsBomCalc;
    R = window.FomsBomRules;
    F = window.FomsBomForm;
    B = window.FomsBomResults;
    D = window.FomsBomRulesDialog;
    ctx = opts;
    if (!C || !R || !F || !B || !D || !ctx || !ctx.host) { return false; }
    var head = ctx.host.appendChild(el('div', 'dws-calc-head'));
    head.appendChild(el('span', 'dws-calc-title', '자재표 계산'));
    var about = head.appendChild(el('button', 'dws-calc-info', 'ⓘ'));
    about.type = 'button';
    about.title = '이 칸은 무엇을 하나요?';
    about.setAttribute('aria-label', '자재표 계산 안내');
    about.setAttribute('aria-expanded', 'false');
    about.setAttribute('aria-controls', 'dws-calc-note');
    var badge = head.appendChild(el('span', 'dws-calc-badge', '참고용'));
    badge.title = '계산만 보여 주고 시트에는 넣지 않습니다';
    var close = head.appendChild(el('button', 'dws-calc-close', '✕'));
    close.type = 'button';
    close.title = '닫기';
    close.setAttribute('aria-label', '자재표 계산 닫기');
    close.addEventListener('click', function () { setOpen(false); });
    els.note = ctx.host.appendChild(el('p', 'dws-calc-note', NOTE));
    els.note.id = 'dws-calc-note';
    els.note.hidden = true;
    about.addEventListener('click', function () {
      els.note.hidden = !els.note.hidden;
      about.setAttribute('aria-expanded', String(!els.note.hidden));
    });
    els.top = ctx.host.appendChild(el('div', 'dws-calc-top'));   // 계산 결과(아래 칸과 따로 스크롤)
    els.top.hidden = true;
    els.body = ctx.host.appendChild(el('div', 'dws-calc-body'));
    initGrip();
    if (ctx.button) { ctx.button.addEventListener('click', toggle); }
    return true;
  }

  window.FomsBomPanel = { init: init, sync: sync, toggle: toggle, roomPlan: roomPlan };
})();
