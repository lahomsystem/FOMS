/** 긴급 사이렌: 사용자 입력에서 오디오 준비, 컨텍스트 재사용, 8초 상한·확인 시 정지.
 *  생산 현장 알람 소리 표(새 일 · 멈춤 · 띠)와 되풀이 — 설계서 docs/specs/2026-11-28-production-floor-alarm_SPEC.md §3.
 *  start(알림 종류)가 이름 앞머리로 소리를 고른다. 빈 값 · 그 밖 종류 = 지금 사이렌 그대로(값 · 동작 안 바뀜). */
(function () {
  'use strict';
  if (window.FOMSUrgentSound) return;
  var ctx = null, wave = null, voice = null, active = false, generation = 0;
  var status = '소리 켜기·시험을 눌러 사이렌과 기기 음량을 확인해 주세요.';
  // ── 생산 알람 소리 표(§3-1, 사장님이 들으신 시안 값): 줄 = [Hz, 초](Hz 0 = 쉼), cycle = 한 마디(뒤 쉼 포함) ──
  var SOUNDS = {
    'new': { wave: 'square', cycle: 2.6, notes: [[880, 0.22], [1320, 0.3], [0, 0.15], [880, 0.22], [1320, 0.3]] },
    stop: { wave: 'square', cycle: 1.5,
      notes: [[1760, 0.12], [0, 0.08], [1760, 0.12], [0, 0.08], [1760, 0.12], [0, 0.08], [1760, 0.12]] },
    band: { wave: 'triangle', cycle: 0.5, notes: [[660, 0.5]] }
  };
  var FLOOR_GAIN = 0.9; // 생산 소리는 낼 수 있는 큰 크기 — 실제 크기는 기기 미디어 음량(§3-4). 사이렌 0.12 는 그대로.
  // 되풀이(§2-2): [알람 뒤 몇 초에, 몇 초 동안] — 처음 20초 → 1분마다 6초 → 5분(300초)부터 소리만 그친다(화면은 남는다).
  var REPEAT = [[0, 20], [60, 6], [120, 6], [180, 6], [240, 6]];
  var LIMIT = 300;
  var kind = '', since = 0, timers = [], muted = false;

  function kindOf(name) {
    var n = String(name || '');
    if (SOUNDS[n]) return n;
    // 사장님 답 2차 3: 담당 변경은 받은 사람 · 원래 담당 둘 다 새 일 소리(…_STOP_TAKEN 도 같다).
    if (n.indexOf('PRODUCTION_FLOOR_NEW') === 0 || n === 'PRODUCTION_FLOOR_STOP_TAKEN') return 'new';
    if (n.indexOf('PRODUCTION_FLOOR_STOP') === 0) return 'stop';
    if (n.indexOf('PRODUCTION_FLOOR_NOTICE') === 0) return 'band';
    return '';
  }
  function running() { return !!ctx && ctx.state === 'running'; }
  function state() { return muted ? 'off' : (running() ? 'on' : 'locked'); }
  function sync() {
    document.querySelectorAll('[data-foms-urgent-sound-status]').forEach(function (el) { el.textContent = status; });
    try { document.dispatchEvent(new CustomEvent('foms:urgent-sound-state', { detail: state() })); } catch (e) { /* 옛 브라우저 */ }
  }
  function report(message, error) {
    status = message;
    sync();
    if (error) console.warn('[urgent-sound]', message, error);
  }
  function release() {
    if (!voice) return;
    var old = voice;
    voice = null;
    old.osc.onended = null;
    old.osc.stop();
    old.osc.disconnect();
    old.gain.disconnect();
  }
  function clearTimers() {
    timers.forEach(function (t) { clearTimeout(t); });
    timers = [];
  }
  function stop() {
    active = false;
    generation += 1;
    clearTimers();
    release();
    if (ctx && ctx.state === 'running') report('사이렌 준비됨 · 탭 음소거와 기기 음량을 확인해 주세요.');
  }
  function frequencyCurve(seconds, isTest) {
    var values = new Float32Array(Math.ceil(seconds * 256) + 1);
    var wailEnd = isTest ? 1.6 : 3.2;
    for (var i = 0; i < values.length; i += 1) {
      var t = seconds * i / (values.length - 1);
      // Wail → Yelp → 빠른 Priority. 전환점도 저음에서 이어져 음높이가 튀지 않는다.
      var phase = t < wailEnd ? t / 1.6 :
        (t < 6.4 ? (t - wailEnd) / 0.4 : (t - 6.4) / 0.16);
      values[i] = 650 + 900 * (1 - Math.cos(2 * Math.PI * phase)) / 2;
    }
    return values;
  }
  function tone(seconds, isTest) {
    release();
    if (!ctx || ctx.state !== 'running') return;
    // 정규화된 배음으로 전자 사이렌 스피커의 날카로운 질감. 외부 음원·타이머 없음.
    if (!wave) wave = ctx.createPeriodicWave(new Float32Array(9),
      new Float32Array([0, 1, 0.12, 0.45, 0.08, 0.2, 0.04, 0.1, 0.02]));
    var osc = ctx.createOscillator(), gain = ctx.createGain(), now = ctx.currentTime;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.setPeriodicWave(wave);
    osc.frequency.setValueCurveAtTime(frequencyCurve(seconds, isTest), now, seconds);
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.12, now + 0.08);
    gain.gain.setValueAtTime(0.12, now + seconds - 0.15);
    gain.gain.linearRampToValueAtTime(0, now + seconds);
    voice = { osc: osc, gain: gain };
    osc.onended = function () {
      if (!voice || voice.osc !== osc) return;
      voice = null;
      osc.disconnect();
      gain.disconnect();
      report(isTest ? '시험 재생 완료 · 소리가 들리는지 확인해 주세요.' : '사이렌 재생 완료 · 긴급 알림은 확인할 때까지 남아 있어요.');
    };
    osc.start(now);
    osc.stop(now + seconds);
    report('사이렌 재생 중 · 기기에서 소리가 들리는지 확인해 주세요.');
  }
  // 생산 알람 한 번 울림: seconds 안에 들어가는 마디만큼(0 = 한 마디). 발진기 하나 + 크기 줄만 바꾼다.
  function ring(name, seconds) {
    var s = SOUNDS[name], span = 0, len = 0;
    release();
    if (!s || muted || !running()) return;
    var osc = ctx.createOscillator(), gain = ctx.createGain(), now = ctx.currentTime;
    s.notes.forEach(function (n) { span += n[1]; });
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = s.wave;
    gain.gain.setValueAtTime(0, now);
    for (var at = 0; at === 0 || at + span <= seconds + 1e-6; at += s.cycle) {
      var t = now + at;
      s.notes.forEach(function (n) {
        if (n[0]) {
          osc.frequency.setValueAtTime(n[0], t);
          gain.gain.setValueAtTime(0, t);
          gain.gain.linearRampToValueAtTime(FLOOR_GAIN, t + 0.01);
          gain.gain.setValueAtTime(FLOOR_GAIN, t + n[1] - 0.01);
          gain.gain.linearRampToValueAtTime(0, t + n[1]);
        }
        t += n[1];
      });
      len = at + span;
    }
    voice = { osc: osc, gain: gain };
    osc.onended = function () {
      if (!voice || voice.osc !== osc) return;
      voice = null;
      osc.disconnect();
      gain.disconnect();
    };
    osc.start(now);
    osc.stop(now + len);
  }
  // 알람 뒤 elapsed 초일 때 남은 울림: [지금부터 몇 초 뒤, 몇 초 동안].
  function plan(elapsed) {
    var out = [];
    REPEAT.forEach(function (w) {
      var from = Math.max(w[0], elapsed), end = w[0] + w[1];
      if (from < end) out.push([from - elapsed, end - from]);
    });
    return out;
  }
  // late = 소리가 늦게 켜짐(창을 눌러 켠 때) — 쉬는 틈이어도 바로 한 번(6초) 울리고 시간표를 잇는다.
  function schedule(late) {
    clearTimers();
    var name = kind, elapsed = (Date.now() - since) / 1000, left = plan(elapsed);
    if (name === 'band') { ring('band', 0); return; }
    if (late && elapsed < LIMIT && (!left.length || left[0][0] > 0)) left.unshift([0, REPEAT[1][1]]);
    left.forEach(function (w) {
      if (w[0] <= 0) { ring(name, w[1]); return; }
      timers.push(setTimeout(function () { if (active && kind === name) ring(name, w[1]); }, w[0] * 1000));
    });
  }
  function start(name) {
    stop();
    active = true;
    kind = kindOf(name);
    since = Date.now();
    if (!ctx || ctx.state !== 'running') {
      report('사이렌 소리를 켜려면 소리 켜기·시험을 눌러 주세요.');
      return;
    }
    try { if (kind) schedule(false); else if (!muted) tone(8); }
    catch (e) { report('사이렌을 재생하지 못했어요. 소리 켜기·시험을 다시 눌러 주세요.', e); }
  }
  function prepare(test) {
    var Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) { report('이 브라우저는 사이렌 소리를 지원하지 않아요.'); return; }
    var ticket = generation;
    try {
      if (!ctx || ctx.state === 'closed') { ctx = new Ctx(); wave = null; }
      var audio = ctx;
      // 반드시 클릭/키 입력의 동기 구간에서 resume한다(iOS·Chrome autoplay 정책).
      var ready = ctx.state === 'running' ? Promise.resolve() : ctx.resume();
      Promise.resolve(ready).then(function () {
        sync(); // 소리 단추(생산 화면)가 켬 상태를 바로 알게
        if (ctx !== audio || ticket !== generation) return;
        if (ctx.state !== 'running') { report('소리가 차단됐어요. 브라우저 소리 권한을 확인해 주세요.'); return; }
        if (muted) return;
        if (test === 'floor') ring('new', 0);
        else if (!test && active && kind) { if (!voice && !timers.length) schedule(true); }
        else if (test || (active && !voice)) tone(test ? 2 : 8, test);
        else if (!voice) report('사이렌 준비됨 · 탭 음소거와 기기 음량을 확인해 주세요.');
      }).catch(function (e) { report('소리를 켜지 못했어요. 브라우저 소리 권한을 확인해 주세요.', e); });
    } catch (e) { report('소리를 켜지 못했어요. 브라우저 소리 권한을 확인해 주세요.', e); }
  }
  function test() { muted = false; prepare(true); }
  // 생산 화면 소리 단추: 켜졌으면 끔, 아니면 켜기 + 시험 한 마디(새 일 소리). 끔은 화면을 새로 읽으면 풀린다(§3-3).
  function toggle() {
    if (state() === 'on') { muted = true; release(); report('소리를 껐어요 · 화면을 새로 읽으면 다시 켜져요.'); return; }
    muted = false;
    prepare('floor');
  }
  function prime(event) {
    var target = event.target && event.target.closest ? event.target : null;
    var button = target ? target.closest('[data-foms-urgent-sound-test]') : null;
    if (event.type === 'click' && button) { test(); return; }
    if (event.type === 'click' && target && target.closest('[data-foms-urgent-sound-toggle]')) { toggle(); return; }
    if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
    if (!ctx || ctx.state !== 'running') prepare(false);
  }
  window.FOMSUrgentSound = {
    start: start, stop: stop, test: test, sync: sync, toggle: toggle, state: state, plan: plan, kind: kindOf,
    play: function (name) { if (!voice) ring(kindOf(name), 0); } // 띠 소리처럼 한 번만 — 울리는 중이면 끊지 않는다
  };
  document.addEventListener('click', prime);
  document.addEventListener('keydown', prime);
  document.addEventListener('shown.bs.modal', sync);
  // 생산 알람 창은 배경 누름이 문서까지 안 올라온다(긴급 창이 막는다) — 창(window)에서 먼저 듣고 소리를 켠다(§3-3 의 4).
  // 긴급 호출 창(data-ntype 이 생산 알람이 아님)은 지금 그대로.
  window.addEventListener('click', function (event) {
    var t = event.target;
    var floor = t && t.closest ? t.closest('.foms-urgent-alert[data-ntype^="PRODUCTION_FLOOR_"]') : null;
    if (floor && !muted && !running()) prepare(false);
  }, true);
  window.addEventListener('pagehide', function () {
    stop();
    if (ctx) {
      var audio = ctx;
      ctx = null;
      wave = null;
      audio.close().catch(function (e) { console.warn('[urgent-sound] 오디오 종료 실패:', e); });
    }
  });
})();
