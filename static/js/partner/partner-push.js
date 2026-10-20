/**
 * PARTNER-FOMS 6: 협력사 화면 "알림 받기" — 이 기기에서 웹 푸시를 켜고 끈다.
 *
 * 서버 계약(우리 푸시 주소를 그대로 쓴다 — 협력사 문지기 허용, 자기 것만 다룸):
 *   GET    /erp/api/notifications/push/vapid-public-key → {success, data:{public_key}}
 *   POST   /erp/api/notifications/push/subscribe {endpoint, keys, platform, browser, permission_state}
 *   DELETE /erp/api/notifications/push/subscribe {endpoint}
 *   POST   /erp/api/notifications/push/test → 자기에게 시험 알림
 * 쓰기는 X-FOMS-Notification-Write: 1 헤더가 필요하다(CSRF 는 csrf_bootstrap 이 붙인다).
 * 아이폰은 홈 화면에 추가한 앱에서만 켤 수 있다(iOS 16.4+).
 * 설계서: docs/specs/2026-10-20-partner-notifications_SPEC.md §5-5
 */
(function () {
  'use strict';

  var BASE = '/erp/api/notifications/push';
  var ua = navigator.userAgent || '';
  var IS_IOS = /iphone|ipad|ipod/i.test(ua);

  function standalone() {
    return (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || window.navigator.standalone === true;
  }

  function supported() {
    return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  }

  function write(path, method, body) {
    return fetch(BASE + path, {
      method: method,
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-FOMS-Notification-Write': '1' },
      credentials: 'same-origin',
      body: body ? JSON.stringify(body) : null,
    }).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (!res.ok || !data || !data.success) throw new Error((data && data.error) || ('HTTP ' + res.status));
        return data.data;
      });
    });
  }

  function vapidKey() {
    return fetch(BASE + '/vapid-public-key', { credentials: 'same-origin' })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) { return data && data.success && data.data ? data.data.public_key : null; });
  }

  function toBytes(base64) {
    var padded = (base64 + '===='.slice((base64.length % 4) || 4)).replace(/-/g, '+').replace(/_/g, '/');
    var raw = window.atob(padded);
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
    return out;
  }

  function registration() {
    return navigator.serviceWorker.register('/static/sw.js', { scope: '/' });
  }

  function currentSubscription() {
    if (!supported()) return Promise.resolve(null);
    return navigator.serviceWorker.getRegistration('/').then(function (reg) {
      return reg && reg.pushManager ? reg.pushManager.getSubscription() : null;
    });
  }

  function Push(root) {
    this.root = root;
    this.panel = root.querySelector('[data-pp-push-panel]');
    this.msg = root.querySelector('[data-pp-push-msg]');
    this.steps = root.querySelector('[data-pp-push-steps]');
  }

  Push.prototype.show = function (selector, on) {
    var el = this.root.querySelector(selector);
    if (el) el.hidden = !on;
  };

  Push.prototype.say = function (text, steps) {
    this.msg.textContent = text;
    this.steps.innerHTML = '';
    (steps || []).forEach(function (line) {
      var li = document.createElement('li');
      li.textContent = line;
      this.steps.appendChild(li);
    }, this);
    this.steps.hidden = !(steps && steps.length);
  };

  Push.prototype.render = function (on) {
    this.root.querySelector('[data-pp-push-label]').textContent = on ? '알림 켜짐' : '알림 받기';
    this.root.classList.toggle('pp-push--on', !!on);
    this.show('[data-pp-push-enable]', !on && supported());
    this.show('[data-pp-push-test]', !!on);
    this.show('[data-pp-push-disable]', !!on);
    if (on) return this.say('이 기기로 도면 확인 차례 · 시공일 · AS 방문 · 시공 끝 알림이 옵니다.');
    if (!supported() && IS_IOS && !standalone()) {
      return this.say('아이폰은 홈 화면에 추가한 뒤에 알림을 켤 수 있습니다.', [
        '사파리 아래쪽 공유 버튼(네모에 위쪽 화살표)을 누르세요.',
        "목록에서 '홈 화면에 추가'를 누르세요.",
        "홈 화면에 생긴 '협력사 주문'으로 다시 열고 '알림 받기'를 누르세요.",
      ]);
    }
    if (!supported()) return this.say('이 브라우저는 알림을 받을 수 없습니다. 크롬이나 사파리(홈 화면 앱)로 열어 주세요.');
    if (window.Notification.permission === 'denied') {
      return this.say('이 기기에서 알림이 막혀 있습니다. 브라우저 설정 → 사이트 설정 → 알림에서 이 사이트를 허용한 뒤 다시 눌러 주세요.');
    }
    this.say('이 기기에서 알림을 켜면 협력사 주문에 할 일이 생길 때 바로 알려 드립니다.');
  };

  Push.prototype.enable = function () {
    var self = this;
    self.say('알림을 켜는 중…');
    Promise.resolve(window.Notification.requestPermission()).then(function (permission) {
      if (permission !== 'granted') throw new Error('denied');
      return Promise.all([vapidKey(), registration()]);
    }).then(function (both) {
      if (!both[0]) throw new Error('no key');
      return both[1].pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: toBytes(both[0]) });
    }).then(function (sub) {
      var json = sub.toJSON();
      return write('/subscribe', 'POST', {
        endpoint: json.endpoint, keys: json.keys || {}, platform: IS_IOS ? 'ios' : (/android/i.test(ua) ? 'android' : 'desktop'),
        browser: 'partner', permission_state: 'granted',
      });
    }).then(function () { self.render(true); }).catch(function (err) {
      self.render(false);
      if (err && err.message !== 'denied') self.say('알림을 켜지 못했습니다. 잠시 뒤 다시 눌러 주세요.');
    });
  };

  Push.prototype.disable = function () {
    var self = this;
    currentSubscription().then(function (sub) {
      if (!sub) return null;
      return write('/subscribe', 'DELETE', { endpoint: sub.endpoint }).catch(function () { return null; })
        .then(function () { return sub.unsubscribe(); });
    }).then(function () { self.render(false); });
  };

  Push.prototype.test = function () {
    var self = this;
    write('/test', 'POST', {}).then(function (data) {
      self.say(data && data.sent ? '시험 알림을 보냈습니다. 잠시 뒤 이 기기에 알림이 뜨는지 봐 주세요.' : '시험 알림을 보내지 못했습니다. 알림을 껐다가 다시 켜 주세요.');
    }).catch(function () { self.say('시험 알림을 보내지 못했습니다. 잠시 뒤 다시 눌러 주세요.'); });
  };

  Push.prototype.bind = function () {
    var self = this;
    this.root.addEventListener('click', function (ev) {
      if (ev.target.closest('[data-pp-push-toggle]')) {
        self.panel.hidden = !self.panel.hidden;
        ev.target.closest('[data-pp-push-toggle]').setAttribute('aria-expanded', String(!self.panel.hidden));
      }
      if (ev.target.closest('[data-pp-push-enable]')) self.enable();
      if (ev.target.closest('[data-pp-push-disable]')) self.disable();
      if (ev.target.closest('[data-pp-push-test]')) self.test();
    });
    currentSubscription().then(function (sub) {
      self.render(!!sub && window.Notification.permission === 'granted');
    }).catch(function () { self.render(false); });
  };

  document.addEventListener('DOMContentLoaded', function () {
    // PC 머리줄과 휴대폰 위 줄에 하나씩 있다(4-1) — 칸마다 따로 묶는다.
    Array.prototype.forEach.call(document.querySelectorAll('[data-pp-push]'), function (root) {
      new Push(root).bind();
    });
  });
})();
