"""생산 현장 알람 화면(일꾼 ⓔ) — 소리 표 · 되풀이 · 소리 단추 · 띠 · 다시 받기를 Node 로 실제 실행한다.

설계서 docs/specs/2026-11-28-production-floor-alarm_SPEC.md §2 · §3 · §6-2(약속 5 · 6 · 7) · §6-4 · §7, 사장님 답 2차 3
(담당 변경은 받은 사람 · 원래 담당 둘 다 파랑 + 새 일 소리). 시각은 넣어 준다(Date.now · setTimeout 을 바꿔 끼운다 —
진짜로 기다리는 시험 없음). 서버 다시 받기 주소는 다른 일꾼이 만드는 중이라 약속 7 모양의 값을 넣어 준다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.support.drawing_customer_js_harness import run_js

ROOT = Path(__file__).resolve().parents[2]
SOUND = "static/js/foms/urgent-sound.js"
FLOOR = "static/js/foms/foms-floor-alarm.js"
ALERT = "static/js/foms/foms-urgent-alert.js"
ALERT_CSS = "static/css/components/foms-urgent-alert.css"
FLOOR_CSS = "static/css/contexts/production/floor-alarm.css"

#: 약속 5 알림 종류 이름 → (화면 색, 소리 이름). 답 2차 3: …_STOP_TAKEN 은 새 일과 같은 파랑 · 같은 소리.
TYPE_TABLE = {
    "PRODUCTION_FLOOR_NEW_GIVEN": ("blue", "new"),
    "PRODUCTION_FLOOR_STOP_TAKEN": ("blue", "new"),
    "PRODUCTION_FLOOR_STOP_DRAWING": ("red", "stop"),
    "PRODUCTION_FLOOR_STOP_REVISING": ("red", "stop"),
    "PRODUCTION_FLOOR_STOP_HOLD": ("red", "stop"),
    "PRODUCTION_FLOOR_STOP_CANCELLED": ("red", "stop"),
    "PRODUCTION_FLOOR_STOP_FACTORY": ("red", "stop"),
    **{f"PRODUCTION_FLOOR_NOTICE_{s}": ("band", "band") for s in (
        "START_CANCELLED", "DONE_CANCELLED", "DRAWING", "HOLD_RELEASED", "DATE", "DEFECT", "REWORK",
        "FIX_REJECTED", "FIX_APPLIED", "UNBLOCKED", "DUE_TODAY")},
}
#: 음성 대조군 — 생산 알람이 아닌 긴급(긴급 호출 등) · 빈 값은 지금 사이렌.
SIREN_TYPES = ["", "URGENT_CALL", "DRAWING_FIX_REQUEST", "PRODUCTION_ORDER_CHANGED", "PRODUCTION_FLOORX"]

SOUND_DRIVER = r"""
const stats = {contexts: 0, voices: []};
document.querySelectorAll = () => [];
const windowEvents = {};
window.addEventListener = (name, fn) => { windowEvents[name] = fn; };
const parameter = () => ({ points: [], setValueAtTime(v,t) { this.points.push([v,t]); },
  setValueCurveAtTime(values,t,duration) { this.curve = {n: values.length, t, duration}; },
  linearRampToValueAtTime(v,t) { this.points.push([v,t]); } });
