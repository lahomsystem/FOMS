/**
 * Mobile Web Push CTA — Phase 3B (device push subscribe client).
 *
 * 알림 시트(erp_mobile_notification_panel.html) 하단 고정 영역(data-foms-push-cta)에
 * 기기 알림(Web Push) 켜기/끄기 CTA 를 렌더한다. 상태 판단 SSOT 는 서버의
 * GET /erp/api/notifications/mobile-state (flag off 여도 200) 다.
 *
 * - 켜기 flow 는 반드시 클릭 user gesture 안에서 Notification.requestPermission →
 *   VAPID key 확보 → SW 등록(window.fomsRegisterServiceWorker) → pushManager.subscribe →
 *   subscribe POST 순서로 진행한다(각 단계 실패는 사용자 가시 toast).
 * - 끄기 flow 는 로컬 subscription.unsubscribe + DELETE POST.
 * - 모든 write 는 window.FOMSNotificationWrite.fetch(same-origin write 헤더) 를 경유한다.
 * - app icon badge 는 navigator.setAppBadge feature detect + FOMSNotificationBadge 공유
 *   count 구독으로 반영(0 이면 clearAppBadge).
 *
 * foms_app_shell.html 에서 defer 로드되며 shell fragment 재실행 대상이므로 모든 상태는
 * window.__FOMS_MOBILE_PUSH_BOUND singleton 가드 뒤에서 document 위임으로 배선한다(perf G4).
 */
