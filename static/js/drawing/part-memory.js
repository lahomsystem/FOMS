/**
 * 도면 마법사 — 그림 종류 기억(사람이 고른 종류를 바로 배우기). V1 · V2 공통(같은 엔진 wizard.js 가 부른다).
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-part-memory-spec.md
 * - remember: 분류 직후 특징(768 → float16 → base64)과 이름표를 서버에 남긴다. 그림은 보내지 않는다.
 * - labelsChanged: 이름표가 바뀌면(사람 고름 · 되돌리기 · 다시 하기 · 저장 성공) 이 주문 그림들의 이름표 목록을
 *   지난번 보낸 것과 견줘 바뀐 줄만 보낸다. 서버가 '특징 없음'(missing)이라 하면 모델이 이 브라우저에 이미 있을 때만
 *   특징을 다시 뽑아 보낸다(이름표는 안 바꾼다, 한 창에서 40장까지).
 * - follow: 새로 분류한 그림이 사람이 고른 비슷한 그림을 따를지 서버에 묻는다(1.5초 안에 답이 없으면 그대로).
 * - spread: 사람이 한 장을 고치면 같은 시트의 닮은 AI 이름표 그림을 서버에 묻는다(바꾸기는 wizard.js 가 한다).
 *   내부/도어로 고쳤을 때 같은 보기 그림이 딱 하나 더 있으면(주방 짝) 그 짝은 묻지 않는다 — 짝은 반대 종류일 때가 많다.
 * - 보내기는 한 줄로 차례차례(앞의 것이 끝나야 다음) — 늦게 온 분류 결과가 사람 이름표를 덮지 않는다.
 *   실패하면 조용히 버리고 다음 동기화 때 다시 보낸다. 분류 · 배치 · 저장 · 전달은 기다리지 않는다.
 *
 * window.FomsPartMemory = { init(cfg), remember(o, res), labelsChanged(), follow(o, res) → Promise<verdict|null>,
 *   spread(sheet, o, label) → Promise<[{id, sim}]>, noteSim(id, sim), simOf(id), isMem(part), memHead(head),
 *   f16b64(feat), labelMap(sheets), partnerOf(sheet, o, label) }
 *   cfg = { base, orderId, fetch(url, opts) → Promise<{status, data}>, sheets() → [sheet], imageFor(key) → img|null,
 *           policy: {store, follow, spread} }
 */