class Audio {
  constructor() { stats.contexts++; this.state = 'suspended'; this.currentTime = 10; this.destination = {}; }
  resume() { this.state = 'running'; return Promise.resolve(); }
  close() { this.state = 'closed'; return Promise.resolve(); }
  createPeriodicWave(real, imag) { return {real: Array.from(real), imag: Array.from(imag)}; }
  createGain() { return {gain: parameter(), connect() {}, disconnect() {}}; }
  createOscillator() { const v = {type: '', frequency: parameter(), stops: [], connect() {},
    setPeriodicWave(w) { this.wave = w; },
    start(t) {this.started = t;}, stop(t) {this.stops.push(t === undefined ? 'now' : t);}, disconnect() {} };
    stats.voices.push(v); return v; }
}
window.AudioContext = Audio;
let clock = 5000000; Date.now = () => clock;
const timers = [];
globalThis.setTimeout = (fn, ms) => { timers.push({fn, ms, cleared: false}); return timers.length; };
globalThis.clearTimeout = (id) => { if (timers[id - 1]) timers[id - 1].cleared = true; };
const states = [];
document.addEventListener('foms:urgent-sound-state', (e) => states.push(e.detail));
function info(v) {
  if (!v) return null;
  const f = v.frequency.points.map(p => p[0]);
  return {type: v.type, freqs: Array.from(new Set(f)).sort((a, b) => a - b), notes: f.length,
    len: Math.round((v.stops[0] - v.started) * 1000) / 1000, stops: v.stops};
}
function last() { return info(stats.voices[stats.voices.length - 1]); }
async function unlock() { fire('click', makeEl({})); await flush(); }
function live() { return timers.filter(t => !t.cleared).map(t => t.ms); }
"""


def _sound(body: str) -> dict:
    return run_js([SOUND], SOUND_DRIVER + body)


def test_소리_표_알림_종류_앞머리로_고르고_그_밖은_사이렌() -> None:
    names = list(TYPE_TABLE) + SIREN_TYPES
    r = _sound("loadSources(); out({kinds: %s.map(n => window.FOMSUrgentSound.kind(n)), nul: window.FOMSUrgentSound.kind(null)});"
               % repr(names).replace("'", '"'))
    got = dict(zip(names, r["kinds"]))
    assert {n: got[n] for n in TYPE_TABLE} == {n: v[1] for n, v in TYPE_TABLE.items()}
    assert [got[n] for n in SIREN_TYPES] == [""] * len(SIREN_TYPES) and r["nul"] == ""


def test_되풀이_시간표_20초_뒤_1분마다_6초_5분부터_그침() -> None:
    r = _sound("loadSources(); const S = window.FOMSUrgentSound;"
               "out({p: [0, 10, 30, 63, 246, 300, 400].map(s => S.plan(s))});")
    assert r["p"] == [
        [[0, 20], [60, 6], [120, 6], [180, 6], [240, 6]],
        [[0, 10], [50, 6], [110, 6], [170, 6], [230, 6]],
        [[30, 6], [90, 6], [150, 6], [210, 6]],
        [[0, 3], [57, 6], [117, 6], [177, 6]],
        [], [], [],
    ]


def test_멈춤_소리_빠른_네_번_20초_울리고_타이머_넷_뒤_6초씩_확인하면_전부_멈춤() -> None:
    r = _sound(r"""
loadSources(); await unlock();
const S = window.FOMSUrgentSound;
S.start('PRODUCTION_FLOOR_STOP_HOLD');
const first = last(), delays = live();
timers[0].fn();
const again = last();
S.stop();
out({first, delays, again, after: live(), stopped: stats.voices[stats.voices.length - 1].stops});
""")
    # 1,760Hz 네모파 · 한 마디 1.5초(소리 0.12 · 쉼 0.08 네 번) → 20초 안 13마디(0 ~ 18초 시작), 6초 안 4마디
    assert r["first"]["type"] == "square" and r["first"]["freqs"] == [1760]
    assert r["first"]["notes"] == 13 * 4 and r["first"]["len"] == 18.72
    assert r["delays"] == [60000, 120000, 180000, 240000]
    assert r["again"]["notes"] == 4 * 4 and r["again"]["len"] == 5.22
    assert r["after"] == [] and r["stopped"][-1] == "now"


@pytest.mark.parametrize("ntype", ["PRODUCTION_FLOOR_NEW_GIVEN", "PRODUCTION_FLOOR_STOP_TAKEN"])
def test_새_일_소리_올라가는_두_음_두_번_담당_변경_둘_다(ntype) -> None:
    r = _sound("loadSources(); await unlock(); window.FOMSUrgentSound.start(%r); out({v: last(), delays: live()});" % ntype)
    # 880 → 1,320Hz 네모파, 한 마디 2.6초(두 번 = 1.19초 + 쉼) → 20초 안 8마디
    assert r["v"]["type"] == "square" and r["v"]["freqs"] == [880, 1320]
    assert r["v"]["notes"] == 8 * 4 and r["v"]["len"] == 19.39
    assert r["delays"] == [60000, 120000, 180000, 240000]


@pytest.mark.parametrize("ntype", SIREN_TYPES)
def test_생산_알람이_아닌_긴급은_지금_사이렌_그대로(ntype) -> None:
    r = _sound(r"""
