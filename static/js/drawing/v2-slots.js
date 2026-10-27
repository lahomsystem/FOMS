/**
 * 도면 마법사 V2 — 시트 객체를 칸으로 묶는다(순수 계산, 화면을 건드리지 않는다).
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §2 · §4
 * - 칸은 저장하지 않고 객체에서 읽는다: 그림 = part.label, 자재표 = 첫 줄이 '[SR]' 같은 대괄호 머리글인 글자,
 *   특이 사항 = id 가 'n-'(실선 · 제작) · 'nc-'(점선 · 현장/고객)인 글자, 강조 문구 = id 가 'st-' 인 글자.
 * - '확신이 낮으면 미분류로'(lowToUnsorted)를 끄면 미분류 그림은 AI 짐작(part.ai) 칸으로 간다.
 * - 고정 = 잠금 · 돌림 · (lockMoved 일 때) 자동 배치가 놓은 자리(part.arr)에서 사람이 옮긴 그림 — 배치가 옮기지 않는다.
 *   옮김은 6px 넘게(MOVE_TOL): 그림을 누르다 손이 조금 밀려도 Konva 는 3px 부터 끌기로 친다 — 1px 로 재던 때는 누르기만 해도
 *   고정이 되어 다시 배치가 그 그림을 건너뛰었다(스테이징 주문 4385, 2026-10-27).
 * - 주방이면 큰 그림을 정면 · 입체 두 칸으로 나눈다(kitchen).
 * - AI 칸 짐작(opts.guess = form.v2_ai): 세부 종류 확신은 낮아도(미분류) 칸 확신(큰 그림 = 정면 + 입체 확률 합,
 *   상세 = 서랍 단면 + 부품 상세 합)이 문턱을 넘은 그림은 그 칸에 놓는다. 이름표는 미분류 그대로 — 사람이 고르기 전까지 '확인'.
 * - 칸 이름(title)은 칸에 든 그림 종류로 짓는다(제품 이름이 아니다).
 * - 칸 글자(letters): 칸으로 정리한 시트는 종이 위 칸 상자를 왼쪽 위부터 읽는 순서로 A, B, C… — 큰 그림부터 붙였더니
 *   틀에 따라 상세가 왼쪽에 와서 종이 위 순서가 B → A → D, 그 밑 C 로 뒤섞였다(생산팀이 'B 그림'을 찾기 어렵다, 2026-10-27).
 *
 * window.FomsV2Slots = { group(objects, opts) → g, role(o), noteKind(o), textBox(o), isFixed(o, opts), moved(o),
 *   detectKind(productText), KINDS, letters(g, kitchen, laid), slotBox(g, key), readOrder(items), title(key, g, kitchen),
 *   parseGuess(text), formatGuess(map, objects) }
 *   g = { photo, main, iso, detail, plan, unsorted (그림 객체 배열), bom, notes (글자), stamp (글자|null), free, fixed: {id:true},
 *         labels: { id: 보이는 이름표 }, lay: { id: 칸 · 짝을 정한 이름표(짐작이면 짐작 칸의 이름표) }, guess: { id: {fam, conf} } }
 */
