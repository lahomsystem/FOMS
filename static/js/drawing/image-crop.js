/**
 * 도면 마법사 — 그림 자르기(포토샵 자르기 도구처럼).
 *
 * 2026-11-03 사용자 '이미지를 자를 수 있는 기능을 넣어 줘(like photoshop)':
 * 그림 하나를 고르고 미니 툴바 [자르기] → 그림 위에 자르기 틀이 뜬다. 모서리·변 손잡이를 끌어 남길 부분을 고르고
 * 틀 안을 끌어 옮긴다. 틀 밖은 어둡게 덮는다. Enter·[자르기] = 적용, Esc·[취소] = 그대로 둔다. 틀 안 두 번 누름도 적용.
 * - 적용 = 화면에 보이는 그대로(뒤집기 포함) 원본 해상도에서 잘라 새 에셋으로 올린다(trim=0 — 서버 여백 자르기 건너뜀).
 *   원본 에셋은 그대로 남아 Ctrl+Z 한 번이면 돌아온다(core.applyCrop 이 되돌리기 · 자리 · V2 다시 놓기를 맡는다).
 * - 돌린 그림도 그림 틀과 같이 돌린 무리 안에서 자르므로 남긴 부분이 화면 제자리에 남는다.
 * - 자르는 동안 마법사 단축키(Delete · Ctrl+Z 등)는 막는다 — 뒤 그림이 지워지거나 되돌려지지 않게.
 *
 * window.FomsImageCrop = { start(), cancel(), active() }
 */