loadSources(); await unlock();
window.FOMSUrgentSound.start(%r);
const v = stats.voices[stats.voices.length - 1];
out({wave: !!v.wave, curve: v.frequency.curve, stop: v.stops[0], delays: live()});
""" % ntype)
    # 새 경광등 사이렌(f0541a723, 운영과 같은 값) — 배음 파형 · 8초 음높이 곡선 · 되풀이 없음
    assert r["wave"] is True and r["curve"]["t"] == 10 and r["curve"]["duration"] == 8
    assert r["stop"] == 18 and r["delays"] == []


def test_띠_소리_낮은_음_한_번_되풀이_없음() -> None:
    r = _sound("loadSources(); await unlock(); window.FOMSUrgentSound.play('PRODUCTION_FLOOR_NOTICE_DEFECT'); out({v: last(), delays: live()});")
    assert r["v"] == {**r["v"], "type": "triangle", "freqs": [660], "notes": 1, "len": 0.5}
    assert r["delays"] == []


def test_늦게_켜면_생산_알람_창을_누를_때_바로_울리고_시간표를_잇는다_긴급_호출_창은_그대로() -> None:
    r = _sound(r"""
loadSources();
const S = window.FOMSUrgentSound;
const overlay = makeEl({}), inside = makeEl({});
inside._closest['.foms-urgent-alert[data-ntype^="PRODUCTION_FLOOR_"]'] = overlay;
S.start('');                       // 긴급 호출 창 — 창 누름으로는 지금처럼 안 켜진다(음성 대조군)
windowEvents.click({target: makeEl({})}); await flush();
const sirenContexts = stats.contexts;
S.start('PRODUCTION_FLOOR_STOP_DRAWING');
const lockedVoices = stats.voices.length, lockedTimers = live();
clock += 30000;                    // 30초 뒤(첫 20초가 지난 쉬는 틈)에 창을 누름
windowEvents.click({target: inside}); await flush();
out({sirenContexts, lockedVoices, lockedTimers, v: last(), delays: live(), state: S.state()});
""")
    assert r["sirenContexts"] == 0
    assert r["lockedVoices"] == 0 and r["lockedTimers"] == []
    assert r["v"]["freqs"] == [1760] and r["v"]["notes"] == 16  # 바로 6초
    assert r["delays"] == [30000, 90000, 150000, 210000]  # 1분 · 2분 · 3분 · 4분 자리 그대로
    assert r["state"] == "on"


def test_소리_단추_세_상태_켜기_시험_끔_끔이면_소리_0_새로_읽으면_풀림() -> None:
    r = _sound(r"""
loadSources();
const S = window.FOMSUrgentSound;
const btn = makeEl({}); btn._closest['[data-foms-urgent-sound-toggle]'] = btn;
const seq = [S.state()];
fire('click', btn); await flush();
const test = last(); seq.push(S.state());
fire('click', btn); await flush(); seq.push(S.state());
const before = stats.voices.length;
S.start('PRODUCTION_FLOOR_STOP_HOLD'); timers.forEach(t => t.fn()); S.start('');
const mutedVoices = stats.voices.length - before;
fire('click', btn); await flush(); seq.push(S.state());
delete window.FOMSUrgentSound; loadSources();       // 화면을 새로 읽음
out({seq, test, mutedVoices, reloaded: window.FOMSUrgentSound.state(), events: states.length});
""")
    assert r["seq"] == ["locked", "on", "off", "on"]
    assert r["test"]["freqs"] == [880, 1320] and r["test"]["notes"] == 4  # 시험 소리 = 새 일 한 마디
    assert r["mutedVoices"] == 0  # 끔이면 생산 알람 · 사이렌 모두 소리 0(창은 그대로 뜬다)
    assert r["reloaded"] == "locked" and r["events"] > 0


# ---------------------------------------------------------------------------
# foms-floor-alarm.js — 긴급 창 · 소리 모듈은 가짜로 두고 이 파일의 일만 본다
# ---------------------------------------------------------------------------
FLOOR_DRIVER = r"""
const shows = [], fronts = [], played = [], posts = [], later = [];
let soundState = 'locked';
window.FOMSUrgentAlert = { show(d) { shows.push(d); return true; }, openFromPush(id) { fronts.push(String(id)); } };
window.FOMSUrgentSound = { state: () => soundState, play: (n) => played.push(n) };
globalThis.setInterval = () => 0;
globalThis.setTimeout = (fn) => { later.push(fn); return later.length; };
globalThis.BroadcastChannel = class { constructor(n) { this.name = n; } postMessage(m) { posts.push([this.name, m]); } };
const header = makeEl({}), label = makeEl({}), icon = makeEl({});
const soundBtn = makeEl({cls: ['is-locked']});
soundBtn._closest['header'] = header;
soundBtn._sel['[data-foms-floor-sound-label]'] = label;
soundBtn._sel['i'] = icon;
const PROD = typeof window.__noProd === 'undefined';
if (PROD) globalSel['[data-foms-floor-sound]'] = soundBtn;
document.querySelectorAll = (s) => (PROD && s === '[data-foms-floor-sound]') ? [soundBtn] : [];
document.visibilityState = 'visible';
window.location.pathname = '/erp/production/home'; window.location.search = '';
const sock = {}; window.__appSocket = { on(name, fn) { sock[name] = fn; } };
route('/erp/api/notifications/', () => Resp(200, {success: true}));
function emit(type, detail) { document.dispatchEvent({type, detail}); }
function band() { return header.children[0]; }
function bandView() { const b = band(); return b ? {hidden: !!b.hidden, text: b.goBtn.textContent, count: b.count.textContent} : null; }
function U(id, type, order, extra) { return Object.assign({notification_id: id, notification_type: type, order_id: order,
  title: 't' + id, message: 'm' + id, created_by_name: '박반장'}, extra || {}); }
