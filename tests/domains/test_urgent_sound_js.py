"""사이렌 오디오 실제 JS 실행: 제스처·재사용·시간 제한·정리·차단/실패 표시."""
from tests.support.drawing_customer_js_harness import run_js

JS = 'static/js/foms/urgent-sound.js'
DRIVER = r"""
const stats = {contexts: 0, resumes: 0, voices: [], closed: 0};
const status = makeEl({});
document.querySelectorAll = () => [status];
const windowEvents = {};
window.addEventListener = (name, fn) => { windowEvents[name] = fn; };
const parameter = () => ({ points: [], setValueAtTime(v,t) { this.points.push([v,t]); },
  linearRampToValueAtTime(v,t) { this.points.push([v,t]); } });
class Audio {
  constructor() { stats.contexts++; this.state = 'suspended'; this.currentTime = 10; this.destination = {}; }
  resume() { stats.resumes++; this.state = 'running'; return Promise.resolve(); }
  close() { stats.closed++; this.state = 'closed'; return Promise.resolve(); }
  createGain() { return {gain: parameter(), connect() {}, disconnect() {this.disconnected = true;} }; }
  createOscillator() { const voice = {frequency: parameter(), stops: [], connect() {},
    start(t) {this.started = t;}, stop(t) {this.stops.push(t === undefined ? 'now' : t);},
    disconnect() {this.disconnected = true;} }; stats.voices.push(voice); return voice; }
}
window.AudioContext = Audio;
"""


def test_waits_for_gesture_reuses_context_limits_duration_and_cleans_up():
    r = run_js([JS], DRIVER + r"""
loadSources(); loadSources();
window.FOMSUrgentSound.start();
const before = stats.contexts;
fire('click', makeEl({})); await flush();
const emergency = stats.voices[0];
window.FOMSUrgentSound.stop();
const stopped = emergency.stops.slice(), disconnected = emergency.disconnected;
window.FOMSUrgentSound.start();
window.FOMSUrgentSound.test(); await flush();
const test = stats.voices[2];
test.onended();
windowEvents.pagehide(); await flush();
out({before, contexts: stats.contexts, resumes: stats.resumes, stopped, disconnected,
  firstRamp: emergency.frequency.points.slice(0,3), lastStop: test.stops[0],
  closed: stats.closed, handlers: docListeners.click.length});
""")
    assert r['before'] == 0
    assert r['contexts'] == 1 and r['resumes'] == 1 and r['handlers'] == 1
    assert r['stopped'] == [18, 'now'] and r['disconnected']
    assert r['firstRamp'] == [[600, 10], [1200, 10.5], [600, 11]]
    assert r['lastStop'] == 12  # 시험은 2초, 긴급은 8초
    assert r['closed'] == 1


def test_ack_while_resume_pending_does_not_play_stale_alert():
    r = run_js([JS], DRIVER + r"""
let finish;
Audio.prototype.resume = function () { this.state = 'running'; return new Promise(r => {finish = r;}); };
loadSources();
window.FOMSUrgentSound.start(); fire('click', makeEl({}));
window.FOMSUrgentSound.stop(); finish(); await flush();
out({voices: stats.voices.length});
""")
    assert r['voices'] == 0


def test_blocked_audio_and_retry_are_visible():
    r = run_js([JS], DRIVER + r"""
Audio.prototype.resume = function () { return Promise.reject(new Error('blocked')); };
loadSources(); window.FOMSUrgentSound.test(); await flush();
const blocked = status.textContent;
Audio.prototype.resume = function () { this.state = 'running'; return Promise.resolve(); };
window.FOMSUrgentSound.test(); await flush();
out({blocked, voices: stats.voices.length, status: status.textContent});
""")
    assert '켜지 못했어요' in r['blocked']
    assert r['voices'] == 1 and '재생 중' in r['status']


def test_unsupported_browser_shows_status_without_throwing():
    r = run_js([JS], DRIVER + r"""
delete window.AudioContext;
loadSources(); window.FOMSUrgentSound.test(); out({status: status.textContent});
""")
    assert '지원하지 않아요' in r['status']