(function () {
  'use strict';
  if (window.FomsV2Slots) { return; }

  var FRONT = { '정면·내부': 1, '정면·도어': 1 };
  var ISO = { '입체·내부': 1, '입체·도어': 1 };
  var DETAIL = { '서랍 단면': 1, '부품 상세': 1 };
  // AI 칸 짐작 글자 — f 정면 · i 입체 · d 상세. 짐작 칸에 놓을 때 AI 첫 짐작이 다른 칸이면 대표 이름표로 놓는다.
  var FAM = { f: '정면·내부', i: '입체·내부', d: '부품 상세' };
  var FAM_OF = { '정면·내부': 'f', '정면·도어': 'f', '입체·내부': 'i', '입체·도어': 'i', '서랍 단면': 'd', '부품 상세': 'd' };
  var GUESS_MAX = 500;   // 폼 한 칸 글자 한도(서버 _MAX_FORM_VALUE_LEN)
  var MOVE_TOL = 6;      // 이만큼(px)까지 어긋난 것은 옮긴 것으로 치지 않는다(끌기 시작 3px + 손떨림)
  var KINDS = [
    { key: 'closet', name: '붙박이장류' },
    { key: 'kitchen', name: '주방' },
    { key: 'fridge', name: '냉장고장' },
    { key: 'other', name: '그 밖 가구' }
  ];
  var KITCHEN_WORDS = /부엌|주방|싱크|아일랜드|하부장|상부장|홈카페|홈바/;

  function isBom(o) { return !!o && o.type === 'text' && /^\s*\[[^\]\n]{1,12}\]/.test(String(o.text || '')); }

  /** 객체 역할 — 'image' · 'bom' · 'note' · 'stamp' · 'free'(그 밖 글자 · 도형 · 펜). */
  function role(o) {
    if (!o) { return 'free'; }
    if (o.type === 'image') { return 'image'; }
    if (o.type !== 'text') { return 'free'; }
    var id = String(o.id || '');
    if (/^st-/.test(id)) { return 'stamp'; }
    if (/^nc?-/.test(id)) { return 'note'; }
    return isBom(o) ? 'bom' : 'free';
  }

  /** 특이 사항 종류 — 'make'(실선 · 제작) · 'site'(점선 · 현장/고객). */
  function noteKind(o) { return /^nc-/.test(String((o && o.id) || '')) ? 'site' : 'make'; }

  /** 그려 보기 전 글자 폭 어림 — 한글·한자는 크기의 0.95, 그 밖은 0.58(새 시트 자리표는 폭이 1 로 저장돼 있다). */
  function estWidth(text, size) {
    var best = 0;
    String(text || '').split('\n').forEach(function (line) {
      var w = 0;
      for (var i = 0; i < line.length; i++) { w += line.charCodeAt(i) >= 0x1100 ? size * 0.95 : size * 0.58; }
      best = Math.max(best, w);
    });
    return Math.max(1, Math.round(best));
  }

  /** 글자 상자(스테이지 좌표) — 마법사 글자 노드와 같은 셈: 폭 = 그린 자연폭 w(없으면 어림), 높이 = 줄 수 × 크기 × 1.25. */
  function textBox(o) {
    var size = o.size > 0 ? o.size : 20;
    var lines = String(o.text || '').split('\n').length;
    var w = o.w > 1 ? o.w : estWidth(o.text, size);
    return { x: o.x || 0, y: o.y || 0, w: w, h: Math.round(lines * size * 1.25) };
  }

  function rotated(o) { var r = Math.round(o.rotation || 0) % 360; return r !== 0; }

  /** 자동 배치가 놓은 자리(part.arr)에서 사람이 옮기거나 크기를 바꿨나(MOVE_TOL 넘게). arr 가 없으면 false. */
  function moved(o) {
    var a = o && o.part && o.part.arr, t = MOVE_TOL;
    if (!a || a.length !== 4) { return false; }
    return Math.abs(a[0] - o.x) > t || Math.abs(a[1] - o.y) > t || Math.abs(a[2] - o.w) > t || Math.abs(a[3] - o.h) > t;
  }

  function isFixed(o, opts) {
    var p = opts || {};
    return !!o.locked || rotated(o) || (p.lockMoved !== false && moved(o));
  }

  function labelOf(o, opts) {
    var p = (o && o.part) || {};
    var label = p.label || '미분류';
    if (label === '미분류' && opts && opts.lowToUnsorted === false && p.ai && p.ai !== '미분류' && p.ai !== '그림 아님') {
      label = p.ai;
    }
    return label;
  }

  function slotOf(label, kitchen) {
    if (label === '사진') { return 'photo'; }
    if (FRONT[label]) { return 'main'; }
    if (ISO[label]) { return kitchen ? 'iso' : 'main'; }
    if (DETAIL[label]) { return 'detail'; }
    if (label === '평면·상판') { return 'plan'; }
    return 'unsorted';
  }

  /** form.v2_ai 글자 → { id: { fam: 'f'|'i'|'d', conf: 0~1 } }. 'o-ab12=f68 o-cd34=d55' 꼴(V2 만 쓰고, 서버는 폼 글자로만 본다). */
  function parseGuess(text) {
    var out = {};
    String(text || '').split(' ').forEach(function (part) {
      var m = /^([^\s=]{1,48})=([fid])(\d{1,3})$/.exec(part);
      if (m) { out[m[1]] = { fam: m[2], conf: Math.min(100, Number(m[3])) / 100 }; }
    });
    return out;
  }

  /** { id: {fam, conf} } → 폼 글자. 시트에 없는 그림은 빼고 폼 한 칸 한도 안에서 끊는다. */
  function formatGuess(map, objects) {
    var have = {}, out = '';
    (objects || []).forEach(function (o) { if (o && o.type === 'image') { have[o.id] = true; } });
    Object.keys(map || {}).forEach(function (id) {
      var v = map[id], part = id + '=' + (v && v.fam) + Math.round(((v && v.conf) || 0) * 100);
      if (have[id] && FAM[v.fam] && out.length + part.length + 1 <= GUESS_MAX) { out += (out ? ' ' : '') + part; }
    });
    return out;
  }

  /** objects → 칸 묶음. opts: { lowToUnsorted (기본 true), lockMoved (기본 true), kitchen, guess (parseGuess 결과) } */
  function group(objects, opts) {
    var o2 = opts || {}, guess = o2.guess || {};
    var g = { photo: [], main: [], iso: [], detail: [], plan: [], unsorted: [], bom: [], notes: [], stamp: null,
      free: [], fixed: {}, labels: {}, lay: {}, guess: {} };
    (objects || []).forEach(function (o) {
      var r = role(o);
      if (r === 'bom') { g.bom.push(o); return; }
      if (r === 'note') { g.notes.push(o); return; }
      if (r === 'stamp') { if (g.stamp) { g.free.push(o); } else { g.stamp = o; } return; }
      if (r !== 'image') { g.free.push(o); return; }
      var label = labelOf(o, o2), lay = label, p = o.part || {}, gs = guess[o.id];
      if (label === '미분류' && p.src !== 'user' && o2.lowToUnsorted !== false && gs && FAM[gs.fam]) {
        lay = FAM_OF[p.ai] === gs.fam ? p.ai : FAM[gs.fam];
        g.guess[o.id] = gs;
      }
      g.labels[o.id] = label;
      g.lay[o.id] = lay;
      if (isFixed(o, o2)) { g.fixed[o.id] = true; }
      g[slotOf(lay, !!o2.kitchen)].push(o);
    });
    return g;
  }

  /** 칸 이름 — 칸에 든 그림 종류로 짓는다. 큰 그림 = 정면 · 입체, 상세 = 서랍 단면 · 부품 상세. 빈 칸은 기본 이름. */
  function title(key, g, kitchen) {
    var have = {};
    (g[key] || []).forEach(function (o) {
      var l = (g.lay && g.lay[o.id]) || g.labels[o.id], f = FAM_OF[l];
      have[f === 'f' ? '정면' : (f === 'i' ? '입체' : l)] = true;
    });
    function pick(names) { return names.filter(function (n) { return have[n]; }).join(' · '); }
    if (key === 'main' || key === 'iso') { return pick(['정면', '입체']) || (key === 'iso' ? '입체' : (kitchen ? '정면' : '큰 그림')); }
    if (key === 'detail') { return pick(['서랍 단면', '부품 상세']) || '상세'; }
    if (key === 'plan') { return '평면 · 상판'; }
    if (key === 'photo') { return '실측 사진'; }
    return '기타 그림';
  }

  /** 제품 이름 · 시트 이름 → 제품 종류 키(주방 짝 규칙과 같은 말 — 냉장고는 주방이 아니다). */
  function detectKind(text) {
    var t = String(text || '');
    if (/냉장고/.test(t)) { return 'fridge'; }
    if (KITCHEN_WORDS.test(t)) { return 'kitchen'; }
    return 'closet';
  }

  /** 칸 상자(스테이지 좌표) — 고정 그림을 뺀 객체들의 테두리(다 고정이면 전부). 종이 위 칸 머리 자리(v2-paper.js)와 같은 셈.
      고정 그림은 칸 밖에 있을 수 있다 — 넣으면 머리가 다른 칸 위로 길게 뻗었다. 빈 칸은 null. */
  function slotBox(g, key) {
    var list = g[key] || [], loose = list.filter(function (o) { return !g.fixed[o.id]; });
    var use = loose.length ? loose : list, x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    if (!use.length) { return null; }
    use.forEach(function (o) {
      var b = o.type === 'text' ? textBox(o) : { x: o.x || 0, y: o.y || 0, w: o.w || 0, h: o.h || 0 };
      x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y); x1 = Math.max(x1, b.x + b.w); y1 = Math.max(y1, b.y + b.h);
    });
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }

  /** 축(p 'y' · s 'h' = 위아래, p 'x' · s 'w' = 좌우)을 따라 처음 나오는 틈에서 둘로 나눈다 — 틈이 없으면 null. */
  function cut(items, p, s) {
    var sorted = items.slice().sort(function (a, b) { return a.box[p] - b.box[p]; }), end = -Infinity;
    for (var i = 0; i < sorted.length; i++) {
      if (i > 0 && sorted[i].box[p] >= end) { return [sorted.slice(0, i), sorted.slice(i)]; }
      end = Math.max(end, sorted[i].box[p] + sorted[i].box[s]);
    }
    return null;
  }

  /** 읽는 순서 — 위아래로 틈이 있으면 위 무리부터, 없으면(위아래가 겹치면 같은 줄) 좌우 틈에서 왼쪽 무리부터 다시 읽는다.
      한 줄 안 기둥(왼쪽 기둥형의 상세 · 평면)은 그 기둥 안에서 위부터. 못 자르면 위 → 왼쪽 순. items = [{ key, box }] → key 배열 */
  function readOrder(items) {
    var parts = items.length > 1 ? (cut(items, 'y', 'h') || cut(items, 'x', 'w')) : null;
    if (parts) { return readOrder(parts[0]).concat(readOrder(parts[1])); }
    return items.slice().sort(function (a, b) { return a.box.y - b.box.y || a.box.x - b.box.x; }).map(function (it) { return it.key; });
  }

  /** 칸 글자 딱지 — 그림 없는 칸은 빼고 센다.
      정리 전 시트(laid 아님): 큰 그림 A, (주방) 입체 B, 상세 · 평면 · 기타 그림은 다음 글자(예전 그대로).
      칸으로 정리한 시트(laid): 칸 상자(slotBox — 칸 머리 자리)를 종이 왼쪽 위부터 읽는 순서(readOrder)로 붙인다.
      기타 그림은 글자를 받지 않는다 — 머리가 화면에만 '종류 확인'(v2-paper.js)이라 전달 도면 글자가 비지 않게. */
  function letters(g, kitchen, laid) {
    var out = {}, abc = 'ABCDEFG', keys = ['main'].concat(kitchen ? ['iso'] : [], ['detail', 'plan'], laid ? [] : ['unsorted']);
    keys = keys.filter(function (k) { return g[k] && g[k].length; });
    if (laid) { keys = readOrder(keys.map(function (k) { return { key: k, box: slotBox(g, k) }; })); }
    keys.forEach(function (k, i) { out[k] = abc.charAt(i); });
    return out;
  }

  window.FomsV2Slots = {
    group: group, role: role, noteKind: noteKind, textBox: textBox, isFixed: isFixed, moved: moved, MOVE_TOL: MOVE_TOL,
    detectKind: detectKind, KINDS: KINDS, letters: letters, slotBox: slotBox, readOrder: readOrder, slotOf: slotOf, isBom: isBom,
    title: title, parseGuess: parseGuess, formatGuess: formatGuess, FAM_OF: FAM_OF
  };
})();