function N(id, order, title, message) { return {notification_id: id, notification_type: 'PRODUCTION_FLOOR_NOTICE_DEFECT',
  order_id: order, title: title || ('띠' + id), message: message || ('본문' + id)}; }
function writes() { return calls.filter(c => c.method === 'POST').map(c => c.url); }
"""

PENDING = "/api/production/alarms/pending"


def _floor(body: str, pre: str = "") -> dict:
    return run_js([FLOOR], pre + FLOOR_DRIVER + body)


def test_다시_받기_약속_7_긴급은_멈춤_먼저_띠는_줄_서기_1_3() -> None:
    r = _floor(r"""
route('/api/production/alarms/pending', () => Resp(200, {success: true, error: null, data: {
  urgent: [U(11, 'PRODUCTION_FLOOR_NEW_GIVEN', 5), U(12, 'PRODUCTION_FLOOR_STOP_HOLD', 6), U(13, 'URGENT_CALL', 7)],
  notices: [N(21, 5, '박엣지가 불량을 알렸어요 — 파손', '정하늘 · 11/30 시공'), N(22, 6), N(23, 7)]}}));
loadSources(); await flush();
out({asked: calls.filter(c => c.url === '/api/production/alarms/pending').length, shows: shows.map(s => [s.notification_id, s.urgent]),
  band: bandView(), played});
""")
    assert r["asked"] == 1
    assert r["shows"] == [[12, True], [11, True]]  # 멈춤 먼저 · 생산 알람이 아닌 13 은 안 넘긴다(공용 창 몫)
    assert r["band"] == {"hidden": False, "text": "박엣지가 불량을 알렸어요 — 파손 · 정하늘 · 11/30 시공", "count": "1/3"}
    assert r["played"] == []  # 다시 받기로 온 띠는 소리 없이(새로 읽은 화면은 어차피 소리가 잠겨 있다)


@pytest.mark.parametrize("answer", ["404", "500", "throw", "bad"])
def test_다시_받기_주소가_없거나_실패하면_조용히(answer) -> None:
    r = _floor(r"""
const a = %r;
if (a === '404') route('/api/production/alarms/pending', () => Resp(404, {success: false}));
if (a === '500') route('/api/production/alarms/pending', () => Resp(500, {success: false, error: 'x'}));
if (a === 'bad') route('/api/production/alarms/pending', () => Resp(200, {success: true, data: {urgent: 'no'}}));
loadSources(); await flush();
out({shows: shows.length, band: bandView()});
""" % answer)
    assert r["shows"] == 0 and r["band"] is None


def test_실시간_멈춤은_새_일_창보다_앞으로_긴급_호출_창은_안_건드림() -> None:
    r = _floor(r"""