(function () {
  'use strict';
  if (window.__FOMS_MOBILE_PUSH_BOUND) return;
  window.__FOMS_MOBILE_PUSH_BOUND = true;

  var MOBILE_STATE_URL = '/erp/api/notifications/mobile-state';
  var VAPID_KEY_URL = '/erp/api/notifications/push/vapid-public-key';
  var SUBSCRIBE_URL = '/erp/api/notifications/push/subscribe';

  var vapidKeyCache = null;

  // ---- helpers --------------------------------------------------------------
  function ctaEl() {
    return document.querySelector('[data-foms-push-cta]');
  }

  function pushSupported() {
    return (
      'serviceWorker' in navigator &&
      'PushManager' in window &&
      'Notification' in window
    );
  }

  function isStandalone() {
    try {
      return (
        window.matchMedia('(display-mode: standalone)').matches ||
        window.navigator.standalone === true
      );
    } catch (e) {
      return false;
    }
  }

  function isIosSafari() {
    var ua = navigator.userAgent || '';
    var iOS =
      /iPad|iPhone|iPod/.test(ua) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    var webkit = /WebKit/i.test(ua);
    var notOtherEngine = !/CriOS|FxiOS|EdgiOS/i.test(ua);
    return iOS && webkit && notOtherEngine;
  }

  function detectPlatform() {
    var ua = navigator.userAgent || '';
    if (/Android/i.test(ua)) return 'android';
    if (/iPad|iPhone|iPod/.test(ua)) return 'ios';
    if (/Windows/i.test(ua)) return 'windows';
    if (/Macintosh|Mac OS X/i.test(ua)) return 'mac';
    return 'web';
  }

  function detectBrowser() {
    var ua = navigator.userAgent || '';
    if (/EdgiOS|Edg\//i.test(ua)) return 'edge';
    if (/CriOS|Chrome\//i.test(ua)) return 'chrome';
    if (/FxiOS|Firefox\//i.test(ua)) return 'firefox';
    if (/Safari\//i.test(ua)) return 'safari';
    return 'unknown';
  }

  function urlBase64ToUint8Array(base64String) {
    var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    var rawData = window.atob(base64);
    var outputArray = new Uint8Array(rawData.length);
    for (var i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  function toast(message) {
    if (typeof window.fomsShowToast === 'function') {
      window.fomsShowToast(message);
    } else {
      window.alert(message);
    }
  }

  function getRegistration() {
    if (typeof window.fomsRegisterServiceWorker === 'function') {
      return window.fomsRegisterServiceWorker();
    }
    return Promise.resolve(null);
  }

  // write helper — same-origin write 헤더가 붙는 공용 helper 경유(직접 fetch POST 금지).
  function writeJson(url, method, body) {
    if (!(window.FOMSNotificationWrite && typeof window.FOMSNotificationWrite.fetch === 'function')) {
      return Promise.reject(new Error('FOMSNotificationWrite unavailable'));
    }
    return window.FOMSNotificationWrite.fetch(url, {
      method: method,
      headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : null
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success) {
          throw new Error((data && data.error) || 'push write error');
        }
        return data;
      });
  }

  function fetchVapidKey() {
    if (vapidKeyCache) return Promise.resolve(vapidKeyCache);
    return fetch(VAPID_KEY_URL, {
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    })
      .then(function (res) {
        if (!res.ok) return null; // flag off 면 404
        return res.json();
      })
      .then(function (data) {
        if (data && data.success && data.data && data.data.public_key) {
          vapidKeyCache = data.data.public_key;
          return vapidKeyCache;
        }
        return null;
      })
      .catch(function (err) {
        console.error('[foms-push] vapid key error', err);
        return null;
      });
  }

  // ---- CTA rendering (정적 텍스트 — createElement/textContent 로 XSS 여지 제거) --------
  function clearCta() {
    var el = ctaEl();
    if (el) el.innerHTML = '';
    return el;
  }

  function hideCta() {
    var el = ctaEl();
    if (el) {
      el.hidden = true;
      el.innerHTML = '';
    }
  }

  function appendMessage(el, text, hintText) {
    var p = document.createElement('p');
    p.className = 'erp-mobile-push-cta__msg';
    p.textContent = text;
    el.appendChild(p);
    if (hintText) {
      var hint = document.createElement('p');
      hint.className = 'erp-mobile-push-cta__hint';
      hint.textContent = hintText;
      el.appendChild(hint);
    }
  }

  function renderButton(label, action, iconClass) {
    var el = clearCta();
    if (!el) return;
    el.hidden = false;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'erp-mobile-push-cta__btn';
    btn.setAttribute('data-foms-push-toggle', action);
    var icon = document.createElement('i');
    icon.className = iconClass;
    icon.setAttribute('aria-hidden', 'true');
    btn.appendChild(icon);
    btn.appendChild(document.createTextNode(' ' + label));
    el.appendChild(btn);
  }

  function renderUnsupported() {
    var el = clearCta();
    if (!el) return;
    el.hidden = false;
    if (isIosSafari() && !isStandalone()) {
      appendMessage(
        el,
        '이 브라우저는 기기 알림을 지원하지 않습니다.',
        '홈 화면에 추가하면 기기 알림을 받을 수 있습니다.'
      );
    } else {
      appendMessage(el, '이 브라우저는 기기 알림을 지원하지 않습니다.');
    }
  }

  // 차단(denied) 상태 안내: 웹/PWA 는 OS 알림 설정 화면을 프로그램적으로 열 수 없다
  // (iOS 설정 URL 스킴 차단, Android 설정 액티비티는 CATEGORY_BROWSABLE 부재로 링크 거부).
  // 딥링크 시도 대신 플랫폼별 정확한 수동 단계를 안내하고 복귀 시 자동 재평가한다.
  function guideSteps() {
    var ua = navigator.userAgent || '';
    var isAndroid = /android/i.test(ua);
    var isIos = /iphone|ipad|ipod/i.test(ua);
    var standalone = isStandalone();

    if (standalone && isIos) {
      return {
        title: '아이폰 홈 화면 앱에서 알림 켜기',
        items: [
          '설정 앱 → 알림 을 여세요.',
          '목록에서 이 앱(홈 화면에 추가한 이름)을 선택하세요.',
          "'알림 허용'을 켜세요."
        ]
      };
    }
    if (standalone && isAndroid) {
      return {
        title: '설치된 앱에서 알림 켜기',
        items: [
          '방법1: 홈 화면의 앱 아이콘을 길게 누르고 ⓘ(앱 정보) → 알림 → 허용',
          '방법2: 기기 설정 → 애플리케이션 → 이 앱 → 알림'
        ]
      };
    }
    if (isAndroid) {
      return {
        title: 'Chrome에서 알림 켜기',
        items: [
          '주소창 왼쪽 자물쇠(🔒) 아이콘 → 권한 → 알림 → 허용',
          '또는 Chrome ⋮ → 설정 → 사이트 설정 → 알림'
        ]
      };
    }
    return {
      title: '브라우저에서 알림 켜기',
      items: ['주소창의 자물쇠 아이콘 → 사이트 설정 → 알림 → 허용']
    };
  }

  function buildGuidePanel(guideId) {
    var wrap = document.createElement('div');
    wrap.className = 'erp-mobile-push-cta__guide';
    wrap.setAttribute('data-foms-push-guide', '');
    wrap.id = guideId;
    wrap.hidden = true;

    var steps = guideSteps();
    var title = document.createElement('p');
    title.className = 'erp-mobile-push-cta__guide-title';
    title.textContent = steps.title;
    wrap.appendChild(title);

    var ol = document.createElement('ol');
    ol.className = 'erp-mobile-push-cta__guide-steps';
    steps.items.forEach(function (text) {
      var li = document.createElement('li');
      li.textContent = text;
      ol.appendChild(li);
    });
    wrap.appendChild(ol);

    var foot = document.createElement('p');
    foot.className = 'erp-mobile-push-cta__hint';
    foot.textContent = '허용을 켜고 이 화면으로 돌아오면 자동으로 반영됩니다.';
    wrap.appendChild(foot);
    return wrap;
  }

  function renderDenied() {
    var el = clearCta();
    if (!el) return;
    el.hidden = false;
    appendMessage(el, '기기 알림 권한이 차단되어 있습니다.');

    var guideId = 'foms-push-guide-panel';
    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'erp-mobile-push-cta__btn erp-mobile-push-cta__btn--guide';
    toggle.setAttribute('data-foms-push-guide-toggle', '');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-controls', guideId);
    var icon = document.createElement('i');
    icon.className = 'fas fa-circle-question';
    icon.setAttribute('aria-hidden', 'true');
    toggle.appendChild(icon);
    toggle.appendChild(document.createTextNode(' 허용 방법 보기'));
    el.appendChild(toggle);

    el.appendChild(buildGuidePanel(guideId));
  }

  function renderEnable() {
    renderButton('기기 알림 켜기', 'enable', 'fas fa-bell');
  }

  function renderDisable() {
    renderButton('기기 알림 끄기', 'disable', 'fas fa-bell-slash');
  }

  function setBusy(busy) {
    var el = ctaEl();
    if (!el) return;
    var btn = el.querySelector('[data-foms-push-toggle]');
    if (btn) btn.disabled = !!busy;
  }

  // ---- state → CTA ----------------------------------------------------------
  function applyState(data) {
    var el = ctaEl();
    if (!el) return;
    data = data || {};

    // flag off(web_push_enabled false 또는 vapid 미설정) → CTA 비노출.
    if (!data.web_push_enabled || !data.vapid_configured) {
      hideCta();
      return;
    }
    el.hidden = false;

    if (!pushSupported()) {
      renderUnsupported();
      return;
    }
    if (window.Notification && Notification.permission === 'denied') {
      renderDenied();
      return;
    }

    // 서버 subscription_active 와 로컬 pushManager.getSubscription 일치 여부를 조율한다.
    getRegistration()
      .then(function (reg) {
        if (!reg || !reg.pushManager) return null;
        return reg.pushManager.getSubscription();
      })
      .then(function (localSub) {
        var active = !!(data.subscription_active && localSub);
        if (active) {
          renderDisable();
        } else {
          renderEnable();
        }
      })
      .catch(function (err) {
        console.error('[foms-push] subscription reconcile error', err);
        renderEnable();
      });
  }

  function refresh() {
    var el = ctaEl();
    if (!el) return;
    fetch(MOBILE_STATE_URL, {
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success) throw new Error('mobile-state error');
        applyState(data.data || {});
      })
      .catch(function (err) {
        console.error('[foms-push] mobile-state error', err);
        hideCta();
      });
  }

  // ---- enable / disable flows ----------------------------------------------
  function enable() {
    if (!pushSupported()) {
      renderUnsupported();
      return;
    }
    setBusy(true);
    Promise.resolve(Notification.requestPermission())
      .then(function (permission) {
        if (permission !== 'granted') {
          toast('알림 권한이 허용되지 않았습니다.');
          refresh();
          return null;
        }
        return fetchVapidKey().then(function (key) {
          if (!key) throw new Error('vapid key unavailable');
          return getRegistration().then(function (reg) {
            if (!reg || !reg.pushManager) throw new Error('service worker unavailable');
            return reg.pushManager.subscribe({
              userVisibleOnly: true,
              applicationServerKey: urlBase64ToUint8Array(key)
            });
          });
        });
      })
      .then(function (subscription) {
        if (!subscription) return null;
        var json = subscription.toJSON();
        var keys = json.keys || {};
        return writeJson(SUBSCRIBE_URL, 'POST', {
          endpoint: json.endpoint,
          keys: { p256dh: keys.p256dh, auth: keys.auth },
          platform: detectPlatform(),
          browser: detectBrowser(),
          permission_state: (window.Notification && Notification.permission) || 'granted'
        });
      })
      .then(function (result) {
        if (result) {
          toast('기기 알림이 켜졌습니다.');
        }
        refresh();
      })
      .catch(function (err) {
        console.error('[foms-push] enable failed', err);
        toast('기기 알림 설정에 실패했습니다.');
        refresh();
      })
      .finally(function () {
        setBusy(false);
      });
  }

  function disable() {
    setBusy(true);
    getRegistration()
      .then(function (reg) {
        if (!reg || !reg.pushManager) return null;
        return reg.pushManager.getSubscription();
      })
      .then(function (subscription) {
        if (!subscription) return null;
        var endpoint = subscription.endpoint;
        return subscription
          .unsubscribe()
          .catch(function () {
            // 로컬 해제 실패해도 서버 레코드는 정리한다.
            return true;
          })
          .then(function () {
            return writeJson(SUBSCRIBE_URL, 'DELETE', { endpoint: endpoint });
          });
      })
      .then(function () {
        toast('기기 알림이 꺼졌습니다.');
        refresh();
      })
      .catch(function (err) {
        console.error('[foms-push] disable failed', err);
        toast('기기 알림 해제에 실패했습니다.');
        refresh();
      })
      .finally(function () {
        setBusy(false);
      });
  }

  // ---- app icon badge (setAppBadge + 공유 count 구독) -------------------------
  function updateAppBadge(count) {
    try {
      var n = Number(count);
      if ('setAppBadge' in navigator) {
        if (Number.isFinite(n) && n > 0) {
          navigator.setAppBadge(n);
        } else if ('clearAppBadge' in navigator) {
          navigator.clearAppBadge();
        }
      }
    } catch (e) {
      /* noop — 미지원/권한 문제는 조용히 무시 */
    }
  }

  function subscribeAppBadge() {
    try {
      if (window.FOMSNotificationBadge && typeof window.FOMSNotificationBadge.subscribe === 'function') {
        window.FOMSNotificationBadge.subscribe('app-icon-badge', updateAppBadge);
      }
    } catch (e) {
      /* noop */
    }
  }

  // ---- document-delegated events (swap-safe) --------------------------------
  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;
    var toggle = e.target.closest('[data-foms-push-toggle]');
    if (toggle) {
      e.preventDefault();
      if (toggle.disabled) return;
      var action = toggle.getAttribute('data-foms-push-toggle');
      if (action === 'enable') enable();
      else if (action === 'disable') disable();
      return;
    }
    // 차단 안내 '허용 방법 보기' 토글 — 인라인 가이드 패널 확장/접기(aria-expanded 관리).
    var guideToggle = e.target.closest('[data-foms-push-guide-toggle]');
    if (guideToggle) {
      e.preventDefault();
      var panel = document.querySelector('[data-foms-push-guide]');
      if (panel) {
        var expanded = guideToggle.getAttribute('aria-expanded') === 'true';
        guideToggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
        panel.hidden = expanded;
      }
      return;
    }
    // 벨(시트 opener) 탭 시 최신 권한/구독 상태로 CTA 재평가.
    var opener = e.target.closest('[data-foms-notif-open]');
    if (opener) {
      refresh();
    }
  });

  // OS 설정에서 알림을 켜고 앱으로 복귀하면(가시성 visible) 권한이 더 이상 denied 가
  // 아닐 수 있으므로 CTA 를 자동 재평가한다(수동 새로고침 불필요).
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState !== 'visible') return;
    if (window.Notification && Notification.permission !== 'denied') {
      refresh();
    }
  });

  function init() {
    subscribeAppBadge();
    refresh();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
