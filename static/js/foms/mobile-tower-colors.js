/**
 * 모바일 홈 달력 — 칸 색 기준 시트(관리자·팀장). 회사 공통 한 벌.
 *  - 톱니 [data-foms-colors-open] → GET /erp/dashboard/calendar-colors 로 값·버전을 읽어 시트를 연다.
 *  - 저장 → POST 같은 주소 {enabled, yellow_from, pink_from, settings_version}.
 *    409(다른 사람이 먼저 저장) = 안내 후 최신 값으로 다시 채운다. 성공 = 시트 닫고 달력을 다시 읽는다
 *    (타워 요소에 foms:tower-calendar-reload → mobile-tower.js).
 * 문서 단위 위임이라 탭 스왑 뒤 다시 연결할 것이 없다(셸 run-once 스크립트).
 * 근거: docs/specs/2026-10-14-mobile-calendar-amount-colors_SPEC.md
 */
(function () {
  'use strict';

  if (window.__FOMS_TOWER_COLORS_BOUND) {
    return;
  }
  window.__FOMS_TOWER_COLORS_BOUND = true;

  var state = { version: 0, opener: null };

  function sheetEl() {
    return document.querySelector('[data-foms-colors-sheet]');
  }

  function showError(sheet, message) {
    var box = sheet.querySelector('[data-foms-colors-error]');
    if (!box) {
      return;
    }
    box.textContent = message || '';
    box.hidden = !message;
  }

  function fill(sheet, colors) {
    var form = sheet.querySelector('[data-foms-colors-form]');
    form.elements.yellow_from.value = colors.yellow_from == null ? '' : String(colors.yellow_from);
    form.elements.pink_from.value = colors.pink_from == null ? '' : String(colors.pink_from);
    form.elements.enabled.checked = !!colors.enabled;
  }

  function endpoint(sheet) {
    return sheet.getAttribute('data-foms-colors-endpoint') || '/erp/dashboard/calendar-colors';
  }

  async function load(sheet) {
    try {
      var res = await fetch(endpoint(sheet), { headers: { 'X-Requested-With': 'fetch' }, credentials: 'same-origin' });
      var data = await res.json();
      if (!data || !data.success || !data.data) {
        throw new Error('load failed');
      }
      state.version = data.data.version || 0;
      fill(sheet, data.data.colors || {});
      showError(sheet, '');
    } catch (err) {
      showError(sheet, '기준을 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.');
    }
  }

  function open(opener) {
    var sheet = sheetEl();
    if (!sheet) {
      return;
    }
    state.opener = opener || null;
    sheet.hidden = false;
    document.body.classList.add('foms-tower-sheet-open');
    load(sheet).then(function () {
      var first = sheet.querySelector('input[name="yellow_from"]');
      if (first) {
        first.focus();
      }
    });
  }

  function close() {
    var sheet = sheetEl();
    if (!sheet || sheet.hidden) {
      return;
    }
    sheet.hidden = true;
    document.body.classList.remove('foms-tower-sheet-open');
    if (state.opener && state.opener.isConnected) {
      state.opener.focus();
    }
  }

  /** 빈 칸 = 그 단계 없음(null). 숫자가 아니면 undefined 를 돌려 저장을 막는다. */
  function readMan(value) {
    var text = String(value || '').replace(/,/g, '').trim();
    if (!text) {
      return null;
    }
    return /^\d+$/.test(text) ? parseInt(text, 10) : undefined;
  }

  async function save(sheet) {
    var form = sheet.querySelector('[data-foms-colors-form]');
    var yellow = readMan(form.elements.yellow_from.value);
    var pink = readMan(form.elements.pink_from.value);
    if (yellow === undefined || pink === undefined) {
      showError(sheet, '기준은 0 이상의 숫자로 넣어 주세요.');
      return;
    }
    if (yellow != null && pink != null && pink <= yellow) {
      showError(sheet, '분홍 기준은 노랑 기준보다 커야 해요.');
      return;
    }
    var headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' };
    if (typeof window.fomsCsrfToken === 'function') {
      headers['X-CSRF-Token'] = window.fomsCsrfToken();
    }
    var button = form.querySelector('[type="submit"]');
    button.disabled = true;
    try {
      var res = await fetch(endpoint(sheet), {
        method: 'POST',
        credentials: 'same-origin',
        headers: headers,
        body: JSON.stringify({
          enabled: form.elements.enabled.checked,
          yellow_from: yellow,
          pink_from: pink,
          settings_version: state.version,
        }),
      });
      var data = await res.json();
      if (res.status === 409) {
        await load(sheet);
        showError(sheet, (data && data.error) || '다른 사람이 먼저 바꿨어요. 새로 불러왔어요.');
        return;
      }
      if (!data || !data.success) {
        showError(sheet, (data && data.error) || '저장하지 못했어요.');
        return;
      }
      state.version = data.data.version;
      close();
      var tower = document.querySelector('[data-foms-tower]');
      if (tower) {
        tower.dispatchEvent(new CustomEvent('foms:tower-calendar-reload'));
      }
    } catch (err) {
      showError(sheet, '저장하지 못했어요. 연결을 확인해 주세요.');
    } finally {
      button.disabled = false;
    }
  }

  document.addEventListener('click', function (ev) {
    var opener = ev.target.closest('[data-foms-colors-open]');
    if (opener) {
      open(opener);
      return;
    }
    if (ev.target.closest('[data-foms-colors-close]')) {
      close();
    }
  });

  document.addEventListener('submit', function (ev) {
    var form = ev.target.closest('[data-foms-colors-form]');
    if (!form) {
      return;
    }
    ev.preventDefault();
    save(form.closest('[data-foms-colors-sheet]'));
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') {
      close();
    }
  });
})();
