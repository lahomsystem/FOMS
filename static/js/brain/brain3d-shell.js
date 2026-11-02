/**
 * 회사 지식 '뇌 보기' 껍데기(설계서 7.6) — 반투명 두 반구 · 소뇌 · 뇌줄기를 **코드로** 빚는다(바깥 3D 모델 파일 없음 — 라이선스 문제 없음).
 *
 * 사장님 시제품(학습 폴더 design/brain3d_prototype/js/shell.js)에서 다듬은 것:
 * - '가까이 보면 유리 같은 주름': 반짝임(specular)을 빼고 무광(확산광 + 은은한 테두리)으로, 이랑은 밝게 · 고랑은 어둡게.
 * - '3/4 각도에서 먼 쪽 주름이 겹쳐 어지러움': 깊이만 먼저 쓰는 판(색 없음)을 한 번 그린 뒤 색 판은 **가장 앞 겉면만** 칠한다
 *   (먼 쪽 반구 · 뒷면이 비쳐 겹치지 않는다). 점 · 줄은 깊이 시험을 끄고 그려 껍데기 안쪽도 보인다.
 * - BufferGeometryUtils 대신 직접 만든 꼭짓점 공유 구(정이십면체 나누기)를 쓴다.
 * classic 스크립트 — 뇌 보기 탭을 열 때 import() 로 읽혀 window.FOMS_BRAIN3D_SHELL.create(THREE, layout, opts) 를 내놓는다.
 */
