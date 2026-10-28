/**
 * 도면 마법사 V2 — 칸 자동 배치 화면을 마법사 엔진(window.FomsWizardCore)에 잇는다.
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §4 · §5
 * - 언제 배치하나(자동 배치 모드만): 같이 올린 묶음이 끝났을 때 · 그림 한 장을 올렸을 때(붙여넣기 · 복제 사본 포함) · 종류가 바뀌었을 때
 *   (묶음 배치 뒤 늦게 온 AI 이름표 포함) · 그림을 지웠을 때 · 여백을 잘랐을 때 · [다시 자동 배치] · 앱바 [자동 배치]를 눌렀을 때 ·
 *   틀 · 켜고 끄기를 바꿨을 때. 시트를 열기만 해서는 옮기지 않는다(다른 시트에 올린 묶음은 그 시트를 열 때 놓는다).
 *   자유 배치 모드는 저절로 옮기지 않는다. 예전엔 지우기에 배치가 없어 남은 그림 자리가 비었다(스테이징 주문 4385, 2026-10-27).
 * - 되돌리기: 사람이 한 일(올리기 · 종류 바꾸기 · 지우기 · 자르기)과 그 뒤 배치는 Ctrl+Z 한 번(그 일이 이미 남긴 사본으로 돌아간다).
 *   [다시 자동 배치] · 틀 고르기 · 켜고 끄기 · 나누기는 따로 한 번. 바뀐 것이 없으면 사본을 남기지 않는다(되돌려도 그대로인 헛 한 번).
 * - 사람이 누른 배치와 지운 뒤 배치는 결과를 알림으로 말한다(다시 놓은 장수 · 이미 맞음 · 고정이라 그대로 · 못 놓음 — v2-chrome.js).
 * - 실측 사진 자동: 첫 배치 때 사진 그림이 없고 실측 사진이 있으면 한 장 골라 넣는다(폼 v2_photo = 'done' — 시트마다 한 번).
 * - AI 칸 짐작: AI 이름표가 미분류(세부 확신 낮음)여도 칸 확신이 문턱을 넘으면 폼 v2_ai 에 남겨 그 칸에 놓는다(v2-slots).
 * - 사람이 종류를 고르면(자동 배치 모드) 그 그림의 고정(손으로 옮김)을 풀어 새 종류 칸으로 보낸다 — 잠금 · 돌림은 그대로.
 * - 손으로 끌거나 키워 고정이 된 그림(코어 moved)은 비켜 나머지를 다시 놓는다 — 메인을 키우면 옆 그림과 겹쳤다(주문 4385, 2026-10-28).
 *   칸 머리 위 글자(자재표 · 특이 · 강조)는 글이 바뀌면 다시 배치하고 손으로 옮기면 고정한다(v2-text.js — 같은 날 '자재 입력 시 간격').
 *
 * window.FomsV2 = { refresh(), arrange(reason, opts), plan(), settings(), setSetting(k, v), mode(), setMode(m, fromUser),
 *   relabel(id, label), selectIds(ids), split(), pickTemplate(t), unpinAll(), core }
 */