(function () {
  'use strict';
  if (window.FomsPartMemory) { return; }

  var MAX_ITEMS = 30, FOLLOW_WAIT_MS = 1500, SYNC_DELAY_MS = 1500, FLUSH_DELAY_MS = 800, BACKFILL_MAX = 40;
  var VIEW = { '정면·내부': 'f', '정면·도어': 'f', '입체·내부': 'i', '입체·도어': 'i' };
  var cfg = null;
  var queue = Promise.resolve();
  var buffer = [], flushTimer = 0, syncTimer = 0;
  var sent = {};      // 그림 키 → '이름표|출처' 지난번 보낸 것
  var sims = {};      // 그림 id → 따른 기억 닮음(이 창에서만)
  var tried = {}, backfilled = 0;

  function on(name) { return !!(cfg && cfg.policy && cfg.policy[name]); }

  function keyOk(key) {
    return !!cfg && typeof key === 'string' && key.indexOf('orders/' + cfg.orderId + '/drawing_wizard/assets/') === 0;
  }

  /* float32 → float16(IEEE 754 반정밀도) 비트. 특징은 L2 정규화라 값이 −1~1 이다. */
  var f32 = new Float32Array(1), u32 = new Uint32Array(f32.buffer);
  function half(v) {
    f32[0] = v;
    var x = u32[0], sign = (x >>> 16) & 0x8000, exp = (x >>> 23) & 0xff, mant = x & 0x7fffff;
    if (exp === 0xff) { return sign | 0x7c00 | (mant ? 0x200 : 0); }
    var e = exp - 127 + 15;
    if (e >= 0x1f) { return sign | 0x7c00; }
    if (e <= 0) {
      if (e < -10) { return sign; }
      return sign | (((mant | 0x800000) >> (1 - e)) + 0x1000 >> 13);
    }
    return sign | ((e << 10) + ((mant + 0x1000) >> 13));
  }

  /** 특징(Float32Array) → float16 little-endian 바이트 → base64(768개면 2,048자). */
  function f16b64(feat) {
    var bytes = new Uint8Array(feat.length * 2), s = '';
    for (var i = 0; i < feat.length; i++) { var h = half(feat[i]); bytes[2 * i] = h & 0xff; bytes[2 * i + 1] = h >> 8; }
    for (var j = 0; j < bytes.length; j += 0x2000) { s += String.fromCharCode.apply(null, bytes.subarray(j, j + 0x2000)); }
    return window.btoa(s);
  }

  function post(path, body) {
    return cfg.fetch(cfg.base + path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    }).then(function (r) {
      return (r && r.status === 200 && r.data && r.data.success) ? (r.data.data || {}) : null;
    }, function () { return null; });
  }

  /** 차례차례 — 앞의 것이 실패해도 다음은 간다. */
  function enqueue(fn) {
    var job = queue.then(fn, fn);
    queue = job.then(function () {}, function () {});
    return job;
  }

  function flush() {
    clearTimeout(flushTimer);
    flushTimer = 0;
    while (buffer.length) {
      (function (chunk) {
        enqueue(function () {
          return post('/drawing-wizard/part-memory', { items: chunk }).then(function (d) {
            if (!d) { chunk.forEach(function (it) { if (it.label) { delete sent[it.key]; } }); return; }   // 다음 동기화 때 다시
            backfill(d.missing);
          });
        });
      })(buffer.splice(0, MAX_ITEMS));
    }
  }

  function push(item) {
    buffer.push(item);
    if (buffer.length >= MAX_ITEMS) { flush(); return; }
    if (!flushTimer) { flushTimer = setTimeout(flush, FLUSH_DELAY_MS); }
  }

  /** 분류 직후 — 특징과 지금 이름표를 남긴다(o.part 는 follow · 짝 규칙을 거친 최종 이름표). */
  function remember(o, res) {
    if (!on('store') || !o || !keyOk(o.key) || !res || !res.feat || !res.fv) { return; }
    var p = o.part || {}, src = p.src === 'user' ? 'user' : 'ai', label = p.label || res.label;
    var item = { key: o.key, f: f16b64(res.feat), fv: res.fv, label: label, src: src };
    if (res.ai) { item.ai = res.ai; }
    if (typeof res.conf === 'number') { item.conf = res.conf; }
    if (res.head) { item.head = String(res.head).replace(/\.m$/, ''); }
    sent[o.key] = label + '|' + src;
    push(item);
  }

  /** 이 주문 그림 키 → {label, src}. 같은 그림이 여러 시트에 있으면 사람 이름표가 이기고, 그다음은 나중 것. */
  function labelMap(sheets) {
    var map = {};
    (sheets || []).forEach(function (s) {
      ((s && s.objects) || []).forEach(function (o) {
        if (!o || o.type !== 'image' || !o.key || !o.part || !o.part.label) { return; }
        var cur = { label: o.part.label, src: o.part.src === 'user' ? 'user' : 'ai' }, prev = map[o.key];
        if (!prev || cur.src === 'user' || prev.src !== 'user') { map[o.key] = cur; }
      });
    });
    return map;
  }

  function syncNow() {
    syncTimer = 0;
    var map = labelMap(cfg.sheets());
    Object.keys(map).forEach(function (key) {
      var m = map[key], sig = m.label + '|' + m.src;
      if (sent[key] !== sig && keyOk(key)) { sent[key] = sig; push({ key: key, label: m.label, src: m.src }); }
    });
    flush();
  }

  function labelsChanged() {
    if (!on('store')) { return; }
    clearTimeout(syncTimer);
    syncTimer = setTimeout(syncNow, SYNC_DELAY_MS);
  }

  /** 서버에 특징이 없는 그림 — 모델이 이 브라우저에 이미 있으면 특징만 다시 뽑아 보낸다(24MB 를 새로 받지는 않는다). */
  function backfill(missing) {
    var ai = window.FomsPartAI;
    if (!missing || !missing.length || !cfg.imageFor || !ai || typeof ai.cached !== 'function') { return; }
    ai.cached().then(function (has) {
      if (!has) { return; }
      missing.forEach(function (key) {
        if (tried[key] || backfilled >= BACKFILL_MAX || !keyOk(key)) { return; }
        var img = cfg.imageFor(key);
        if (!img) { return; }
        tried[key] = true;
        backfilled += 1;
        ai.classify(img).then(function (res) {
          if (res && res.feat && res.fv) { push({ key: key, f: f16b64(res.feat), fv: res.fv }); }
        });
      });
    }, function () {});
  }

  /** 새 그림이 따를 사람 종류 — {label, sim, n, scope} 또는 null(꺼짐 · 없음 · 갈림 · 1.5초 넘음). */
  function follow(o, res) {
    if (!on('follow') || !o || !res || !res.feat || !res.fv) { return Promise.resolve(null); }
    var id = String(o.id);
    var ask = post('/drawing-wizard/part-memory/match', { mode: 'follow', items: [{
      id: id, f: f16b64(res.feat), fv: res.fv, key: o.key || '', ai: res.ai || '', conf: typeof res.conf === 'number' ? res.conf : 0
    }] }).then(function (d) {
      var v = (d && d.enabled && d.items) ? d.items[id] : null;
      return (v && v.label && !v.conflict) ? v : null;
    });
    var late = new Promise(function (resolve) { setTimeout(function () { resolve(null); }, FOLLOW_WAIT_MS); });
    return Promise.race([ask, late]);
  }

  /** 내부/도어로 고친 그림의 주방 짝 — 같은 보기(정면 · 입체) 그림이 딱 하나 더 있으면 그 id. */
  function partnerOf(sheet, o, label) {
    var v = VIEW[label];
    if (!v || !sheet) { return null; }
    var same = (sheet.objects || []).filter(function (x) {
      return x && x !== o && x.type === 'image' && x.part && VIEW[x.part.label] === v;
    });
    return same.length === 1 ? same[0].id : null;
  }

  /** 사람이 o 를 label 로 고쳤다 — 같은 시트의 닮은 AI 이름표 그림 [{id, sim}]. 사람 이름표 · 잠금 · 짝은 뺀다. */
  function spread(sheet, o, label) {
    if (!on('spread') || !sheet || !o || !keyOk(o.key)) { return Promise.resolve([]); }
    var partner = partnerOf(sheet, o, label), items = [];
    (sheet.objects || []).forEach(function (x) {
      if (!x || x === o || x.type !== 'image' || !keyOk(x.key) || !x.part || x.part.src === 'user' || x.locked) { return; }
      if (x.id === partner || x.part.label === label) { return; }
      items.push({ id: String(x.id), key: x.key, label: x.part.label || '미분류' });
    });
    if (!items.length) { return Promise.resolve([]); }
    flush();   // 고친 그림의 특징 줄이 먼저 들어간 뒤에 묻는다
    return enqueue(function () {
      return post('/drawing-wizard/part-memory/match', { mode: 'spread', key: o.key, label: label, items: items.slice(0, MAX_ITEMS) });
    }).then(function (d) { return (d && d.enabled && d.ids) ? d.ids : []; }, function () { return []; });
  }

  function isMem(part) { return !!part && part.src !== 'user' && /\.m$/.test(String(part.head || '')); }

  /** 기억을 따른 이름표의 판 표시 — 'h1' → 'h1.m'(서버 head 규칙 16자 안). */
  function memHead(head) {
    var h = String(head || 'h0').replace(/\.m$/, '');
    return (h.length > 14 ? h.slice(0, 14) : h) + '.m';
  }

  window.FomsPartMemory = {
    init: function (c) { cfg = c || null; },
    remember: remember, labelsChanged: labelsChanged, follow: follow, spread: spread,
    noteSim: function (id, sim) { if (typeof sim === 'number') { sims[id] = sim; } },
    simOf: function (id) { return typeof sims[id] === 'number' ? sims[id] : null; },
    isMem: isMem, memHead: memHead, f16b64: f16b64, labelMap: labelMap, partnerOf: partnerOf
  };
})();