loadSources(); await flush();
sock.erp_notification(U(31, 'PRODUCTION_FLOOR_NEW_GIVEN', 5, {urgent: true}));
emit('foms:urgent-shown', shows[0]);
sock.erp_notification(U(32, 'PRODUCTION_FLOOR_STOP_DRAWING', 5, {urgent: true}));
const first = fronts.slice();
emit('foms:urgent-shown', {notification_id: 40, notification_type: 'URGENT_CALL', urgent: true});
sock.erp_notification(U(33, 'PRODUCTION_FLOOR_STOP_CANCELLED', 6, {urgent: true}));
emit('foms:urgent-shown', shows[1]);
sock.erp_notification(U(34, 'PRODUCTION_FLOOR_STOP_FACTORY', 6, {urgent: true}));
out({shows: shows.map(s => s.notification_id), first, fronts});
""")
    assert r["shows"] == [31, 32, 33, 34]
    assert r["first"] == ["32"]  # 새 일 창 위로 멈춤
    assert r["fronts"] == ["32"]  # 긴급 호출 창 · 이미 멈춤 창이면 앞으로 안 올린다


def test_합친_알람은_같은_번호로_글만_갈아_끼운다() -> None:
    r = _floor(r"""
const t = makeEl({id: 'foms-urgent-alert-title'}), m = makeEl({id: 'foms-urgent-alert-message'});
loadSources(); await flush();
const a = U(50, 'PRODUCTION_FLOOR_NEW_GIVEN', 5, {urgent: true, title: '박반장이 재단 담당을 당신으로 변경했어요'});
sock.erp_notification(a); emit('foms:urgent-shown', a);
sock.erp_notification(U(50, 'PRODUCTION_FLOOR_NEW_GIVEN', 5, {urgent: true,
  title: '박반장이 재단 담당을 당신으로 변경했어요 — 도면 3장', message: '11/30 시공 · 정하늘 · 도면 1번 · 2번 · 4번'}));
out({shows: shows.length, title: t.textContent, message: m.textContent, stored: a.title});
""")
    assert r["shows"] == 1
    assert r["title"] == r["stored"] == "박반장이 재단 담당을 당신으로 변경했어요 — 도면 3장"
    assert r["message"] == "11/30 시공 · 정하늘 · 도면 1번 · 2번 · 4번"


def test_실시간_띠_소리_한_번_kind_notice_칸은_안_읽고_서버가_닫으면_치운다() -> None:
    r = _floor(r"""
loadSources(); await flush();
sock.erp_notification({urgent: false, notice: true, kind: 'erp_notification', notification_id: 60, title: '쪽지', notification_type: 'X'});
const ignored = bandView();
sock.erp_notification(Object.assign(N(61, 5, '보류가 풀렸어요 — 다시 작업하세요', '정하늘'), {urgent: false, floor_notice: true}));
sock.erp_notification(Object.assign(N(62, 6), {urgent: false, floor_notice: true}));
const two = bandView();
sock.erp_notification({urgent: false, floor_closed: true, notification_ids: [61, 70]});
out({ignored, two, after: bandView(), played, posts});
""")
    assert r["ignored"] is None  # notice · kind 칸만 있는 값은 띠가 아니다
    assert r["two"] == {"hidden": False, "text": "보류가 풀렸어요 — 다시 작업하세요 · 정하늘", "count": "1/2"}
    assert r["played"] == ["band", "band"]
    assert r["after"] == {"hidden": False, "text": "띠62 · 본문62", "count": ""}
    assert r["posts"] == [["foms-urgent", {"type": "ack", "notification_id": "61"}],
                          ["foms-urgent", {"type": "ack", "notification_id": "70"}]]


def test_띠_확인은_확인_읽음_기록_뒤_다음_줄_마지막이면_그_주문으로() -> None:
    r = _floor(r"""
route('/api/production/alarms/pending', () => Resp(200, {success: true, data: {urgent: [], notices: [N(21, 5), N(22, 6), N(23, 7)]}}));
loadSources(); await flush();
fire('click', band().okBtn); await flush();
const s1 = [bandView(), window.location.href];
fire('click', band().okBtn); await flush();
const s2 = [bandView(), window.location.href];
fire('click', band().okBtn); await flush();
out({s1, s2, end: [bandView().hidden, window.location.href], writes: writes()});
""")
    assert r["s1"] == [{"hidden": False, "text": "띠22 · 본문22", "count": "1/2"}, ""]
    assert r["s2"] == [{"hidden": False, "text": "띠23 · 본문23", "count": ""}, ""]
    assert r["end"] == [True, "/erp/production/home?order=7"]
    assert r["writes"] == [f"/erp/api/notifications/{n}/{v}" for n in (21, 22, 23) for v in ("ack", "read")]


def test_띠를_누르면_바로_그_주문으로_이미_그_화면이면_안_감() -> None:
    r = _floor(r"""
