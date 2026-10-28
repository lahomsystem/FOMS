/**
 * 도면 마법사 V2 — 칸 머리 위 글자(자재표 · 특이 사항 · 강조 문구)를 지켜본다: 글이 바뀌어 크기가 달라지면 다시 배치하고,
 * 손으로 옮긴 글자는 고정한다(시트 폼 v2_pin).
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §4 — 사용자 보고 2026-10-28 '자재 입력 시 자동 간격 조절 안 됨' ·
 *   '특이 사항 추가 시 간격이 자동으로 돌아가 버려'(질문 창 답: 손으로 벌린 간격이 되돌아감). 스테이징 주문 4385: [SR] 칸에 1000*2450 을 쓰자
 *   글 폭이 35 → 97px 인데 옆 [EP] 는 그 자리에 남아 겹쳤다(글을 고쳐도 다시 배치가 돌지 않았다). 손으로 벌려 놓으면 특이 사항을 넣을 때
 *   다시 배치가 자재표를 원래 자리로 돌렸다(글자는 고정이 없었다).
 * - 글이 바뀌면(자동 배치 모드 · 칸으로 정리한 시트): 그린 뒤(render — 글자 폭을 잰 뒤) 칸 머리 위 글자 크기 지문(id · 폭 · 높이)이
 *   달라졌으면 0.45초 뒤 한 번 다시 배치한다(글을 쓰는 중 · 끄는 중이면 기다린다). 시트를 열거나 바꿀 때는 지문만 새로 잡는다.
 *   되돌리기는 글 고치기가 남긴 한 번. 고정된 자재표 줄은 그 자리에서 앞 열에 붙은 열만 오른쪽으로 민다(사람이 벌린 틈은 그대로).
 * - 손으로 6px 넘게 옮기면(자동 배치 모드 · '손으로 옮긴 그림은 고정' 켬): 그 글자를 고정한다 — 자재표는 한 열만 옮겨도 줄 전체, 특이 사항 ·
 *   강조 문구는 그 글자만. 고정 글자는 장애물이 되고(v2-plan) 그림이 겹치면 비켜 다시 놓인다. 자재표 열을 옆 열 위에 놓으면 뒤 열을
 *   민다(스테이징 4385 실화면 — [DOOR] 를 끌어 [옷봉] 위에 놓으면 겹친 채 남았다). [고정 풀고 모두 다시]가 함께 푼다(v2-shell).
 *
 * window.FomsV2Text = { init(api), sig(sheet) → 지문 글자, respace(bom) → 민 열 수, pin(sheet, ids) → 새로 고정한 수, WAIT }
 */
