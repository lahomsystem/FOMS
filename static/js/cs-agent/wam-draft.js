/**
 * 채널톡 안 작은 창(WAM) — AI 초안 [보내기] · [수정하기](설계서 17.2.2 · 사장님 11-05).
 *
 * 단계 S1(시험 장치): 채널톡 다리(window.ChannelIOWam)가 있는지, 받은 칸 이름이 무엇인지, 서명 함수(cs.draft.ping)를
 * 부를 수 있는지만 보여 준다. 값은 차례 번호 말고는 꼴(있음 · 없음)만 — 상담원 번호 · 상담 번호는 화면에 찍지 않는다.
 * 글은 textContent 로만 넣는다.
 */
(function () {
  'use strict';

  var root = document.getElementById('cs-wam');
  var status = document.getElementById('cs-wam-status');
  var log = document.getElementById('cs-wam-log');
  if (!root || !status || !log) return;

  var KEYS = ['appId', 'channelId', 'managerId', 'chatId', 'chatType', 'rootMessageId', 'wamArgs', 'turn', 'mode',
    'appearance', 'locale'];

  function line(text) {
    var p = document.createElement('p');
    p.className = 'cs-wam__line';
    p.textContent = text;
    log.appendChild(p);
  }

  // S1 시험 신호 — 단계 코드만(값 · 글 없음) 같은 출처로 남긴다. 교차 출처 창이라 화면을 직접 못 읽어서 둔다(S2 에서 뺀다).
  function beacon(code) {
    try { fetch('/channel/wam/cs-draft/beacon?c=' + encodeURIComponent(String(code).slice(0, 160)), { credentials: 'omit' }); } catch (e) { /* 무시 */ }
  }

  function read(wam, key) {
    try { return wam.getWamData(key); } catch (e) { return undefined; }
  }

  function turnOf(wam) {
    var args = read(wam, 'wamArgs');
    var value = args && typeof args === 'object' ? args.turn : read(wam, 'turn');
    var number = parseInt(value, 10);
    return number > 0 ? number : null;
  }

  var wam = window.ChannelIOWam;
  // 채널톡 작은 창에는 닫기 단추가 없다 — 화면이 직접 단다(ChannelIOWam.close, 사장님 11-05 "창을 삭제하는 버튼이 없네").
  var closeButton = document.getElementById('cs-wam-close');
  if (closeButton) {
    closeButton.addEventListener('click', function () {
      try { if (wam && typeof wam.close === 'function') wam.close(); } catch (e) { /* 닫기를 못 해도 화면은 그대로 */ }
    });
  }
  if (!wam || typeof wam.callFunction !== 'function') {
    beacon('nobridge:' + (wam ? Object.keys(wam).join('.') : 'none'));
    status.textContent = '채널톡 밖에서 열었어요. 채널톡 메모의 단추로 열어 주세요.';
    return;
  }
  try { wam.setSize({ height: 260 }); } catch (e) { /* 크기 바꾸기를 못 해도 계속 */ }

  line('받은 칸: ' + KEYS.map(function (key) {
    var value = read(wam, key);
    return key + (value === undefined || value === null || value === '' ? ' 없음' : ' 있음');
  }).join(' · '));
  beacon('keys:' + KEYS.filter(function (key) {
    var value = read(wam, key);
    return !(value === undefined || value === null || value === '');
  }).join(','));
  var turn = turnOf(wam);
  line('차례 번호: ' + (turn || '없음'));

  var appId = root.getAttribute('data-app-id') || read(wam, 'appId');
  if (!appId) {
    beacon('noapp');
    status.textContent = '앱 번호가 없어 함수를 부를 수 없어요.';
    return;
  }
  status.textContent = '서명 함수를 부르는 중이에요.';
  Promise.resolve(wam.callFunction({ appId: String(appId), name: 'cs.draft.ping', params: { turn: turn } }))
    .then(function (res) {
      var result = res && (res.result || res);
      beacon(result && result.ok ? 'ping:ok' : 'ping:shape:' + Object.keys(res || {}).join('.'));
      status.textContent = result && result.ok ? '연결됐어요.' : '함수가 답했지만 연결 확인이 안 됐어요.';
      line('함수 답: ' + (result && result.ok ? 'ok · 차례 ' + (result.turn || '없음') : '오류'));
    }, function (err) {
      beacon('ping:err:' + String((err && (err.code || err.type || err.message)) || err).replace(/[^A-Za-z0-9_.:-]/g, '_').slice(0, 80));
      status.textContent = '함수를 부르지 못했어요.';
      line('오류: ' + String((err && err.message) || err).slice(0, 120));
    });
}());
