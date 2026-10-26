/**
 * 도면 마법사 — 알림(토스트) 쌓기: 같은 글 합치기 · 같은 key 고쳐 쓰기 · 3개 상한 · 대화 상자 위에 띄우기.
 *
 * 2026-10-25 실화면 QA(보통): 알림이 4초 이상 남게 되자(평가 보통-6) 연달아 뜬 알림이 한꺼번에 쌓였다.
 * Enter 로 5장을 확인하면 같은 '확인했어요' 5개가 시트 아래 제목·주소 칸을 4초 동안 가렸고, [일괄 저장] 5장은
 * '1/5 처리 중'…'5/5' 와 마무리 알림까지 6개가 한꺼번에 떠 있었다. 또 규칙 창(<dialog> showModal)이 열린 채 뜬
 * 알림('다른 사람이 먼저 규칙을 고쳤습니다'·'칸에 정수를 넣어 주세요')은 흐린 바탕 밑에 깔렸다 — 모달 창은 브라우저
 * 맨 위 층(top layer)에 올라가서 z-index 를 아무리 올려도 그 위로 못 간다.
 * - 같은 글이 떠 있으면 새로 쌓지 않고 '(5)'처럼 횟수만 올린다(오류 알림도 같은 글이면 하나).
 * - opts.key 가 같은 알림은 그 하나를 고쳐 쓴다(일괄 저장·내보내기의 'n/N 처리 중').
 * - 한 번에 3개까지 — 넘치면 오래된 일반 알림부터 닫는다(오류 알림은 닫을 일반 알림이 없을 때만).
 * - 모달 창이 열려 있으면 알림을 그 창 안의 알림 자리에 띄운다(창의 일부라 맨 위 층에 같이 오르고, 창 밖이 막혀도
 *   '다시 시도'·'×' 를 누를 수 있다). 창이 닫히면 남은 알림은 원래 자리(#dws-toast-host)로 돌아온다.
 *
 * window.FomsWizardToast = {
 *   MAX, label(text, n), findIndex(list, text, opts), evictList(list, max),     // 순수(node 시험)
 *   reuse(msg, opts, ms), add(home, el, msg, opts, ms), remove(el), drop(key), count()
 * }
 */