route('/api/production/alarms/pending', () => Resp(200, {success: true, data: {urgent: [], notices: [N(21, 5), N(22, 6)]}}));
loadSources(); await flush();
window.location.search = '?order=5';
fire('click', band().goBtn); await flush();
const stay = [window.location.href, bandView()];
fire('click', band().goBtn); await flush();
out({stay, go: window.location.href, writes: writes()});
""")
    assert r["stay"] == ["", {"hidden": False, "text": "띠22 · 본문22", "count": ""}]
    assert r["go"] == "/erp/production/home?order=6"
    assert r["writes"] == ["/erp/api/notifications/21/ack", "/erp/api/notifications/21/read",
                           "/erp/api/notifications/22/ack", "/erp/api/notifications/22/read"]


def test_띠_확인_실패면_줄이_남는다() -> None:
    r = _floor(r"""
routes.length = 0;
route('/erp/api/notifications/', () => Resp(500, {success: false, message: 'x'}));
route('/api/production/alarms/pending', () => Resp(200, {success: true, data: {urgent: [], notices: [N(21, 5)]}}));
loadSources(); await flush();
fire('click', band().okBtn); await flush();
out({band: bandView(), href: window.location.href});
""")
    assert r["band"] == {"hidden": False, "text": "띠21 · 본문21", "count": ""} and r["href"] == ""


def test_긴급_확인_뒤_그_주문으로_다음_건이_떠_있으면_다_누른_뒤() -> None:
    r = _floor(r"""
loadSources(); await flush();
const overlay = makeEl({id: 'foms-urgent-alert'});
emit('foms:urgent-acked', U(1, 'PRODUCTION_FLOOR_STOP_HOLD', 5));
later.splice(0).forEach(f => f());
const waiting = window.location.href;
delete byId['foms-urgent-alert'];
emit('foms:urgent-acked', U(2, 'PRODUCTION_FLOOR_NEW_GIVEN', 6));
later.splice(0).forEach(f => f());
const went = window.location.href;
window.location.href = ''; window.location.search = '?order=8';
emit('foms:urgent-acked', {notification_id: 3, notification_type: 'URGENT_CALL', order_id: 9});
emit('foms:urgent-acked', U(4, 'PRODUCTION_FLOOR_STOP_TAKEN', 8));
const asksBefore = calls.filter(c => c.url === '/api/production/alarms/pending').length;
later.splice(0).forEach(f => f()); await flush();
out({waiting, went, here: window.location.href,
  asked: calls.filter(c => c.url === '/api/production/alarms/pending').length - asksBefore});
""")
    assert r["waiting"] == ""
    assert r["went"] == "/erp/production/home?order=6"
    assert r["here"] == ""  # 이미 그 주문 화면 — 창만 닫히고, 줄이 비었으니 다시 받기를 한 번 묻는다
    assert r["asked"] == 1


def test_소리_단추_글_세_상태_회색_없음() -> None:
    r = _floor(r"""
loadSources(); await flush();
function view() { return {label: label.textContent, on: soundBtn.classList.contains('is-on'),
  locked: soundBtn.classList.contains('is-locked'), off: soundBtn.classList.contains('is-off'),
  pressed: soundBtn.getAttribute('aria-pressed'), icon: icon.className}; }
const a = view();
soundState = 'on'; emit('foms:urgent-sound-state', 'on'); const b = view();
soundState = 'off'; emit('foms:urgent-sound-state', 'off'); const c = view();
out({a, b, c});
""")
    assert r["a"] == {"label": "소리 켜기", "on": False, "locked": True, "off": False, "pressed": "false", "icon": "fas fa-volume-up"}
    assert r["b"] == {"label": "소리 켬", "on": True, "locked": False, "off": False, "pressed": "true", "icon": "fas fa-volume-up"}
    assert r["c"] == {"label": "소리 꺼짐", "on": False, "locked": False, "off": True, "pressed": "false", "icon": "fas fa-volume-mute"}


@pytest.mark.parametrize("case", ["coarse", "reject", "fine", "not-production"])
def test_화면_안_꺼지게_생산_화면_터치_기기만_실패는_조용히(case) -> None:
    pre = "window.__noProd = true;\n" if case == "not-production" else ""
    r = _floor(r"""
