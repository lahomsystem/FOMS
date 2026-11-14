/* 생산팀 첫 화면 '날짜' 탭 — 날 고르기. 설계서 §15.6 '날 고르기'(11-14, 예전 D5 '15장 다 보내고 보이기/숨기기'를 바꿨다).
 * 서버는 고른 날 장 하나만 그린다. 왼쪽 띠에서 다른 날을 누르면 그 날 장만 받아(GET 같은 주소 + view=day, 응답 머리글
 * X-FOMS-HOME-DAY = 받은 날) 끼우고, 한 번 받은 날은 화면에 남겨 다시 누르면 바로 보인다. 누르는 즉시 켜짐 표시를 바꾸고,
 * 받는 동안 '받는 중' 한 줄 + 지금 장 흐리게, 못 받으면 연결 안내 글(설계서 §8 한 가지). 받는 중에 또 누르면 앞 요청을 버리고
 * (AbortController + 차례 번호) 마지막 누름만 반영한다. 날 단추는 진짜 링크(data-foms-erp-no-shell)라 이 파일이 묶이기 전에
 * 누르면 그 날 주소로 이동한다. 주소와 [다시 받기]도 그날로(replaceState — '도면 카드' 탭은 링크가 tab · part 를 싣는다).
 * 끼운 장의 도면 카드는 parts*.js 가 화면(root) 위임으로 받으므로 다시 묶을 것이 없다.
 * 셸 조각 교체로 다시 실행된다 — 같은 화면에는 한 번만 묶는다(data-foms-home-days-bound). 창 · 문서 리스너는 없다. */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  if (!root || root.getAttribute('data-foms-home-days-bound') === '1') { return; }
  if (!root.querySelector('[data-foms-home-panes]')) { return; } // 날짜 · 도면 카드 탭만
  root.setAttribute('data-foms-home-days-bound', '1');

  var OFFLINE_TEXT = '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.';
  var DAY_VIEW = 'day';
  var DAY_HEADER = 'X-FOMS-HOME-DAY';
  function toArr(list) { return [].slice.call(list); }

  var panesBox = root.querySelector('[data-foms-home-panes]');
  var dayLoad = root.querySelector('[data-foms-home-dayload]');
  var dayErr = root.querySelector('[data-foms-home-dayerr]');
  var dayReq = { seq: 0, ctl: null };
  var onDay = root.querySelector('[data-foms-home-daybtn].is-on');
  var currentDay = onDay ? onDay.getAttribute('data-foms-home-daybtn') : '';
  function dayPane(key) {
    return toArr(root.querySelectorAll('[data-foms-home-daypane]')).filter(function (p) {
      return p.getAttribute('data-foms-home-daypane') === key;
    })[0] || null;
  }
  function showPane(key) {
    toArr(root.querySelectorAll('[data-foms-home-daypane]')).forEach(function (p) {
      p.hidden = p.getAttribute('data-foms-home-daypane') !== key;
    });
  }
  function setDayBusy(on, errText) {
    if (panesBox) {
      panesBox.classList.toggle('is-loading', !!on);
      panesBox.setAttribute('aria-busy', on ? 'true' : 'false');
    }
    if (dayLoad) { dayLoad.hidden = !on; }
    if (dayErr) { dayErr.textContent = errText || ''; dayErr.hidden = !errText; }
  }
  function markDay(key) {
    toArr(root.querySelectorAll('[data-foms-home-daybtn]')).forEach(function (b) {
      var on = b.getAttribute('data-foms-home-daybtn') === key;
      b.classList.toggle('is-on', on);
      if (on) { b.setAttribute('aria-current', 'true'); } else { b.removeAttribute('aria-current'); }
    });
  }
  function keepDayUrl(href) {
    try { window.history.replaceState(window.history.state, '', href); } catch (e) { /* 주소를 못 바꿔도 화면은 그대로 */ }
    var shell = window.FOMS_ERP_SHELL;
    if (shell && typeof shell.syncRenderedUrl === 'function') { shell.syncRenderedUrl(); }
    var reload = root.querySelector('[data-foms-home-reload]');
    if (reload) { reload.setAttribute('href', href); }
  }
  function dropDayRequest() {
    dayReq.seq += 1; // 늦게 온 앞 응답은 버린다(마지막 누름만)
    if (dayReq.ctl) {
      try { dayReq.ctl.abort(); } catch (e) { /* 이미 끝난 요청 */ }
    }
    dayReq.ctl = null;
  }
  function fetchDay(key, href) {
    dropDayRequest();
    var seq = dayReq.seq;
    var ctl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    dayReq.ctl = ctl;
    var url = new URL(href, window.location.href);
    url.searchParams.set('view', DAY_VIEW);
    setDayBusy(true);
    var req;
    try {
      req = fetch(url.toString(), { credentials: 'same-origin', cache: 'no-store', signal: ctl ? ctl.signal : undefined,
        headers: { Accept: 'text/html', 'X-Requested-With': 'XMLHttpRequest' } });
    } catch (e) {
      req = Promise.reject(e);
    }
    req.then(function (res) {
      if (!res.ok || res.headers.get(DAY_HEADER) !== key) { throw new Error('day ' + res.status); }
      return res.text();
    }).then(function (html) {
      if (seq !== dayReq.seq) { return; }
      var tpl = document.createElement('template');
      tpl.innerHTML = html;
      var pane = tpl.content.querySelector('[data-foms-home-daypane]');
      if (!pane || pane.getAttribute('data-foms-home-daypane') !== key) { throw new Error('day pane'); }
      if (!dayPane(key) && panesBox) { panesBox.appendChild(pane); } // 받은 날은 남겨 둔다(다시 누르면 바로)
      dayReq.ctl = null;
      setDayBusy(false);
      showPane(currentDay);
      document.dispatchEvent(new CustomEvent('foms:prod-home-day-loaded', { detail: { key: key } }));
    }).catch(function (err) {
      if (seq !== dayReq.seq || (err && err.name === 'AbortError')) { return; }
      dayReq.ctl = null;
      showPane(''); // 옛 날 장을 새 날처럼 보이지 않게 — 안내 글만
      setDayBusy(false, OFFLINE_TEXT);
    });
  }
  function selectDay(btn) {
    var key = btn.getAttribute('data-foms-home-daybtn') || '';
    var href = btn.getAttribute('href') || (window.location.pathname + '?day=' + encodeURIComponent(key));
    currentDay = key;
    markDay(key); // 누르는 즉시 켜짐 표시
    keepDayUrl(href);
    window.scrollTo(0, 0);
    if (dayPane(key)) {
      dropDayRequest();
      setDayBusy(false);
      showPane(key);
      return;
    }
    fetchDay(key, href);
  }

  root.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || typeof t.closest !== 'function') { return; }
    var dayBtn = t.closest('[data-foms-home-daybtn]');
    if (!dayBtn || e.metaKey || e.ctrlKey || e.shiftKey || e.button > 0) { return; } // 새 탭으로 열기는 링크 그대로
    e.preventDefault();
    selectDay(dayBtn);
  });
})();
