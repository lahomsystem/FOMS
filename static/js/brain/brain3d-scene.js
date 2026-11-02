/**
 * 회사 지식 '뇌 보기' 무대(설계서 7.6) — renderer · 카메라 · 돌리기(OrbitControls) · 그리기 고리 · 누른 점 찾기 · 정리.
 *
 * - WebGL 은 failIfMajorPerformanceCaveat 로 연다 — 소프트웨어로만 그릴 수 있으면 만들기가 실패하고 탭이 숨는다(brain3d-tab.js).
 * - **움직일 때만 그린다**(시제품은 늘 그렸다 — 노트북 전지): 돌리기 · 확대 중 · 자동 돌기 · 빛 흐름 · 고르기 · 크기 바뀜.
 *   탭이 안 보이면 브라우저가 고리를 멈춘다. 그린 장면 수를 1초마다 세어 onFps 로 알린다(측정용).
 * - 자리는 키 해시(brain3d-layout.js positionFor) — 같은 항목은 늘 같은 자리.
 * - dispose() 가 고리 · 관찰자 · 돌리기 · 껍데기 · 점 · 이름표 · renderer(+ WebGL 문맥 놓기)를 모두 정리한다.
 * classic 스크립트 — import() 로 읽혀 window.FOMS_BRAIN3D_SCENE.create(THREE, OrbitControls, deps, host, opts).
 */
(function (root) {
  'use strict';

  var PICK_RADIUS_PX = 14;
  var CLICK_MOVE_PX = 5;

  function create(THREE, OrbitControls, deps, host, opts) {
    var canvasHost = host.querySelector('[data-brain3d-canvas]');
    var svg = host.querySelector('[data-brain3d-labels]');
    var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance',
                                             failIfMajorPerformanceCaveat: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);
    canvasHost.appendChild(renderer.domElement);

    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(36, 1, 0.05, 50);
    camera.position.set(3.0, 0.9, 1.25);
    var controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, -0.1, -0.06);
    controls.enableDamping = true;
    controls.minDistance = 1.1;
    controls.maxDistance = 7;
    controls.autoRotate = !opts.reduced;
    controls.autoRotateSpeed = 0.45;
    controls.update();

    var shell = deps.shell.create(THREE, deps.layout, {});
    scene.add(shell.group);
    var pos = deps.layout.layoutAll(opts.items.map(function (it) { return { key: it.key, type: it.type, layer: it.layer }; }));
    var nodes = deps.nodes.create(THREE, deps, scene, { items: opts.items, pos: pos, display: opts.display });
    var labels = deps.labels.create(svg);
    var dirty = true;

    function markDirty() { dirty = true; }
    controls.addEventListener('change', markDirty);
    controls.addEventListener('start', function () { controls.autoRotate = false; });

    function resize() {
      var w = canvasHost.clientWidth || 1;
      var h = canvasHost.clientHeight || 1;
      renderer.setSize(w, h, false);
      svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      dirty = true;
    }
    var ro = new ResizeObserver(resize);
    ro.observe(canvasHost);
    resize();

    var v = new THREE.Vector3();
    /** 점 번호 → 칸 기준 화면 자리(px). 카메라 뒤면 null. */
    function project(i) {
      v.set(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]).project(camera);
      if (v.z > 1) return null;
      return { x: (v.x * 0.5 + 0.5) * canvasHost.clientWidth, y: (-v.y * 0.5 + 0.5) * canvasHost.clientHeight, depth: v.z };
    }

    /** 누른 자리에서 가장 가까운 점(화면 거리 — 레이캐스트 대신 투영, 5천 개도 1ms 안). */
    function pickAt(px, py) {
      var best = -1;
      var bestD = PICK_RADIUS_PX * PICK_RADIUS_PX;
      var bestDepth = 2;
      for (var i = 0; i < opts.items.length; i++) {
        var p = project(i);
        if (!p) continue;
        var d = (p.x - px) * (p.x - px) + (p.y - py) * (p.y - py);
        if (d < bestD - 4 || (Math.abs(d - bestD) <= 4 && p.depth < bestDepth)) {
          best = i; bestD = d; bestDepth = p.depth;
        }
      }
      return best;
    }

    var down = null;
    function onDown(e) { down = { x: e.clientX, y: e.clientY }; }
    function onUp(e) {
      if (!down) return;
      var moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      down = null;
      if (moved > CLICK_MOVE_PX) return;
      var r = renderer.domElement.getBoundingClientRect();
      opts.onPick(pickAt(e.clientX - r.left, e.clientY - r.top));
    }
    renderer.domElement.addEventListener('pointerdown', onDown);
    renderer.domElement.addEventListener('pointerup', onUp);

    var frames = 0;
    var lastFps = performance.now();
    var start = performance.now();
    renderer.setAnimationLoop(function () {
      var moving = controls.update();
      var flowing = nodes.flowing();
      if (!(dirty || moving || flowing || controls.autoRotate)) return;
      dirty = false;
      nodes.update((performance.now() - start) / 1000);
      renderer.render(scene, camera);
      labels.update(project);
      frames++;
      var now = performance.now();
      if (now - lastFps >= 1000) {
        if (opts.onFps) opts.onFps((frames * 1000) / (now - lastFps));
        frames = 0;
        lastFps = now;
      }
    });

    return {
      /** 고르기 — idx -1 = 해제. lit = 이웃 번호, links = [{from, to, kind}], named = 이름표 [{idx, name, type}](첫째 = 고른 항목). */
      select: function (idx, lit, links, named) {
        nodes.select(idx, lit, links, !opts.reduced);
        shell.setDim(idx >= 0);
        labels.set(named[0] || null, named.slice(1));
        dirty = true;
      },
      setAutoRotate: function (on) { controls.autoRotate = !!on && !opts.reduced; dirty = true; },
      rendererName: function () {
        var gl = renderer.getContext();
        var ext = gl.getExtension('WEBGL_debug_renderer_info');
        return String(ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER));
      },
      screenOf: project,
      dispose: function () {
        renderer.setAnimationLoop(null);
        ro.disconnect();
        renderer.domElement.removeEventListener('pointerdown', onDown);
        renderer.domElement.removeEventListener('pointerup', onUp);
        controls.dispose();
        labels.clear();
        nodes.dispose();
        scene.remove(shell.group);
        shell.dispose();
        renderer.dispose();
        renderer.forceContextLoss();
        renderer.domElement.remove();
      }
    };
  }

  root.FOMS_BRAIN3D_SCENE = { create: create };
})(typeof window !== 'undefined' ? window : globalThis);