(function () {
  'use strict';
  if (window.FomsImageCrop) { return; }
  var MIN = 8;          // 틀 최소 변(논리 px)
  var crop = null;      // { id, o, wrap, group, box, tr, shades[4], W, H }
  var core = null, bar = null, applyBtn = null, busy = false;

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  /* 틀 밖 네 조각을 어둡게 — 그림 틀(0..W × 0..H) 안에서 상자 둘레만 덮는다. */
  function layoutShades() {
    var b = crop.box, x = b.x(), y = b.y(), w = b.width(), h = b.height(), W = crop.W, H = crop.H;
    var parts = [[0, 0, W, y], [0, y + h, W, H - y - h], [0, y, x, h], [x + w, y, W - x - w, h]];
    crop.shades.forEach(function (r, i) {
      r.setAttrs({ x: parts[i][0], y: parts[i][1], width: Math.max(0, parts[i][2]), height: Math.max(0, parts[i][3]) });
    });
    placeBar();
  }

  /* 손잡이로 늘린 배율을 치수로 옮기고 그림 틀 밖으로 못 나가게 막는다. */
  function normalizeBox() {
    var b = crop.box;
    var x = b.x(), y = b.y(), w = b.width() * b.scaleX(), h = b.height() * b.scaleY();
    if (w < 0) { x += w; w = -w; }
    if (h < 0) { y += h; h = -h; }
    var x2 = clamp(x + w, 0, crop.W), y2 = clamp(y + h, 0, crop.H);
    x = clamp(x, 0, crop.W - MIN); y = clamp(y, 0, crop.H - MIN);
    b.setAttrs({ x: x, y: y, width: Math.max(MIN, x2 - x), height: Math.max(MIN, y2 - y), scaleX: 1, scaleY: 1 });
    layoutShades();
  }

  function onDrag() {
    var b = crop.box;
    b.x(clamp(b.x(), 0, crop.W - b.width()));
    b.y(clamp(b.y(), 0, crop.H - b.height()));
    layoutShades();
  }

  function placeBar() {
    if (!bar || !crop) { return; }
    var anno = crop.wrap.getStage().container().getBoundingClientRect();
    var r = crop.box.getClientRect(), z = core.zoom();
    var left = anno.left + r.x * z, top = anno.top + r.y * z - bar.offsetHeight - 10;
    if (top < 8) { top = anno.top + (r.y + r.height) * z + 10; }
    bar.style.left = clamp(left, 8, Math.max(8, window.innerWidth - bar.offsetWidth - 8)) + 'px';
    bar.style.top = clamp(top, 8, Math.max(8, window.innerHeight - bar.offsetHeight - 8)) + 'px';
  }

  /* 자르기 틀 무리 — 그림과 같은 자리·돌림. 클릭은 마법사 스테이지 처리(선택 · 끌어 고르기)로 새지 않게 막는다. */
  function buildOverlay(o, layer) {
    var W = Number(o.w) || 1, H = Number(o.h) || 1;
    var wrap = new Konva.Group({ name: 'dws-crop' });
    var cover = new Konva.Rect({ x: 0, y: 0, width: core.stageW, height: core.stageH, fill: 'rgba(0,0,0,0.001)' });
    var group = new Konva.Group({ x: Number(o.x) || 0, y: Number(o.y) || 0, rotation: Number(o.rotation) || 0 });
    var shades = [0, 1, 2, 3].map(function () { return new Konva.Rect({ fill: 'rgba(0,0,0,0.5)', listening: false }); });
    var box = new Konva.Rect({
      x: 0, y: 0, width: W, height: H, draggable: true,
      fill: 'rgba(0,0,0,0.001)', stroke: '#ffffff', strokeWidth: 1, dash: [6, 4], strokeScaleEnabled: false
    });
    var tr = new Konva.Transformer({
      nodes: [box], rotateEnabled: false, keepRatio: false, flipEnabled: false, ignoreStroke: true,
      enabledAnchors: ['top-left', 'top-center', 'top-right', 'middle-right', 'bottom-right', 'bottom-center', 'bottom-left', 'middle-left'],
      anchorSize: 10, anchorStroke: '#1c62d6', anchorFill: '#ffffff', borderStroke: '#1c62d6', borderStrokeWidth: 1.5,
      shiftBehavior: 'default'   // Shift 누르는 동안 비율 고정(포토샵)
    });
    shades.forEach(function (r) { group.add(r); });
    group.add(box);
    wrap.add(cover); wrap.add(group); wrap.add(tr);
    wrap.on('mousedown pointerdown touchstart click tap dblclick dbltap', function (e) { e.cancelBubble = true; });
    box.on('dragmove', onDrag);
    box.on('transform transformend', normalizeBox);
    box.on('dblclick dbltap', apply);
    cover.on('dblclick dbltap', apply);
    layer.add(wrap);
    wrap.moveToTop();
    return { wrap: wrap, group: group, box: box, tr: tr, shades: shades, W: W, H: H };
  }

  function start() {
    if (!core || crop || busy || !core.canSave()) { return; }
    var id = core.selectedId(), o = id ? core.find(id) : null;
    if (!o || o.type !== 'image' || !o.key) { core.toast('자를 그림 하나를 먼저 고르세요.'); return; }
    if (o.locked) { core.toast('잠긴 그림은 자를 수 없습니다.'); return; }
    if (!core.image(id)) { core.toast('그림을 불러오는 중입니다. 잠시 뒤 다시 눌러 주세요.'); return; }
    var layer = core.layer();
    if (!layer) { return; }
    core.select([]);
    crop = buildOverlay(o, layer);
    crop.id = id; crop.o = o;
    bar.hidden = false;
    layoutShades();
    layer.batchDraw();
  }

  function close() {
    if (!crop) { return; }
    var layer = crop.wrap.getLayer();
    crop.tr.destroy();
    crop.wrap.destroy();
    if (layer) { layer.batchDraw(); }
    crop = null;
    bar.hidden = true;
  }

  function cancel() {
    if (!crop) { return; }
    var id = crop.id;
    close();
    core.select([id]);
  }

  /* 화면에 보이는 그대로(뒤집기 포함 — core.image 는 뒤집은 원본 해상도 캔버스) 고른 부분을 잘라 그린다. */
  function cutCanvas(src, o, b) {
    var sw = src.naturalWidth || src.width, sh = src.naturalHeight || src.height;
    var kx = sw / (Number(o.w) || 1), ky = sh / (Number(o.h) || 1);
    var sx = Math.round(b.x * kx), sy = Math.round(b.y * ky);
    var cw = Math.max(1, Math.min(sw - sx, Math.round(b.w * kx))), ch = Math.max(1, Math.min(sh - sy, Math.round(b.h * ky)));
    var cv = document.createElement('canvas');
    cv.width = cw; cv.height = ch;
    cv.getContext('2d').drawImage(src, sx, sy, cw, ch, 0, 0, cw, ch);
    return cv;
  }

  function apply() {
    if (!crop || busy) { return; }
    var b = { x: crop.box.x(), y: crop.box.y(), w: crop.box.width(), h: crop.box.height() };
    var id = crop.id, o = crop.o, src = core.image(id);
    if (b.x < 0.5 && b.y < 0.5 && Math.abs(b.w - crop.W) < 0.5 && Math.abs(b.h - crop.H) < 0.5) { cancel(); return; }   // 그대로면 할 일 없음
    if (!src) { cancel(); core.toast('그림을 찾지 못했습니다.'); return; }
    var jpeg = /\.jpe?g$/i.test(String(o.key));
    var cv = cutCanvas(src, o, b);
    busy = true;
    if (applyBtn) { applyBtn.disabled = true; }
    function done() { busy = false; if (applyBtn) { applyBtn.disabled = false; } }
    cv.toBlob(function (blob) {
      if (!blob) { done(); core.toast('자르기에 실패했습니다.'); return; }
      var name = 'crop-' + Date.now() + (jpeg ? '.jpg' : '.png');
      core.upload(new File([blob], name, { type: blob.type }), { noTrim: true }).then(function (r) {
        done();
        var data = r && r.data && r.data.data;
        if (r.status !== 200 || !r.data || !r.data.success || !data || !data.key) {
          core.toast((r && r.data && r.data.message) || '자르기에 실패했습니다.');
          return;
        }
        close();
        if (core.applyCrop(id, { key: data.key, width: cv.width, height: cv.height }, b)) { core.toast('그림을 잘랐습니다. 되돌리려면 Ctrl+Z'); }
      }).catch(function (err) {
        done();
        console.warn('[dws] crop image', err);
        core.toast('자르기 오류');
      });
    }, jpeg ? 'image/jpeg' : 'image/png', 0.92);
  }

  /* 자르는 동안 키는 여기서 끝낸다 — Enter 적용 · Esc 취소, 나머지 마법사 단축키는 막는다(Ctrl+S 저장 포함 — 자르기 전 상태 저장을 피함). */
  function onKey(e) {
    if (!crop) { return; }
    var t = e.target, typing = !!(t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)));
    if (typing && e.key !== 'Escape') { return; }   // 오른쪽 칸에 글 쓰는 중이면 그대로 둔다
    if (e.key === 'Enter') { e.preventDefault(); apply(); }
    else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
    else if (e.key === 'Delete' || e.key === 'Backspace' || e.ctrlKey || e.metaKey) { e.preventDefault(); }
    e.stopImmediatePropagation();
  }

  function init() {
    bar = document.getElementById('dws-crop-bar');
    var btn = document.getElementById('dws-mt-crop');
    if (!bar || !btn) { return; }
    applyBtn = document.getElementById('dws-crop-apply');
    btn.addEventListener('click', start);
    if (applyBtn) { applyBtn.addEventListener('click', apply); }
    var cancelBtn = document.getElementById('dws-crop-cancel');
    if (cancelBtn) { cancelBtn.addEventListener('click', cancel); }
    window.addEventListener('keydown', onKey, true);
    window.addEventListener('resize', placeBar);
    window.addEventListener('scroll', placeBar, true);
    core = window.FomsWizardCore;   // wizard.js 가 먼저 DOMContentLoaded 에서 연다(스크립트 순서)
    if (!core) { return; }
    core.on('sheet', close);   // 다른 시트로 가면 틀을 걷는다
    core.on('render', function () { if (crop && !core.find(crop.id)) { close(); } });   // 그림이 사라졌으면 걷는다
  }

  window.FomsImageCrop = { start: start, cancel: cancel, active: function () { return !!crop; } };
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
})();