(function () {
  'use strict';
  if (window.FomsV2) { return; }

  var SET_KEY = 'foms.dws.v2.settings', MODE_KEY = 'foms.dws.v2.mode';
  var core = null, settings = { lowToUnsorted: true, photoFirst: true, sameScale: true, lockMoved: true }, mode = 'auto';
  var last = null, baseCache = { key: '', val: {} }, refreshTimer = 0, arrangeTimer = 0, autoPhoto = {}, awaitingPhoto = false;
  var lastArranged = null;   // 마지막 배치 요약 — 알림 띠 글
  // 지운 그림(다음 배치 알림 · 되돌렸는지) · 배치가 끝난 묶음 그림(뒤에 온 AI 이름표 = 늦은 이름) · 다른 시트에서 끝난 묶음
  var gone = { n: 0, ids: {} }, batched = {}, waiting = {};

  function read(key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } }
  function write(key, v) { try { window.localStorage.setItem(key, v); } catch (e) { /* 사생활 보호 모드 — 이 창에서만 */ } }

  function loadSettings() {
    try { var s = JSON.parse(read(SET_KEY) || '{}'); Object.keys(settings).forEach(function (k) { if (typeof s[k] === 'boolean') { settings[k] = s[k]; } }); }
    catch (e) { /* 기본값 */ }
    mode = read(MODE_KEY) === 'free' ? 'free' : 'auto';
  }

  function baseline(imgs) {
    var sh = core.sheet(), key = (sh ? sh.id : '') + '|' + imgs.map(function (o) {
      return [o.id, o.natural_w || o.w, o.natural_h || o.h, (o.part && o.part.label) || '', core.image && core.image(o.id) ? 1 : 0].join(':');   // 그림이 뜨면(치수 글자 높이를 잰 뒤) 다시 잰다
    }).join(';');
    if (baseCache.key !== key) { baseCache = { key: key, val: core.baseline(imgs) }; }
    return baseCache.val;
  }

  function buildPlan(sheet) {
    return window.FomsV2Plan.build(sheet, { items: core.items, baseline: baseline, productText: core.productText(), settings: settings });
  }

  /** 지금 시트 화면(종이 머리 · 왼쪽 · 오른쪽 · 알림 띠)을 다시 그린다 — 여러 사건을 한 번으로 모은다. */
  function refresh() {
    if (refreshTimer) { return; }
    refreshTimer = window.setTimeout(function () { refreshTimer = 0; refreshNow(); }, 60);
  }

  function refreshNow() {
    var sheet = core.sheet();
    last = sheet ? buildPlan(sheet) : null;
    var pct = last ? window.FomsV2Plan.nowPct(last, sheet) : {}, minId = null, minV = Infinity;
    if (last) {
      Object.keys(pct).forEach(function (id) {
        var slot = last.g.labels[id] === '사진' || last.g.unsorted.some(function (o) { return o.id === id; });
        if (!slot && pct[id] < minV) { minV = pct[id]; minId = id; }
      });
    }
    var view = { sheet: sheet, plan: last, pct: pct, minId: minId, minPct: minV === Infinity ? null : minV, autoPhoto: autoPhoto,
      sheets: core.state().sheets.length, mode: mode, settings: settings, arranged: lastArranged,
      layer: document.getElementById('dws-v2-slots'), badges: document.getElementById('dws-v2-badges'),
      pageTotal: document.getElementById('dws-v2-pagetotal') };
    var root = document.getElementById('dws-root');
    if (root) { root.classList.toggle('dws-v2-laid', !!(last && last.laid)); }
    window.FomsV2Paper.render(view);
    // 아래 띠 글이 칸보다 길면 글씨만 줄인다(V1 표 엔진 대신 — wizard.js fitCellText)
    Array.prototype.forEach.call(document.querySelectorAll('.dws-v2-form [data-dws-form-key]'), function (el) { core.fitCell(el); });
    if (window.FomsV2Left) { window.FomsV2Left.render(view); }
    if (window.FomsV2Right) { window.FomsV2Right.render(view); }
    if (window.FomsV2Chrome) { window.FomsV2Chrome.render(view); }
  }

  function hasPhotoImage(sheet) {
    return (sheet.objects || []).some(function (o) { return o.type === 'image' && o.part && o.part.label === '사진'; });
  }

  /** 실측 사진 자동 — 시트마다 한 번(v2_photo). 고르기는 v2-chrome.js(색 · 밝기 섞임 점수). */
  function maybeAutoPhoto(sheet) {
    if (!settings.photoFirst || !sheet || hasPhotoImage(sheet) || (sheet.form && sheet.form.v2_photo === 'done')) { return; }
    var photos = (core.photos() || []).filter(core.photoVisible);
    if (!photos.length || !window.FomsV2Chrome) { return; }
    sheet.form.v2_photo = 'done';
    window.FomsV2Chrome.pickPhoto(photos).then(function (photo) {
      if (!photo || core.sheet() !== sheet) { return; }
      awaitingPhoto = true;
      return core.importPhoto(photo, null).then(function (ok) { if (!ok) { awaitingPhoto = false; } });
    });
  }

  function say(reason, d, plan, removed, freed) {   // 배치 결과 알림(글은 v2-chrome arrangeText — '' 면 말하지 않음)
    var C = window.FomsV2Chrome, msg = C && C.arrangeText ? C.arrangeText(reason, d, plan, removed, freed) : '';
    if (msg) { core.toast(msg); }
  }
  /** 칸 배치를 시트에 붙인다. opts: { undo: 따로 되돌리기 한 번, photo: 실측 사진 자동, template: 고른 틀, freed: 겹쳐 푼 고정 그림 수(알림) } */
  function arrange(reason, opts) {
    var o = opts || {}, sheet = core.sheet(), removed = gone.n;
    gone = { n: 0, ids: {} };
    if (!core.canSave() || !sheet) { return false; }
    var plan = buildPlan(sheet), key = o.template || plan.pick || plan.out.best, res = key ? plan.out[key] : null;
    if (!res && !o.template && key !== plan.out.best) { key = plan.out.best; res = key ? plan.out[key] : null; }   // 고른 틀에 안 들어가면 되는 틀로
    if (!res) { say(reason, null, plan); return false; }
    var d = window.FomsV2Plan.diff(sheet, res, key), g = plan.g;
    if (d.any && o.undo) { core.recordUndo(); }   // 바뀐 것이 없으면 사본을 남기지 않는다
    window.FomsV2Plan.apply(sheet, res, { template: key });
    if (d.any) {   // 알림 띠 [되돌리기]는 실제로 옮긴 배치만 가리킨다
      lastArranged = { sheetId: sheet.id, pics: g.main.length + g.iso.length + g.detail.length + g.plan.length + g.unsorted.length,
        photos: g.photo.length, unsorted: g.unsorted.length, crowded: !!res.crowded, minPct: res.minPct, reason: reason };
      core.markDirty();
      core.redraw();
    }
    if (reason !== 'moved') { core.select([]); }   // 마지막에 올린 그림이 골라진 채 남으면 미니 막대가 칸을 가린다(손으로 맞추던 그림은 그대로)
    if (o.photo) { maybeAutoPhoto(sheet); }
    say(reason, d, plan, removed, o.freed);
    refresh();
    return true;
  }

  /** 지운 뒤 배치해도 되나 — 그 사이 되돌려 지운 그림이 돌아왔거나 그림이 하나도 없으면 하지 않는다. */
  function afterRemove(sh) {
    var objs = sh.objects || [], ok = objs.some(function (x) { return x.type === 'image'; }) && !objs.some(function (x) { return gone.ids[x.id]; });
    if (!ok) { gone = { n: 0, ids: {} }; }
    return ok;
  }

  function scheduleArrange(reason) {
    if (mode !== 'auto') { return; }
    var sid = core.sheet() ? core.sheet().id : '';
    if (arrangeTimer) { window.clearTimeout(arrangeTimer); }
    arrangeTimer = window.setTimeout(function () {
      arrangeTimer = 0;
      if (core.editing() || core.dragging()) { scheduleArrange(reason); return; }   // 끄는 중에 다시 그리면 끌던 노드가 사라진다
      var sh = core.sheet();
      if (!sh || sh.id !== sid || (reason === 'removed' && !afterRemove(sh))) { return; }   // 그 사이 다른 시트로 옮겼으면 건드리지 않는다
      arrange(reason, { photo: reason === 'added' });
    }, 450);
  }

  function setSetting(k, v) {
    if (!(k in settings)) { return; }
    settings[k] = !!v;
    write(SET_KEY, JSON.stringify(settings));
    var sh = core.sheet();
    if (mode === 'auto' && sh && sh.form && sh.form.v2_layout) { arrange('setting', { undo: true }); } else { refresh(); }
  }

  /** fromUser = 앱바 단추를 눌렀다 — [자동 배치]를 누르면(이미 자동이어도) 지금 그림으로 다시 놓는다(자유 배치에서 손댄 뒤 돌아올 때).
      화면을 열 때(init)는 칸으로 정리하기 전 시트만. */
  function setMode(m, fromUser) {
    mode = m === 'free' ? 'free' : 'auto';
    write(MODE_KEY, mode);
    var root = document.getElementById('dws-root');
    if (root) { root.classList.toggle('dws-v2-auto', mode === 'auto'); root.classList.toggle('dws-v2-free', mode === 'free'); }
    if (mode === 'free') { core.setTool('select'); }
    var sh = core.sheet(), laid = !!(sh && sh.form && sh.form.v2_layout);
    if (mode === 'auto' && sh && (fromUser || !laid) && (sh.objects || []).some(function (x) { return x.type === 'image'; })) {
      arrange(fromUser ? 'mode' : 'open', { undo: true, photo: !laid });
    }
    refresh();
  }

  function relabel(id, label) { core.setPartLabel(id, label); }   // labels 사건 → 자동 배치 모드면 다시 배치

  function sheetWith(id) {
    return (core.state().sheets || []).filter(function (sh) { return (sh.objects || []).some(function (o) { return o.id === id; }); })[0] || null;
  }

  function writeGuess(sh, map) {
    var text = window.FomsV2Slots.formatGuess(map, sh.objects);
    sh.form = sh.form || {};
    if (text) { sh.form.v2_ai = text; } else { delete sh.form.v2_ai; }
  }

  /** AI 이름표가 오면 칸 짐작을 그 시트 폼(v2_ai)에 남긴다 — 이름표가 미분류(세부 확신 낮음)이고 칸 확신이 문턱 이상일 때만. */
  function rememberGuess(d) {
    var sh = d.id ? sheetWith(d.id) : null, S = window.FomsV2Slots;
    if (!sh) { return; }
    var o = sh.objects.filter(function (x) { return x.id === d.id; })[0], p = (o && o.part) || {};
    var map = S.parseGuess(sh.form && sh.form.v2_ai), code = { front: 'f', iso: 'i', detail: 'd' }[d.fam];
    if (p.label === '미분류' && p.src === 'ai' && code && d.famConf >= core.threshold()) { map[d.id] = { fam: code, conf: d.famConf }; }
    else if (!map[d.id]) { return; }
    else { delete map[d.id]; }
    writeGuess(sh, map);
  }

  /** 사람이 종류를 고른 그림 — 칸 짐작을 지우고, unpin 이면 손으로 옮긴 고정을 푼다(지금 자리를 배치 자리로 — 다음 배치가 옮긴다). */
  function release(ids, unpin) {
    var S = window.FomsV2Slots;
    (ids || []).forEach(function (id) {
      var sh = sheetWith(id), o = sh ? sh.objects.filter(function (x) { return x.id === id; })[0] : null;
      if (!o || o.type !== 'image') { return; }
      if (unpin && o.part && !o.locked && S.moved(o)) { o.part.arr = [o.x, o.y, o.w, o.h]; }
      var map = S.parseGuess(sh.form && sh.form.v2_ai);
      if (map[id]) { delete map[id]; writeGuess(sh, map); }
    });
  }

  function pickTemplate(t) {   // '' = 고른 틀만 풀고 추천 틀로([추천 틀로 돌아가기] — 고정 그림은 그대로)
    var sh = core.sheet();
    if (!sh || (t !== 'band' && t !== 'column' && t !== '')) { return; }
    core.recordUndo();
    sh.form.v2_pick = t;
    arrange(t ? 'template' : 'unpick', { template: t });
  }

  function split() {
    var sheet = core.sheet(), plan = sheet ? buildPlan(sheet) : null, groups = plan ? window.FomsV2Plan.splitGroups(plan) : null;
    if (!groups) { core.toast('나눌 그림이 모자라요 — 큰 그림이나 상세가 두 개 이상이어야 해요'); return; }
    var made = core.split(groups, function (fresh) {
      var p = buildPlan(fresh), r = p.out[p.out.best];
      if (r) { window.FomsV2Plan.apply(fresh, r, { template: p.out.best }); }
    });
    if (!made.length) { core.toast('시트는 10장까지예요 — 나눌 수 없어요'); return; }
    arrange('split', {});
    core.toast('그림 ' + groups[0].length + '장을 새 시트 "' + made[0].name + '"로 옮겨 칸에 놓았어요 · 되돌리기: 이 시트에서 Ctrl+Z');
  }

  function unpinAll() {
    var sh = core.sheet();
    if (!sh) { return; }
    core.recordUndo();
    (sh.objects || []).forEach(function (o) {
      if (o.type === 'image' && o.part && window.FomsV2Slots.moved(o)) { o.part.arr = [o.x, o.y, o.w, o.h]; }
    });
    sh.form.v2_pick = '';
    delete sh.form.v2_pin;   // 손으로 옮겨 고정한 칸 머리 위 글자(v2-text.js)도 함께 푼다
    arrange('unpin', {});
  }

  function laidNow() { var sh = core.sheet(); return !!(sh && sh.form && sh.form.v2_layout); }
  function wire() {
    ['render', 'sheet', 'loaded', 'change'].forEach(function (ev) { core.on(ev, refresh); });
    core.on('batch', function (d) {
      var ids = (d && d.ids) || [], sh = core.sheet(), on = ids.length ? sheetWith(ids[ids.length - 1]) : null;
      ids.forEach(function (id) { batched[id] = true; });
      if (mode !== 'auto') { refresh(); return; }
      if (on && sh && on !== sh) { waiting[on.id] = true; return; }   // 묶음 그림이 다른 시트에 있다 — 그 시트를 열 때 놓는다
      arrange('batch', { photo: true });
    });
    core.on('sheet', function () {
      var sh = core.sheet();
      if (sh && waiting[sh.id] && mode === 'auto') { delete waiting[sh.id]; arrange('batch', { photo: true }); }
    });
    core.on('added', function (d) {
      if (awaitingPhoto && d && d.id) { autoPhoto[d.id] = true; awaitingPhoto = false; }
      if (d && !d.batch) { scheduleArrange('added'); }
    });
    core.on('removed', function (d) {   // 그림을 지우면 남은 그림을 다시 놓는다(되돌리기는 지우기가 남긴 한 번)
      if (!d || !d.images || mode !== 'auto' || !laidNow()) { return; }
      gone.n += d.images;
      (d.ids || []).forEach(function (id) { gone.ids[id] = true; });
      scheduleArrange('removed');
    });
    core.on('trimmed', function () { if (laidNow()) { scheduleArrange('trimmed'); } });   // 여백을 자르면 새 비율로 다시
    core.on('moved', function (d) {   // 고정이 된 그림을 비켜 다시 놓는다(되돌리기는 끌기가 남긴 한 번 · 6px 안 손떨림은 고정이 아니라 그대로)
      var objs = (core.sheet() || {}).objects || [], S = window.FomsV2Slots, ids = (d && d.ids) || [];
      if (mode !== 'auto' || !settings.lockMoved || !laidNow() || !objs.some(function (o) { return ids.indexOf(o.id) >= 0 && o.type === 'image' && S.isFixed(o, settings); })) { return; }
      S.release(objs, S.clashes(objs, settings, ids));   // 옮긴 그림과 겹친 다른 고정 그림은 풀어 비키게(방금 옮긴 그림이 이긴다)
      scheduleArrange('moved');
    });
    core.on('labels', function (d) {
      if (!d) { return; }
      if (d.by === 'ai') { rememberGuess(d); }
      else if (d.by === 'user') { release(d.ids || [d.id], mode === 'auto'); }
      var here = !d.id || sheetWith(d.id) === core.sheet();   // 묶음 배치 뒤(30초 넘어) 온 AI 이름표도 그 시트면 다시 놓는다
      if (d.by === 'user' || (here && (!d.batch || batched[d.id]))) { scheduleArrange('labels'); }
    });
    core.on('arrange', function (d) { arrange(d && d.fromUpload ? 'late' : 'button', { undo: !(d && d.fromUpload), photo: true }); });
  }

  function init() {
    core = window.FomsWizardCore;
    if (!core || core.ui !== 'v2') { return; }
    loadSettings();
    window.FomsV2 = {
      core: core, refresh: refresh, arrange: arrange, plan: function () { return last; },
      settings: function () { return settings; }, setSetting: setSetting, mode: function () { return mode; }, setMode: setMode,
      relabel: relabel, selectIds: function (ids) { core.select(ids); }, split: split, pickTemplate: pickTemplate, unpinAll: unpinAll
    };
    ['FomsV2Chrome', 'FomsV2Left', 'FomsV2Right', 'FomsV2Text'].forEach(function (k) { if (window[k]) { window[k].init(window.FomsV2); } });
    wire();
    setMode(mode);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