(function (root) {
  'use strict';

  var VS = [
    'attribute float aGroove;', 'varying vec3 vN;', 'varying vec3 vV;', 'varying float vG;',
    'void main() {',
    '  vec4 mv = modelViewMatrix * vec4(position, 1.0);',
    '  vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); vG = aGroove;',
    '  gl_Position = projectionMatrix * mv;', '}'
  ].join('\n');

  var FS = [
    'uniform vec3 uColor;', 'uniform vec3 uRim;', 'uniform float uOpacity;',
    'varying vec3 vN;', 'varying vec3 vV;', 'varying float vG;',
    'void main() {',
    '  vec3 n = normalize(vN);',
    '  float ndv = clamp(dot(n, normalize(vV)), 0.0, 1.0);',
    '  float rim = pow(1.0 - ndv, 2.5);',
    '  float diff = clamp(dot(n, normalize(vec3(-0.4, 0.8, 0.5))), 0.0, 1.0);',
    '  vec3 col = uColor * (0.32 + 0.68 * diff) * (1.0 - 0.55 * vG);',
    '  col = mix(col, uRim, rim * 0.45);',
    '  float a = uOpacity * (0.55 + 0.45 * rim) * (1.0 - 0.25 * vG);',
    '  gl_FragColor = vec4(col, a);', '}'
  ].join('\n');

  /** 꼭짓점을 나눠 갖는 단위 구(정이십면체를 level 번 나눔) — {position: Float32Array, index: Uint32Array}. */
  function icosphere(level) {
    var t = (1 + Math.sqrt(5)) / 2;
    var verts = [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
                 [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]].map(function (v) {
      var l = Math.hypot(v[0], v[1], v[2]);
      return [v[0] / l, v[1] / l, v[2] / l];
    });
    var faces = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4], [11, 10, 2],
                 [10, 7, 6], [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11],
                 [6, 2, 10], [8, 6, 7], [9, 8, 1]];
    for (var l = 0; l < level; l++) {
      var cache = new Map();
      var mid = function (a, b) {
        var key = a < b ? a * 1e6 + b : b * 1e6 + a;
        var hit = cache.get(key);
        if (hit !== undefined) return hit;
        var p = verts[a], q = verts[b];
        var m = [p[0] + q[0], p[1] + q[1], p[2] + q[2]];
        var len = Math.hypot(m[0], m[1], m[2]);
        verts.push([m[0] / len, m[1] / len, m[2] / len]);
        cache.set(key, verts.length - 1);
        return verts.length - 1;
      };
      var next = [];
      faces.forEach(function (f) {
        var ab = mid(f[0], f[1]), bc = mid(f[1], f[2]), ca = mid(f[2], f[0]);
        next.push([f[0], ab, ca], [f[1], bc, ab], [f[2], ca, bc], [ab, bc, ca]);
      });
      faces = next;
    }
    var position = new Float32Array(verts.length * 3);
    verts.forEach(function (v, i) { position.set(v, i * 3); });
    var index = new Uint32Array(faces.length * 3);
    faces.forEach(function (f, i) { index.set(f, i * 3); });
    return { position: position, index: index };
  }

  function create(THREE, L, opts) {
    var level = (opts && opts.level) || 6;

    /** shape(u) → {p, deep}(큰 고랑) 로 바탕을 빚고, 법선 쪽으로 작은 고랑(groove)을 판다. */
    function sculpt(lvl, shape, groove, depth) {
      var sphere = icosphere(lvl);
      var geo = new THREE.BufferGeometry();
      var pos = new THREE.BufferAttribute(sphere.position.slice(), 3);
      geo.setAttribute('position', pos);
      geo.setIndex(new THREE.BufferAttribute(sphere.index, 1));
      var n = pos.count;
      var u = sphere.position;
      var deep = new Float32Array(n);
      for (var i = 0; i < n; i++) {
        var r = shape(u[i * 3], u[i * 3 + 1], u[i * 3 + 2]);
        pos.setXYZ(i, r.p[0], r.p[1], r.p[2]);
        deep[i] = r.deep;
      }
      geo.computeVertexNormals();
      var nor = geo.attributes.normal;
      var g = new Float32Array(n);
      for (var j = 0; j < n; j++) {
        var x = pos.getX(j), y = pos.getY(j), z = pos.getZ(j);
        var small = groove(x, y, z, u[j * 3], u[j * 3 + 1], u[j * 3 + 2]);
        var d = depth.small * small + depth.deep * deep[j];
        pos.setXYZ(j, x - nor.getX(j) * d, y - nor.getY(j) * d, z - nor.getZ(j) * d);
        g[j] = Math.min(1, Math.max(small, deep[j]));
      }
      geo.setAttribute('aGroove', new THREE.BufferAttribute(g, 1));
      geo.computeVertexNormals();
      return geo;
    }

    /** 피질 주름 — 잡음이 0 을 지나는 선을 고랑으로(이마 · 관자엽은 앞뒤로 긴 이랑, 중심 고랑 둘레는 위아래로). */
    function foldGroove(s, x, y, z, ux, uy, uz) {
      var along = Math.max(L.smoothstep(0.25, 0.55, uz), L.temporalWeight(s, ux, uy, uz));
      var central = Math.exp(-Math.pow((uz - L.centralZ(uy)) / 0.22, 2)) * L.smoothstep(-0.1, 0.1, uy - L.sylvianY(uz));
      var f = 3.9;
      var w = 0.4 * L.noise3(x * 1.4 + 3.1, y * 1.4, z * 1.4 - 2.2);
      var n1 = L.noise3(x * f + w, y * f * (1 - 0.45 * central) - w, z * f * (1 - 0.5 * along) + 1.7);
      var g1 = 1 - L.smoothstep(0, 0.11, Math.abs(n1));
      return g1 * g1 * (3 - 2 * g1);
    }

    function hemisphere(s) {
      return sculpt(level, function (ux, uy, uz) {
        return { p: L.hemiPoint(s, ux, uy, uz), deep: L.fissureWeight(s, ux, uy, uz) };
      }, function (x, y, z, ux, uy, uz) { return foldGroove(s, x, y, z, ux, uy, uz); }, { small: 0.04, deep: 0.065 });
    }

    function cerebellum() {
      var c = [0, -0.4, -0.57], r = [0.5, 0.19, 0.29];
      return sculpt(Math.max(3, level - 1), function (ux, uy, uz) {
        var midline = Math.exp(-Math.pow(ux / 0.12, 2));
        var y = uy * r[1] * (uy > 0 ? 1 - 0.25 * uz * uz : 1);
        var z = uz * r[2] * (1 - 0.12 * midline);
        if (z > 0.12) z = 0.12 + (z - 0.12) * 0.35;
        y -= 0.04 * midline * Math.max(-uz, 0);
        var great = Math.exp(-Math.pow((uy + 0.05) / 0.08, 2)) * L.smoothstep(0.1, -0.5, uz);
        return { p: [c[0] + ux * r[0], c[1] + y, c[2] + z], deep: Math.max(0.6 * midline * L.smoothstep(0, -0.6, uz), great) };
      }, function (x, y, z, ux, uy, uz) {
        var a = Math.atan2(uy, -uz) * 21 + 3.2 * L.noise3(x * 2.5, y * 2.5, z * 2.5);
        return 1 - L.smoothstep(0, 0.32, Math.abs(Math.sin(a)));
      }, { small: 0.014, deep: 0.035 });
    }

    function brainstem() {
      var profile = [[0.0, 0.06], [0.09, 0.05], [0.115, -0.04], [0.125, -0.13], [0.1, -0.24], [0.08, -0.34],
                     [0.068, -0.46], [0.05, -0.54], [0.0, -0.55]].map(function (p) { return new THREE.Vector2(p[0], p[1]); });
      var geo = new THREE.LatheGeometry(profile, 48);
      geo.rotateX(-0.26);
      geo.translate(0, -0.24, -0.2);
      geo.setAttribute('aGroove', new THREE.BufferAttribute(new Float32Array(geo.attributes.position.count), 1));
      return geo;
    }

    function colorMaterial(opacity) {
      return new THREE.ShaderMaterial({
        vertexShader: VS, fragmentShader: FS, transparent: true, depthWrite: false, depthFunc: THREE.LessEqualDepth,
        uniforms: { uColor: { value: new THREE.Color('#d8c3cc') }, uRim: { value: new THREE.Color('#efe4f7') },
                    uOpacity: { value: opacity } }
      });
    }

    var group = new THREE.Group();
    var depthMat = new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: true });
    var cortexMat = colorMaterial(0.42);
    var lowerMat = colorMaterial(0.34);
    var geos = [hemisphere(-1), hemisphere(1), cerebellum(), brainstem()];
    geos.forEach(function (geo, i) {
      var prepass = new THREE.Mesh(geo, depthMat);  // 깊이만 — 가장 앞 겉면만 칠하게
      prepass.renderOrder = 0;
      var paint = new THREE.Mesh(geo, i < 2 ? cortexMat : lowerMat);
      paint.renderOrder = 1;
      group.add(prepass, paint);
    });

    return {
      group: group,
      /** 고른 동안 흐리게. */
      setDim: function (dim) {
        cortexMat.uniforms.uOpacity.value = dim ? 0.24 : 0.42;
        lowerMat.uniforms.uOpacity.value = dim ? 0.2 : 0.34;
      },
      dispose: function () {
        geos.forEach(function (geo) { geo.dispose(); });
        [depthMat, cortexMat, lowerMat].forEach(function (m) { m.dispose(); });
      }
    };
  }

  root.FOMS_BRAIN3D_SHELL = { create: create, icosphere: icosphere };
})(typeof window !== 'undefined' ? window : globalThis);