(function () {
  'use strict';
  if (window.FomsV2Text) { return; }

  var WAIT = 450;
  var api = null, seen = { sheet: '', sig: '' }, timer = 0, drawn = {};   // drawn = 마지막으로 그린 칸 머리 위 글자 자리(끌기 전)

  function S() { return window.FomsV2Slots; }
  function heads(sheet) {
    return ((sheet && sheet.objects) || []).filter(function (o) { var r = S().role(o); return r === 'bom' || r === 'note' || r === 'stamp'; });
  }
  function laid(sh) { return !!(sh && sh.form && sh.form.v2_layout); }

  /** 칸 머리 위 글자 크기 지문 — id · 폭 · 높이(자리는 빼서 배치가 옮겨도 그대로, 글이 바뀌면 달라진다). */
  function sig(sheet) {
    return heads(sheet).map(function (o) { var b = S().textBox(o); return o.id + ':' + Math.round(b.w) + 'x' + Math.round(b.h); }).sort().join(' ');
  }

  /** 자재표 열을 왼쪽부터 — 앞 열들 끝 + COLGAP 보다 붙은 열만 오른쪽으로 민다(잠긴 열은 그대로 두고 그 뒤를 민다). */
  function respace(bom) {
    var gap = window.FomsV2Layout.COLGAP, cols = (bom || []).slice().sort(function (a, b) { return a.x - b.x; }), n = 0, end = -Infinity;
    cols.forEach(function (c) {
      var min = Math.round(end + gap);
      if (c.x < min && !c.locked) { c.x = min; n += 1; }
      var b = S().textBox(c);
      end = Math.max(end, b.x + b.w);
    });
    return n;
  }

  /** 손으로 옮긴 칸 머리 위 글자를 고정(form.v2_pin) — 자재표는 줄 전체. → 새로 고정한 수 */
  function pin(sheet, ids) {
    var all = heads(sheet), list = all.filter(function (o) { return (ids || []).indexOf(o.id) >= 0; }), map = S().parsePins(sheet.form.v2_pin), n = 0;
    if (list.some(function (o) { return S().role(o) === 'bom'; })) { list = list.concat(all.filter(function (o) { return S().role(o) === 'bom'; })); }
    list.forEach(function (o) { if (!map[o.id]) { map[o.id] = true; n += 1; } });
    if (!n) { return 0; }
    var text = S().formatPins(map, sheet.objects);
    if (text) { sheet.form.v2_pin = text; } else { delete sheet.form.v2_pin; }
    return n;
  }

  function run() {
    timer = 0;
    var core = api.core, sh = core.sheet();
    if (!sh || sh.id !== seen.sheet || api.mode() !== 'auto' || !laid(sh)) { return; }
    if (core.editing() || core.dragging()) { timer = window.setTimeout(run, WAIT); return; }
    var bom = sh.objects.filter(function (o) { return S().role(o) === 'bom'; }), pins = S().parsePins(sh.form.v2_pin);
    var pinned = api.settings().lockMoved !== false && bom.some(function (o) { return pins[o.id]; });
    if (pinned && respace(bom)) { core.markDirty(); core.redraw(); }   // 고정된 줄은 그 자리에서
    api.arrange('text', {});
  }

  /** 그린 뒤 — 시트가 같고 글자 크기 지문이 바뀌었으면 다시 배치를 예약한다. */
  function check() {
    var core = api.core, sh = core.sheet();
    if (!sh) { return; }
    drawn = {};
    heads(sh).forEach(function (o) { drawn[o.id] = [o.x || 0, o.y || 0]; });
    var s = sig(sh);
    if (seen.sheet !== sh.id) { seen = { sheet: sh.id, sig: s }; return; }   // 시트를 열거나 바꿨다 — 지문만
    if (s === seen.sig) { return; }
    seen.sig = s;
    if (api.mode() !== 'auto' || !laid(sh) || !core.canSave()) { return; }
    if (timer) { window.clearTimeout(timer); }
    timer = window.setTimeout(run, WAIT);
  }

  /** 끌기 · 크기 바꾸기를 마쳤다 — 칸 머리 위 글자가 6px 넘게(그림과 같은 MOVE_TOL — 더블클릭하다 손이 밀린 것은 빼고) 옮겨졌으면
      고정하고 그림이 겹치면 비켜 다시 놓는다. */
  function moved(d) {
    var core = api.core, sh = core.sheet(), tol = S().MOVE_TOL;
    if (!sh || api.mode() !== 'auto' || api.settings().lockMoved === false || !laid(sh) || !core.canSave()) { return; }
    var ids = ((d && d.ids) || []).filter(function (id) {
      var o = sh.objects.filter(function (x) { return x.id === id; })[0], was = drawn[id];
      return !!o && (!was || Math.abs((o.x || 0) - was[0]) > tol || Math.abs((o.y || 0) - was[1]) > tol);
    }), mine = heads(sh).filter(function (o) { return ids.indexOf(o.id) >= 0; });
    if (!mine.length) { return; }
    pin(sh, ids);
    var bom = sh.objects.filter(function (o) { return S().role(o) === 'bom'; });
    if (mine.some(function (o) { return S().role(o) === 'bom'; }) && respace(bom)) { core.markDirty(); core.redraw(); }   // 옆 열 위에 놓았으면 뒤 열을 민다
    api.arrange('pin', {});   // 이미 고정된 글자를 또 옮겨도 — 그림이 새 자리를 비켜 간다
  }

  function init(a) {
    api = a;
    api.core.on('render', check);
    api.core.on('moved', moved);
  }

  window.FomsV2Text = { init: init, sig: sig, respace: respace, pin: pin, WAIT: WAIT };
})();