const c = %r; let asked = 0;
window.matchMedia = (q) => ({matches: q === '(pointer: coarse)' && c !== 'fine'});
navigator.wakeLock = {request: (t) => { asked += 1; return c === 'reject' ? Promise.reject(new Error('battery'))
  : Promise.resolve({released: false, addEventListener() {}, release() { return Promise.resolve(); }}); }};
loadSources(); await flush();
emit('visibilitychange'); await flush();
out({asked, pending: calls.filter(c => c.url === '/api/production/alarms/pending').length});
""" % case, pre)
    want = {"coarse": 1, "reject": 2, "fine": 0, "not-production": 0}[case]
    assert r["asked"] == want  # 거절되면 다시 보일 때 한 번 더 묻는다(조용히)
    assert r["pending"] == (0 if case == "not-production" else 1)  # 생산 화면이 아니면 다시 받기도 안 부른다


# ---------------------------------------------------------------------------
# 원문 단언 — 긴급 창 고침 넷 · 색 표 · 줄 수
# ---------------------------------------------------------------------------
def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_긴급_창_고침은_네_줄_안_공개_이름_그대로() -> None:
    js = _read(ALERT)
    assert len(js.splitlines()) <= 298  # 294 + 4 줄까지(설계서 §6-4)
    assert "window.FOMSUrgentSound.start(item.notification_type)" in js
    assert "overlay.setAttribute('data-ntype'" in js
    assert "new CustomEvent('foms:urgent-shown', { detail: item })" in js
    assert "new CustomEvent('foms:urgent-acked'" in js
    assert "show: show, handle: handle, bindSocket: bindSocket, resync: resync, openFromPush: openFromPush" in js


def test_색_표가_소리_표와_같다_답_2차_담당_변경_둘_다_파랑() -> None:
    css = _read(ALERT_CSS)
    block = css[css.index("/* ── 생산 현장 알람"):]
    red = re.search(r'\.foms-urgent-alert\[data-ntype\^="PRODUCTION_FLOOR_"\] \{[^}]*background-color: (#\w+)', block).group(1)
    blue = re.search(r'\.foms-urgent-alert\[data-ntype\^="PRODUCTION_FLOOR_NEW"\],\n'
                     r'\.foms-urgent-alert\[data-ntype="PRODUCTION_FLOOR_STOP_TAKEN"\] \{\s*background-color: (#\w+)', block).group(1)
    assert (red, blue) == ("#b81f1f", "#1546b0")  # 시안 값
    for name, (color, sound) in TYPE_TABLE.items():
        if color == "band":
            continue
        css_blue = name.startswith("PRODUCTION_FLOOR_NEW") or name == "PRODUCTION_FLOOR_STOP_TAKEN"
        assert ("blue" if css_blue else "red") == color and (sound == "new") == css_blue, name
    btn = block[block.index('.foms-urgent-alert__btn {'):]
    btn = btn[:btn.index("}")]
    for rule in ("min-width: 320px", "min-height: 96px", "font-size: calc(28px * var(--foms-fs, 1))"):
        assert rule in btn
    assert ".foms-urgent-alert__sound," in block and ".foms-urgent-alert__icon," in block
    # 지금 긴급 창 규칙(빨간 반투명 · 단추 56px)은 그대로
    head = css[:css.index("/* ── 생산 현장 알람")]
    assert "background-color: rgba(220, 53, 69, 0.95);" in head and "min-height: 56px;" in head


def test_새_화면_파일_규칙_글자_배율_회색_없음_인라인_스타일_없음() -> None:
    css = _read(FLOOR_CSS)
    code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert not re.search(r"font-size:\s*\d+px", code)
    assert len(re.findall(r"font-size: calc\(\d+px \* var\(--foms-fs, 1\)\)", code)) >= 4
    for gray in ("#808080", "#888", "#999", "#aaa", "#ccc", "gray", "grey"):
        assert gray not in code.lower(), gray
    assert ".foms-floor-sound.is-on" in code and ".foms-floor-sound.is-locked" in code and ".foms-floor-sound.is-off" in code
    assert "min-height: 64px" in code
    for rel in (FLOOR, SOUND):
        js = _read(rel)
        assert ".style." not in js and "innerHTML" not in js and "jQuery" not in js and "$(" not in js
        assert len(js.splitlines()) < 300
    assert len(_read(FLOOR).splitlines()) <= 250
    assert "'카드'" not in _read(FLOOR) and "카드" not in _read("templates/production/partials/floor_alarm.html")