(function () {
  'use strict';
  if (window.FomsWizardToast) { return; }

  var MAX = 3;          // 한 번에 보이는 알림 수
  var FADE_MS = 240;    // .dws-toast 사라짐 전환(wizard.css)
  var live = [];        // 떠 있는 알림 { el, textEl, text, key, error, retry, n, seq, timer }
  var seq = 0;
  var homeHost = null;  // 원래 알림 자리(#dws-toast-host) — add 가 받는다

  /* ---- 순수 ------------------------------------------------------------- */

  /** 알림 글 — 같은 글이 여러 번 왔으면 뒤에 '(n)'. */
  function label(text, n) {
    return n > 1 ? text + ' (' + n + ')' : text;
  }

  /** 고쳐 쓸 알림의 자리 — key 가 있으면 같은 key, 없으면 같은 글·같은 종류(일반/오류, 다시 시도 단추 유무)이고
      key 가 없는 알림. 없으면 -1. */
  function findIndex(list, text, opts) {
    var o = opts || {};
    var key = o.key ? String(o.key) : '';
    var retry = typeof o.retry === 'function';
    for (var i = 0; i < list.length; i++) {
      var e = list[i];
      if (key) {
        if (e.key === key) { return i; }
      } else if (!e.key && e.text === text && e.error === !!o.error && e.retry === retry) {
        return i;
      }
    }
    return -1;
  }

  /** 알림 하나를 더 띄울 때 닫을 것 — 상한을 넘는 만큼, 마지막으로 고친 때가 이른 일반 알림부터, 모자라면 오류 알림. */
  function evictList(list, max) {
    var over = list.length + 1 - max;
    if (over <= 0) { return []; }
    function bySeq(a, b) { return a.seq - b.seq; }
    var plain = list.filter(function (e) { return !e.error; }).sort(bySeq);
    var errs = list.filter(function (e) { return e.error; }).sort(bySeq);
    return plain.concat(errs).slice(0, over);
  }

  /* ---- 모달 창 위 알림 자리 ---------------------------------------------- */

  function isModal(dlg) {
    try { return dlg.matches(':modal'); } catch (e) { return true; }   // :modal 을 모르는 옛 브라우저 — 마법사 창은 모두 모달로 연다
  }

  /** 지금 맨 위 모달 창(없으면 null). */
  function topModal() {
    if (typeof document.querySelectorAll !== 'function') { return null; }
    var list = document.querySelectorAll('dialog[open]');
    for (var i = list.length - 1; i >= 0; i--) {
      if (isModal(list[i])) { return list[i]; }
    }
    return null;
  }

  /** 모달 창 안의 알림 자리(처음이면 만든다). 창이 닫히면 남은 알림을 home 으로 돌린다. */
  function modalHost(dlg, home) {
    var h = dlg.querySelector('.dws-toast-host-modal');
    if (h) { return h; }
    h = document.createElement('div');
    h.className = 'dws-toast-host dws-toast-host-modal';
    h.setAttribute('aria-live', 'polite');
    dlg.appendChild(h);
    dlg.addEventListener('close', function () {
      while (h.firstChild) { home.appendChild(h.firstChild); }
    });
    return h;
  }

  function hostFor(home) {
    var dlg = topModal();
    return dlg ? modalHost(dlg, home) : home;
  }

  /** 떠 있는 알림을 모두 지금 층(모달 창이 있으면 그 창 위, 없으면 원래 자리)으로 모은다. */
  function gather() {
    if (!homeHost) { return; }
    var host = hostFor(homeHost);
    live.forEach(function (x) { if (x.el.parentNode !== host) { host.appendChild(x.el); } });
  }

  /* ---- 화면 ------------------------------------------------------------- */

  function textOf(msg) { return String(msg || ''); }   // 마법사 toast() 가 화면에 쓰는 글과 같게

  function detach(el) { if (el.parentNode) { el.parentNode.removeChild(el); } }

  /** 알림을 닫는다. now 면 사라짐 전환 없이 바로 뺀다(같은 자리를 새 알림이 이어받을 때). */
  function close(e, now) {
    var i = live.indexOf(e);
    if (i >= 0) { live.splice(i, 1); }
    if (e.timer) { clearTimeout(e.timer); e.timer = null; }
    e.el.classList.remove('dws-toast-show');
    if (now) { detach(e.el); return; }
    setTimeout(function () { detach(e.el); }, FADE_MS);
  }

  /** 일반 알림은 ms 뒤 닫는다(고쳐 쓰면 처음부터 다시 잰다). 오류 알림은 × 를 누를 때까지 남는다. */
  function arm(e, ms) {
    if (e.timer) { clearTimeout(e.timer); e.timer = null; }
    if (!e.error && ms > 0) { e.timer = setTimeout(function () { close(e, false); }, ms); }
  }

  /** 같은 key·같은 글 알림이 떠 있으면 그것을 고쳐 쓰고 true. 일반 알림 자리에 오류가 오면 옛 것을 닫고 false(새로 띄운다). */
  function reuse(msg, opts, ms) {
    var o = opts || {};
    var text = textOf(msg);
    var i = findIndex(live, text, o);
    if (i < 0) { return false; }
    var e = live[i];
    if (e.error !== !!o.error) { close(e, true); return false; }
    e.n = e.text === text ? e.n + 1 : 1;
    e.text = text;
    e.seq = ++seq;
    e.textEl.textContent = label(text, e.n);
    gather();   // 그사이 모달 창이 열렸으면 고친 알림도 그 위로
    arm(e, ms);
    return true;
  }

  /** 새 알림(el, 마법사가 만든 .dws-toast)을 띄운다 — 상한 넘는 몫을 닫고, 모달 창이 열려 있으면 그 창 위 자리로.
      home 은 #dws-toast-host. 오류 알림이면 opts.error, 글 칸이 따로 있으면 .dws-toast-text 를 고쳐 쓴다. */
  function add(home, el, msg, opts, ms) {
    var o = opts || {};
    evictList(live, MAX).forEach(function (x) { close(x, true); });
    var e = {
      el: el,
      textEl: (typeof el.querySelector === 'function' && el.querySelector('.dws-toast-text')) || el,
      text: textOf(msg), key: o.key ? String(o.key) : '', error: !!o.error, retry: typeof o.retry === 'function',
      n: 1, seq: ++seq, timer: null
    };
    live.push(e);
    homeHost = home || homeHost;
    gather();   // 새 알림과 떠 있던 알림을 같은 층으로(새 것은 맨 아래)
    if (typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(function () { el.classList.add('dws-toast-show'); });
    } else {
      el.classList.add('dws-toast-show');
    }
    arm(e, ms);
    return el;
  }

  /** 알림 하나를 닫는다(오류 알림의 ×·다시 시도). */
  function remove(el) {
    for (var i = 0; i < live.length; i++) {
      if (live[i].el === el) { close(live[i], false); return true; }
    }
    return false;
  }

  /** key 알림을 닫는다(일괄 작업이 끝나 마무리 알림이 뜨기 직전 — 진행 알림이 남지 않게). */
  function drop(key) {
    var k = String(key || '');
    live.filter(function (e) { return k && e.key === k; }).forEach(function (e) { close(e, false); });
  }

  window.FomsWizardToast = {
    MAX: MAX,
    label: label,
    findIndex: findIndex,
    evictList: evictList,
    reuse: reuse,
    add: add,
    remove: remove,
    drop: drop,
    count: function () { return live.length; }
  };
})();
