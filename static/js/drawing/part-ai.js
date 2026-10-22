/**
 * 도면 마법사 — 그림 종류 자동 분류(브라우저 안 AI).
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.1
 * - 그림은 브라우저 밖으로 나가지 않는다. 모델(DINOv2-small int8, Apache-2.0)과 실행기(onnxruntime-web)만
 *   처음 쓸 때 한 번 받는다(perf guard G2: 사용 시점 lazy 로드). 모델은 Cache Storage 에 둬서 다시 받지 않는다.
 * - 특징(768 = CLS + 패치 평균, L2 정규화) → 작은 분류기(part-head.json, 운영 그림으로 가르친 가중치) → 종류.
 * - 확신이 문턱보다 낮으면 '미분류'. 어떤 실패든 null 을 돌려 사람이 손으로 고르게 한다(화면을 막지 않음).
 *
 * window.FomsPartAI = { LABELS, KEY_LABELS, classify(img) → Promise<{label, ai, conf, head}|null>, warm() }
 */
(function () {
  'use strict';
  if (window.FomsPartAI) { return; }

  var ORT_VERSION = '1.30.0';
  var ORT_DIR = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@' + ORT_VERSION + '/dist/';
  var ORT_SRC = ORT_DIR + 'ort.wasm.min.js';
  // onnx-community/dinov2-small 커밋 고정(sha256 c179f8f7… = 실험에 쓴 파일과 같음)
  var MODEL_URL = 'https://huggingface.co/onnx-community/dinov2-small/resolve/' +
    '8b1f705a3a7f6f062f6bdd21986c1583d3ef105d/onnx/model_quantized.onnx';
  var CACHE_NAME = 'foms-part-ai-v1';
  var SIZE = 224;
  var MEAN = [0.485, 0.456, 0.406];
  var STD = [0.229, 0.224, 0.225];
  var LABELS = ['정면·내부', '정면·도어', '입체·내부', '입체·도어', '평면·상판', '서랍 단면', '부품 상세', '사진', '그림 아님'];
  var UNSURE = '미분류';
  // 숫자키 1~9 = LABELS 순서, 0 = 미분류
  var KEY_LABELS = LABELS.concat([UNSURE]);

  var me = document.currentScript;
  var HEAD_URL = (me && me.getAttribute('data-head-url')) || '/static/js/drawing/part-head.json';
  var readyPromise = null;
  var warned = false;

  function warnOnce(what, err) {
    if (warned) { return; }
    warned = true;
    console.warn('[dws-part-ai] ' + what, err);
  }

  function loadScript(src) {
    if (window.ort && window.ort.InferenceSession) { return Promise.resolve(); }
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.async = true;
      s.crossOrigin = 'anonymous';
      s.onload = function () { resolve(); };
      s.onerror = function () { reject(new Error('ort load failed')); };
      document.head.appendChild(s);
    });
  }

  function fetchModel() {
    var useCache = typeof window.caches !== 'undefined';
    var fromNet = function () {
      return fetch(MODEL_URL, { mode: 'cors', credentials: 'omit' }).then(function (resp) {
        if (!resp.ok) { throw new Error('model ' + resp.status); }
        if (useCache) {
          var copy = resp.clone();
          window.caches.open(CACHE_NAME).then(function (c) { return c.put(MODEL_URL, copy); }).catch(function () {});
        }
        return resp.arrayBuffer();
      });
    };
    if (!useCache) { return fromNet(); }
    return window.caches.open(CACHE_NAME)
      .then(function (c) { return c.match(MODEL_URL); })
      .then(function (hit) { return hit ? hit.arrayBuffer() : fromNet(); })
      .catch(fromNet);
  }

  function fetchHead() {
    return fetch(HEAD_URL, { credentials: 'same-origin' }).then(function (resp) {
      if (!resp.ok) { throw new Error('head ' + resp.status); }
      return resp.json();
    }).then(function (h) {
      if (!h || !Array.isArray(h.labels) || !Array.isArray(h.W) || !Array.isArray(h.b)) { throw new Error('head shape'); }
      return h;
    });
  }

  /** 모델·실행기·분류기를 한 번만 준비한다(실패하면 다음 호출에서 다시 시도). */
  function warm() {
    if (readyPromise) { return readyPromise; }
    readyPromise = Promise.all([loadScript(ORT_SRC), fetchModel(), fetchHead()]).then(function (r) {
      var ort = window.ort;
      ort.env.wasm.wasmPaths = ORT_DIR;
      ort.env.wasm.numThreads = 1;   // 교차 출처 격리가 없는 페이지 — 단일 스레드
      return ort.InferenceSession.create(r[1], { executionProviders: ['wasm'] }).then(function (sess) {
        return { ort: ort, sess: sess, head: r[2] };
      });
    }).catch(function (err) {
      readyPromise = null;
      throw err;
    });
    return readyPromise;
  }

  /** 흰 여백으로 정사각형을 만든 뒤 224×224 로 줄이고(실험의 prep 과 같은 순서) CHW 로 정규화한다. */
  function toTensor(ort, img) {
    var nw = img.naturalWidth || img.width, nh = img.naturalHeight || img.height;
    if (!nw || !nh) { throw new Error('empty image'); }
    var canvas = document.createElement('canvas');
    canvas.width = SIZE; canvas.height = SIZE;
    var ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, SIZE, SIZE);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    var sc = SIZE / Math.max(nw, nh);
    var dw = nw * sc, dh = nh * sc;
    ctx.drawImage(img, (SIZE - dw) / 2, (SIZE - dh) / 2, dw, dh);
    var px = ctx.getImageData(0, 0, SIZE, SIZE).data;
    var plane = SIZE * SIZE;
    var data = new Float32Array(3 * plane);
    for (var i = 0; i < plane; i++) {
      for (var c = 0; c < 3; c++) {
        data[c * plane + i] = (px[i * 4 + c] / 255 - MEAN[c]) / STD[c];
      }
    }
    return new ort.Tensor('float32', data, [1, 3, SIZE, SIZE]);
  }

  /** last_hidden_state[0] → [CLS, 패치 평균] 768 차원, L2 정규화. */
  function pool(out) {
    var t = out.last_hidden_state || out[Object.keys(out)[0]];
    var dims = t.dims, tokens = dims[1], d = dims[2], v = t.data;
    var feat = new Float32Array(2 * d);
    for (var k = 0; k < d; k++) { feat[k] = v[k]; }
    for (var j = 1; j < tokens; j++) {
      for (var m = 0; m < d; m++) { feat[d + m] += v[j * d + m]; }
    }
    var norm = 0;
    for (var n = 0; n < d; n++) { feat[d + n] /= (tokens - 1); }
    for (var q = 0; q < feat.length; q++) { norm += feat[q] * feat[q]; }
    norm = Math.sqrt(norm) + 1e-9;
    for (var r = 0; r < feat.length; r++) { feat[r] /= norm; }
    return feat;
  }

  function predict(head, feat) {
    var best = -1, bestP = -Infinity, logits = [], maxL = -Infinity;
    for (var c = 0; c < head.labels.length; c++) {
      var w = head.W[c], s = head.b[c];
      for (var i = 0; i < feat.length; i++) { s += w[i] * feat[i]; }
      logits.push(s);
      if (s > maxL) { maxL = s; }
    }
    var sum = 0;
    var exps = logits.map(function (l) { var e = Math.exp(l - maxL); sum += e; return e; });
    exps.forEach(function (e, idx) { if (e > bestP) { bestP = e; best = idx; } });
    return { label: head.labels[best], conf: bestP / sum };
  }

  /** 불러온 <img>(같은 출처) 한 장의 종류. 실패하면 null. */
  function classify(img) {
    return warm().then(function (ctx) {
      var feeds = {};
      feeds[ctx.sess.inputNames[0]] = toTensor(ctx.ort, img);
      return ctx.sess.run(feeds).then(function (out) {
        var p = predict(ctx.head, pool(out));
        var th = typeof ctx.head.threshold === 'number' ? ctx.head.threshold : 0.5;
        var conf = Math.round(p.conf * 1000) / 1000;
        return { label: conf >= th ? p.label : UNSURE, ai: p.label, conf: conf, head: String(ctx.head.version || 'h0') };
      });
    }).catch(function (err) {
      warnOnce('분류를 건너뜁니다(손으로 고르세요)', err);
      return null;
    });
  }

  window.FomsPartAI = { LABELS: LABELS, KEY_LABELS: KEY_LABELS, UNSURE: UNSURE, classify: classify, warm: warm };
})();
