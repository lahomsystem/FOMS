/**
 * 도면 마법사 — 완료 주문 AS 도면(설계서 docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md §4.3).
 *
 * 마법사 엔진(window.FomsWizardCore)에 붙어 화면만 돕는다. 지키는 일은 서버가 한다
 * (원래 시트 저장값 지키기 · 원래 시트 그림 대기함 막기 · [저장] 창 보내기 = AS 도면 보내기).
 *
 * - 탭: 원래·지난 차수 시트에 잠금 표시(지우기 ×·이름 바꾸기 숨김), AS 시트에 빨간 'AS N'.
 * - 처음 열 때 AS 시트가 없으면 "AS 시트 만들기" 창: 원래 도면 복사(탭 ⧉ 와 같은 복제) / 빈 시트.
 * - 종이 오른쪽 위 'AS N차' 도장 — #dws-stage 안이라 [저장] 그림(PNG)에도 찍힌다.
 * - AS 단계의 도면방 PUSH 는 [AS] AS 도면으로 보낸다(as-room-push.js). 차수가 없으면 보내지 않는다.
 */
(function () {
  'use strict';
  if (window.__DWS_AS_BOUND) return;
  window.__DWS_AS_BOUND = true;

  var cfg = {};
  try {
    cfg = JSON.parse((document.getElementById('drawing-wizard-config') || {}).textContent || '{}');
  } catch (e) { cfg = {}; }
  var asd = cfg && cfg.as_drawing;
  if (!asd) return;
  var round = asd.round || null;
  var locked = {};
  (asd.locked_sheet_ids || []).forEach(function (id) { locked[String(id)] = true; });
  var core = null;
  var asked = false;

  function isLocked(sheet) { return !!(sheet && locked[String(sheet.id)]); }
  function isAsSheet(sheet) { return !!(round && sheet && !isLocked(sheet)); }
  function shortDate(v) {
    var s = String(v || '');
    return s.length >= 10 ? s.slice(5, 10) : s;
  }

  function decorateTabs() {
    var bar = core.tabbar && core.tabbar();
    if (!bar) return;
    var sheets = core.state().sheets || [];
    var tabs = bar.querySelectorAll('.dws-tab');
    Array.prototype.forEach.call(tabs, function (tab, i) {
      var sheet = sheets[i];
      if (!sheet || tab.querySelector('.dws-tab-lock, .dws-tab-asmark')) return;   // 탭을 다시 안 그리고 부를 때(V2) 두 번 붙지 않게
      if (isLocked(sheet)) {
        tab.classList.add('dws-tab-locked');
        tab.title = '원래 도면 — 고칠 수 없어요. ⧉ 로 복제하면 AS 시트가 돼요.';
        var lock = document.createElement('span');
        lock.className = 'dws-tab-lock';
        lock.textContent = '잠금';
        tab.insertBefore(lock, tab.firstChild);
      } else if (isAsSheet(sheet)) {
        tab.classList.add('dws-tab-as');
        // 이름이 이미 'AS N' 으로 시작하면 빨간 표를 또 붙이지 않는다(같은 말 두 번 — 스테이징 실화면 11-12).
        if (String(sheet.name || '').replace(/\s+/g, '').indexOf('AS' + round.no) === 0) return;
        var mark = document.createElement('span');
        mark.className = 'dws-tab-asmark';
        mark.textContent = 'AS ' + round.no;
        tab.insertBefore(mark, tab.firstChild);
      }
    });
  }

  function stampEl() {
    var stage = document.getElementById('dws-stage');
    if (!stage) return null;
    var el = document.getElementById('dws-as-stamp');
    if (!el) {
      el = document.createElement('div');
      el.id = 'dws-as-stamp';
      el.className = 'dws-as-stamp';
      el.setAttribute('aria-hidden', 'true');
      stage.appendChild(el);
    }
    return el;
  }

  function updateStamp() {
    var el = stampEl();
    if (!el) return;
    var sheet = core.sheet && core.sheet();
    if (!isAsSheet(sheet)) {
      el.hidden = true;
      return;
    }
    var lines = ['AS ' + round.no + '차'];
    var sub = [];
    if (asd.as_received_date) sub.push('AS 접수 ' + shortDate(asd.as_received_date));
    if (asd.original_construction_date) sub.push('원래 시공 ' + shortDate(asd.original_construction_date));
    el.textContent = '';
    var head = document.createElement('strong');
    head.textContent = lines[0];
    el.appendChild(head);
    if (sub.length) {
      var small = document.createElement('span');
      small.textContent = sub.join(' · ');
      el.appendChild(small);
    }
    el.hidden = false;
  }

  function closeDialog(box) { if (box && box.parentNode) box.parentNode.removeChild(box); }

  function makeAsSheet(fromIndex) {
    var before = (core.state().sheets || []).length;
    if (typeof fromIndex === 'number' && fromIndex >= 0) {
      core.duplicateSheet(fromIndex);
    } else {
      core.addSheet();
    }
    var sheets = core.state().sheets || [];
    if (sheets.length === before) return;   // 시트 10장 한도 등으로 못 만들었다(엔진이 알렸다)
    var sheet = core.sheet();
    if (sheet && String(sheet.name || '').indexOf('AS' + round.no) !== 0) {
      // 복제 이름 끝의 ' 복사' 는 뺀다 — 앞의 'AS N' 이 원래 시트와 가른다.
      var base = String(sheet.name || '').replace(/ 복사( \d+)?$/, '');
      sheet.name = ('AS' + round.no + ' ' + base).slice(0, 50);
      core.markDirty();
      core.renderTabs();
    }
    core.toast('AS 시트를 만들었어요. 바뀌는 곳만 고치고 [저장]을 눌러 주세요.');
  }

  function openDialog() {
    var sheets = core.state().sheets || [];
    var sources = [];
    sheets.forEach(function (s, i) { if (isLocked(s)) sources.push({ i: i, name: s.name || ('시트 ' + (i + 1)) }); });
    var box = document.createElement('div');
    box.className = 'dws-as-dialog';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-label', 'AS 시트 만들기');
    var html = '<div class="dws-as-dialog-card"><h3>AS 시트 만들기</h3>'
      + '<p class="dws-as-dialog-note">AS ' + round.no + '차 도면이에요. 원래 도면은 바뀌지 않아요.</p>';
    if (sources.length) {
      html += '<label class="dws-as-opt"><input type="radio" name="dws-as-src" value="copy" checked>'
        + '<span><b>원래 도면 복사해서 시작</b><small>바뀌는 곳만 고치면 돼요.</small>'
        + '<select class="dws-as-src-sel"></select></span></label>';
    }
    html += '<label class="dws-as-opt"><input type="radio" name="dws-as-src" value="blank"' + (sources.length ? '' : ' checked') + '>'
      + '<span><b>빈 시트로 시작</b><small>원래 도면과 모양이 많이 다를 때</small></span></label>'
      + '<div class="dws-as-dialog-actions"><button type="button" class="dws-as-btn" data-as-close>닫기</button>'
      + '<button type="button" class="dws-as-btn dws-as-btn-primary" data-as-make>만들기</button></div></div>';
    box.innerHTML = html;
    var sel = box.querySelector('.dws-as-src-sel');
    sources.forEach(function (src) {
      var opt = document.createElement('option');
      opt.value = String(src.i);
      opt.textContent = src.name;
      if (sel) sel.appendChild(opt);
    });
    box.addEventListener('click', function (ev) {
      if (ev.target.closest('[data-as-close]')) { closeDialog(box); return; }
      if (!ev.target.closest('[data-as-make]')) return;
      var picked = box.querySelector('input[name="dws-as-src"]:checked');
      var copy = picked && picked.value === 'copy' && sel;
      closeDialog(box);
      makeAsSheet(copy ? Number(sel.value) : -1);
    });
    document.body.appendChild(box);
    var first = box.querySelector('[data-as-make]');
    if (first) first.focus();
  }

  function onLoaded() {
    decorateTabs();
    updateStamp();
    if (asked) return;
    asked = true;
    if (!round) {
      core.toast('시공이 끝난 주문이에요. 원래 도면은 볼 수만 있어요. 도면 작업실 실행판에서 [AS 도면 시작]을 먼저 눌러 주세요.');
      return;
    }
    var sheets = core.state().sheets || [];
    var hasAs = sheets.some(function (s) { return isAsSheet(s); });
    if (!hasAs && core.canSave()) openDialog();
  }

  function guardRoomPush() {
    // [저장] 창의 "도면방에도 보내기" — 완료 주문은 원래 최종 도면이 아니라 [AS] AS 도면을 보낸다(D4).
    core.pushRoom = function (opts) {
      if (!round || !window.FomsAsRoomPush) {
        core.toast('AS 도면을 먼저 시작해야 도면방으로 보낼 수 있어요.');
        return Promise.resolve(false);
      }
      return window.FomsAsRoomPush.send(core.orderId, { skipConfirm: !!(opts && opts.skipConfirm), toast: core.toast });
    };
  }

  function init() {
    core = window.FomsWizardCore;
    if (!core || typeof core.on !== 'function') return;
    guardRoomPush();
    core.on('sheet', function () { decorateTabs(); updateStamp(); });
    core.on('loaded', onLoaded);
    if (core.hydrated && core.hydrated()) onLoaded();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
