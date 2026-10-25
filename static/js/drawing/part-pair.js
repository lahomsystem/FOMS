/**
 * 도면 마법사 — 주방 짝 규칙(순수 계산 + 빗금 세기). 주방 시트에만 쓴다.
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.1
 * - 같은 시트에서 AI 가 같은 보기(정면/입체)로 짐작한 그림이 딱 두 장이면, 회색 빗금이 많은 쪽을 내부,
 *   적은 쪽을 도어로 본다. 빗금 차이가 0.05 미만이면 바꾸지 않는다(실험 그대로: 주방 85% → 90%).
 * - 다른 제품에 쓰면 정확도가 오히려 내려가서 주방 시트에만 쓴다(냉장고장은 주방이 아님).
 * - 빗금 = 회색 점(밝기 150~215) 수 ÷ 잉크 점(밝기 230 미만) 수. 밝기는 PIL 'L' 과 같은 식.
 * - 짝이 깨지면(세 장이 되면) 모델 짐작(확신 문턱 아래면 미분류)으로 되돌린다 — 늘 같은 입력이면 같은 답.
 * - 규칙이 바꾼 이름인지는 저장 필드 없이 계산으로 가린다(pairChanged): AI 이름표인데 '모델 짐작 그대로'와 다르면 규칙 몫.
 *   짝이 풀려 그 이름이 되돌아가면 releaseNote 가 안내 글을 만든다(화면 토스트 — 사용성 평가 보통-2).
 *
 * window.FomsPartPair = { isKitchen(text), pairLabels(items, threshold), pairChanged(part, threshold),
 *   releaseNote(items, next, threshold), hatchFromPixels(rgba, w, h), hatchFromImage(img) }
 *   items: [{ id, ai, conf, label, hatch }]  (사람이 고른 이름표는 넣지 않는다)  →  [{ id, label }]
 */
(function () {
  'use strict';
  if (window.FomsPartPair) { return; }

  var VIEWS = ['정면', '입체'];
  var DOORIN = ['정면·내부', '정면·도어', '입체·내부', '입체·도어'];
  var UNSURE = '미분류';
  var MIN_GAP = 0.05;
  var MAX_SIDE = 1600;   // 큰 그림은 줄여서 센다(두 장을 같은 식으로 세므로 순서는 거의 그대로)

  function isKitchen(text) {
    var t = String(text || '');
    if (/냉장고/.test(t)) { return false; }
    return /부엌|주방|싱크|아일랜드|하부장|상부장|홈카페|홈바/.test(t);
  }

  function viewOf(label) {
    var v = String(label || '').split('·')[0];
    return VIEWS.indexOf(v) >= 0 && DOORIN.indexOf(label) >= 0 ? v : null;
  }

  /** 모델 짐작 그대로의 이름표(확신이 문턱 아래면 미분류). */
  function baseLabel(it, threshold) {
    return (typeof it.conf === 'number' && it.conf >= threshold) ? it.ai : UNSURE;
  }

  function pairLabels(items, threshold) {
    var th = typeof threshold === 'number' ? threshold : 0.5;
    var groups = {};
    var out = (items || []).map(function (it) {
      var view = viewOf(it.ai);
      if (!view) { return { id: it.id, label: it.label }; }
      (groups[view] = groups[view] || []).push(it);
      return { id: it.id, label: baseLabel(it, th) };
    });
    var byId = {};
    out.forEach(function (o) { byId[o.id] = o; });
    Object.keys(groups).forEach(function (view) {
      var g = groups[view];
      if (g.length !== 2 || typeof g[0].hatch !== 'number' || typeof g[1].hatch !== 'number') { return; }
      if (Math.abs(g[0].hatch - g[1].hatch) < MIN_GAP) { return; }
      var hi = g[0].hatch > g[1].hatch ? g[0] : g[1];
      var lo = hi === g[0] ? g[1] : g[0];
      byId[hi.id].label = view + '·내부';
      byId[lo.id].label = view + '·도어';
    });
    return out;
  }

  /** 짝 규칙이 정한 이름인가 — AI 이름표인데 모델 짐작 그대로(확신이 문턱 아래면 미분류)와 다르다. */
  function pairChanged(part, threshold) {
    if (!part || part.src !== 'ai' || !viewOf(part.ai)) { return false; }
    return part.label !== baseLabel(part, typeof threshold === 'number' ? threshold : 0.5);
  }

  /** 짝이 풀려 규칙이 붙였던 이름이 모델 짐작으로 되돌아간 그림이 있으면 안내 글, 없으면 ''.
      items = pairLabels 에 넣은 것(label = 바꾸기 전 이름), next = pairLabels 결과. */
  function releaseNote(items, next, threshold) {
    var th = typeof threshold === 'number' ? threshold : 0.5;
    var after = {}, counts = {}, hit = null;
    (next || []).forEach(function (n) { after[n.id] = n.label; });
    (items || []).forEach(function (it) {
      var v = viewOf(it.ai);
      if (v) { counts[v] = (counts[v] || 0) + 1; }
    });
    (items || []).some(function (it) {
      var v = viewOf(it.ai), base = baseLabel(it, th);
      if (v && it.label !== base && after[it.id] === base) { hit = v; }
      return !!hit;
    });
    if (!hit) { return ''; }
    var n = counts[hit];
    if (n >= 3) {
      return '주방 ' + (hit === '정면' ? '앞모습' : '입체 그림') + '이 ' + (n === 3 ? '세 장' : n + '장') +
        '이 되어 짝 규칙을 풀었어요 — 종류를 확인해 주세요';
    }
    return '주방 짝이 맞지 않아 짝 규칙을 풀었어요 — 종류를 확인해 주세요';
  }

  function hatchFromPixels(rgba, w, h) {
    var ink = 0, mid = 0, n = w * h;
    for (var i = 0; i < n; i++) {
      var k = i * 4;
      var g = (rgba[k] * 299 + rgba[k + 1] * 587 + rgba[k + 2] * 114) / 1000;
      if (g < 230) { ink += 1; }
      if (g >= 150 && g <= 215) { mid += 1; }
    }
    return mid / Math.max(1, ink);
  }

  /** 불러온 그림(같은 출처) → 빗금 세기. 흰 바탕에 그려 투명 부분은 흰색으로 센다. 실패하면 null. */
  function hatchFromImage(img) {
    try {
      var nw = img.naturalWidth || img.width, nh = img.naturalHeight || img.height;
      if (!nw || !nh) { return null; }
      var sc = Math.min(1, MAX_SIDE / Math.max(nw, nh));
      var w = Math.max(1, Math.round(nw * sc)), h = Math.max(1, Math.round(nh * sc));
      var canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      var ctx = canvas.getContext('2d', { willReadFrequently: true });
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      return Math.round(hatchFromPixels(ctx.getImageData(0, 0, w, h).data, w, h) * 1000) / 1000;
    } catch (e) {
      return null;
    }
  }

  window.FomsPartPair = {
    isKitchen: isKitchen, pairLabels: pairLabels, pairChanged: pairChanged, releaseNote: releaseNote,
    hatchFromPixels: hatchFromPixels, hatchFromImage: hatchFromImage
  };
})();
