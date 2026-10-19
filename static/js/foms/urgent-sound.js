/** 긴급 사이렌: 사용자 입력에서 오디오 준비, 컨텍스트 재사용, 8초 상한·확인 시 정지. */
(function () {
  'use strict';
  if (window.FOMSUrgentSound) return;
  var ctx = null, wave = null, voice = null, active = false, generation = 0;
  var status = '소리 켜기·시험을 눌러 사이렌과 기기 음량을 확인해 주세요.';

  function sync() {
    document.querySelectorAll('[data-foms-urgent-sound-status]').forEach(function (el) { el.textContent = status; });
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
  function stop() {
    active = false;
    generation += 1;
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
  function start() {
    stop();
    active = true;
    if (!ctx || ctx.state !== 'running') {
      report('사이렌 소리를 켜려면 소리 켜기·시험을 눌러 주세요.');
      return;
    }
    try { tone(8); }
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
        if (ctx !== audio || ticket !== generation) return;
        if (ctx.state !== 'running') { report('소리가 차단됐어요. 브라우저 소리 권한을 확인해 주세요.'); return; }
        if (test || (active && !voice)) tone(test ? 2 : 8, test);
        else if (!voice) report('사이렌 준비됨 · 탭 음소거와 기기 음량을 확인해 주세요.');
      }).catch(function (e) { report('소리를 켜지 못했어요. 브라우저 소리 권한을 확인해 주세요.', e); });
    } catch (e) { report('소리를 켜지 못했어요. 브라우저 소리 권한을 확인해 주세요.', e); }
  }
  function test() { prepare(true); }
  function prime(event) {
    var button = event.target && event.target.closest ? event.target.closest('[data-foms-urgent-sound-test]') : null;
    if (event.type === 'click' && button) { test(); return; }
    if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
    if (!ctx || ctx.state !== 'running') prepare(false);
  }
  window.FOMSUrgentSound = { start: start, stop: stop, test: test, sync: sync };
  document.addEventListener('click', prime);
  document.addEventListener('keydown', prime);
  document.addEventListener('shown.bs.modal', sync);
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
