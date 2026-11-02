/**
 * 회사 지식 '뇌 보기' 점 · 신경 줄 · 빛 흐름(설계서 7.6) — 점은 InstancedMesh 하나(수천 개도 그리기 한 번).
 *
 * 시제품(학습 폴더 design/brain3d_prototype/js/graph.js)에서 다듬은 것:
 * - '평소 보이는 줄의 실뭉치': 평소엔 줄을 **그리지 않는다** — 고른 항목과 이웃 사이 줄만(링크 종류 색) 그린다.
 * - '가운데 점 뭉침': 점은 더하기 섞기(additive) 대신 보통 섞기로(겹쳐도 하얗게 타지 않음), 수가 많으면 점 · 번짐을 줄인다.
 * - 점 밝기 = 쓰인 횟수(log), 은퇴 = 회색(어둡게), 낡음 = 주황, 초안 = 흐린 테(속이 빈 고리) — 색 · 표시는 brain3d-core.js.
 * - 움직임 줄이기면 빛 흐름을 만들지 않는다.
 * classic 스크립트 — import() 로 읽혀 window.FOMS_BRAIN3D_NODES.create(THREE, deps, scene, opts).
 */
(function (root) {
  'use strict';

  var NODE_VS = [
    'attribute vec3 aColor;', 'attribute float aGlow;', 'attribute float aRing;', 'attribute float aHi;',
    'uniform float uSel;', 'uniform float uScale;',
    'varying vec3 vColor;', 'varying float vGlow;', 'varying float vRing;', 'varying float vHi;', 'varying vec2 vUv;',
    'void main() {',
    '  vec4 mv = modelViewMatrix * instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0);',
    '  float size = uScale * (0.8 + 0.5 * aGlow);',
    '  if (uSel > 0.5) size *= aHi > 1.5 ? 2.6 : (aHi > 0.5 ? 1.6 : 0.8);',
    '  mv.xy += position.xy * size;',
    '  gl_Position = projectionMatrix * mv;',
    '  vColor = aColor; vGlow = aGlow; vRing = aRing; vHi = aHi; vUv = uv;', '}'
  ].join('\n');

  var NODE_FS = [
    'uniform float uSel;', 'uniform float uDim;', 'uniform float uHalo;',
    'varying vec3 vColor;', 'varying float vGlow;', 'varying float vRing;', 'varying float vHi;', 'varying vec2 vUv;',
    'void main() {',
    '  float r = length(vUv - 0.5) * 2.0;',
    '  if (r > 1.0) discard;',
    '  float core = smoothstep(0.42, 0.28, r);',
    '  float halo = exp(-r * r * 5.0) * 0.35 * uHalo;',
    '  float ring = smoothstep(0.1, 0.0, abs(r - 0.52));',
    '  float bright = 0.5 + 0.5 * vGlow;',
    '  vec3 col = vColor;',
    '  float a = vRing > 0.5 ? ring * 0.7 : max(core, halo) * bright;',
    '  if (uSel > 0.5) {',
    '    if (vHi > 1.5) { col = mix(col, vec3(1.0), 0.55 * core); a = max(core, ring * 0.9) + halo; }',
    '    else if (vHi > 0.5) { a = max(a, max(core, halo) * 0.95); }',
    '    else { a *= uDim; }',
    '  }',
    '  gl_FragColor = vec4(col, clamp(a, 0.0, 1.0));', '}'
  ].join('\n');

  var PULSE_VS = [
    'attribute vec3 aColor;', 'uniform float uSize;', 'varying vec3 vColor;',
    'void main() {',
    '  vec4 mv = modelViewMatrix * vec4(position, 1.0);',
    '  gl_PointSize = uSize / -mv.z;', '  gl_Position = projectionMatrix * mv;', '  vColor = aColor;', '}'
  ].join('\n');

  var PULSE_FS = [
    'varying vec3 vColor;',
    'void main() {',
    '  float r = length(gl_PointCoord - 0.5) * 2.0;',
    '  float a = exp(-r * r * 5.0);',
    '  gl_FragColor = vec4(mix(vColor, vec3(1.0), 0.45 * a), a);', '}'
  ].join('\n');

  var SEGMENTS = 20;
  var PULSES_PER_LINK = 2;

  function create(THREE, deps, scene, opts) {
    var L = deps.layout;
    var core = deps.core;
    var items = opts.items;
    var pos = opts.pos;
    var n = items.length;
    var many = n > 1000;
    var maxUses = items.reduce(function (m, it) { return Math.max(m, it.usage || 0); }, 0);
    var tmp = [0, 0, 0];

    var plane = new THREE.PlaneGeometry(1, 1);
    function attr(size) { return new THREE.InstancedBufferAttribute(new Float32Array(n * size), size); }
    var aColor = attr(3), aGlow = attr(1), aRing = attr(1), aHi = attr(1);
    plane.setAttribute('aColor', aColor);
    plane.setAttribute('aGlow', aGlow);
    plane.setAttribute('aRing', aRing);
    plane.setAttribute('aHi', aHi);
    var nodeMat = new THREE.ShaderMaterial({
      vertexShader: NODE_VS, fragmentShader: NODE_FS, transparent: true, depthWrite: false, depthTest: false,
      uniforms: { uSel: { value: 0 }, uScale: { value: many ? 0.032 : 0.05 }, uDim: { value: many ? 0.3 : 0.38 },
                  uHalo: { value: many ? 0.35 : 1 } }
    });
    var nodes = new THREE.InstancedMesh(plane, nodeMat, Math.max(1, n));
    nodes.count = n;
    nodes.frustumCulled = false;
    nodes.renderOrder = 20;
    var m = new THREE.Matrix4();
    items.forEach(function (it, i) {
      m.makeTranslation(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]);
      nodes.setMatrixAt(i, m);
      var c = core.pointColor(it.type, it.flags, opts.display);
      aColor.setXYZ(i, c[0], c[1], c[2]);
      aGlow.setX(i, core.glow(it.usage, maxUses, it.flags));
      aRing.setX(i, it.flags & core.FLAG_DRAFT ? 1 : 0);
    });
    scene.add(nodes);

    var lineMat = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.85, depthWrite: false,
                                                depthTest: false, blending: THREE.AdditiveBlending });
    var pulseMat = new THREE.ShaderMaterial({
      vertexShader: PULSE_VS, fragmentShader: PULSE_FS, transparent: true, depthWrite: false, depthTest: false,
      blending: THREE.AdditiveBlending,
      uniforms: { uSize: { value: 110 * Math.min(window.devicePixelRatio || 1, 2) } }
    });
    var lines = null;
    var pulses = null;
    var flows = [];

    function clearSelection() {
      if (lines) { scene.remove(lines); lines.geometry.dispose(); lines = null; }
      if (pulses) { scene.remove(pulses); pulses.geometry.dispose(); pulses = null; }
      flows = [];
    }

    /** 고른 항목 → 이웃 줄(곡선) — 링크 종류 색. */
    function buildLines(links) {
      var p = new Float32Array(links.length * SEGMENTS * 6);
      var c = new Float32Array(links.length * SEGMENTS * 6);
      var k = 0;
      links.forEach(function (l) {
        var col = core.linkColor(l.kind, opts.display);
        for (var s = 0; s < SEGMENTS; s++) {
          [s / SEGMENTS, (s + 1) / SEGMENTS].forEach(function (t) {
            L.curvePoint(pos, l.from, l.to, t, tmp);
            p.set(tmp, k);
            c.set(col, k);
            k += 3;
          });
        }
      });
      var geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(p, 3));
      geo.setAttribute('color', new THREE.BufferAttribute(c, 3));
      var seg = new THREE.LineSegments(geo, lineMat);
      seg.frustumCulled = false;
      seg.renderOrder = 15;
      return seg;
    }

    function buildPulses(links) {
      var geo = new THREE.BufferGeometry();
      var count = links.length * PULSES_PER_LINK;
      geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3));
      var col = new Float32Array(count * 3);
      links.forEach(function (l, i) {
        var c = core.linkColor(l.kind, opts.display);
        for (var k = 0; k < PULSES_PER_LINK; k++) col.set(c, (i * PULSES_PER_LINK + k) * 3);
      });
      geo.setAttribute('aColor', new THREE.BufferAttribute(col, 3));
      var pts = new THREE.Points(geo, pulseMat);
      pts.frustumCulled = false;
      pts.renderOrder = 30;
      return pts;
    }

    return {
      mesh: nodes,
      /**
       * 고르기 — idx = -1 이면 해제. links = [{from: 번호, to: 번호, kind}](고른 항목 쪽이 from), lit = 이웃 번호들.
       * withPulses 면 고른 항목에서 이웃 쪽으로 빛이 흐른다(움직임 줄이기면 끈다).
       */
      select: function (idx, lit, links, withPulses) {
        clearSelection();
        aHi.array.fill(0);
        nodeMat.uniforms.uSel.value = idx >= 0 ? 1 : 0;
        if (idx >= 0) {
          lit.forEach(function (i) { aHi.setX(i, 1); });
          aHi.setX(idx, 2);
          if (links.length) {
            lines = buildLines(links);
            scene.add(lines);
            if (withPulses) {
              flows = links;
              pulses = buildPulses(links);
              scene.add(pulses);
            }
          }
        }
        aHi.needsUpdate = true;
      },
      /** 빛 흐름이 있나(있으면 매 장면 그린다). */
      flowing: function () { return !!pulses; },
      /** 매 장면 — 빛 흐름 자리. t = 초. */
      update: function (t) {
        if (!pulses) return;
        var arr = pulses.geometry.attributes.position.array;
        flows.forEach(function (l, i) {
          for (var k = 0; k < PULSES_PER_LINK; k++) {
            var phase = (t * 0.55 + k / PULSES_PER_LINK + (i * 0.137) % 1) % 1;
            L.curvePoint(pos, l.from, l.to, phase, tmp);
            arr.set(tmp, (i * PULSES_PER_LINK + k) * 3);
          }
        });
        pulses.geometry.attributes.position.needsUpdate = true;
      },
      dispose: function () {
        clearSelection();
        scene.remove(nodes);
        nodes.dispose();
        plane.dispose();
        [nodeMat, lineMat, pulseMat].forEach(function (mm) { mm.dispose(); });
      }
    };
  }

  root.FOMS_BRAIN3D_NODES = { create: create };
})(typeof window !== 'undefined' ? window : globalThis);
