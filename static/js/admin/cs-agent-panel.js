/**
 * 관리자 — AI 상담팀원 관리 패널(templates/admin/cs_agent.html, 설계서 16.1 단계 1).
 *
 * 화면은 서버가 그린다. 이 스크립트는 쓰기만 한다: 비상 정지 · 초안 스위치 · 두뇌 설정 저장을
 * JSON API(/api/admin/cs-agent/*)로 보내고, 성공하면 같은 탭으로 화면을 다시 읽는다.
 * CSRF 토큰은 공용 csrf_bootstrap 의 fetch 래퍼가 붙인다. 글은 textContent 로만 넣는다(innerHTML 없음).
 * 잠긴 칸(다음 단계 — disabled)은 보내지 않는다. 저장 성공 글은 다시 읽은 뒤 한 번 보인다(sessionStorage — 못 쓰면 없이 간다).
 */
(function () {
  'use strict';
  if (window.__FOMS_CS_AGENT_PANEL_BOUND) return;
  window.__FOMS_CS_AGENT_PANEL_BOUND = true;

  var root = document.querySelector('[data-cs-agent-panel]');
  if (!root) return;
  var busy = false;
  var FLASH_KEY = 'foms.csAgentPanel.flash';

  function message(kind, text) {
    var box = root.querySelector('[data-cs-message]');
    if (!box) return;
    box.className = 'alert cs-agent-message alert-' + kind;
    box.textContent = text;
    box.scrollIntoView({ block: 'nearest' });
  }

  function keepFlash(text) {
    try {
      window.sessionStorage.setItem(FLASH_KEY, text);
      return true;
    } catch (err) {
      return false;  // 저장소를 못 쓰면(사생활 모드 등) 글 없이 다시 읽는다 — 화면은 그대로 맞다
    }
  }

  function showFlash() {
    var text = null;
    try {
      text = window.sessionStorage.getItem(FLASH_KEY);
      window.sessionStorage.removeItem(FLASH_KEY);
    } catch (err) {
      text = null;
    }
    if (text) message('success', text);
  }

  function reloadAt(tabId) {
    if (tabId && window.history && window.history.replaceState) {
      window.history.replaceState(null, '', window.location.pathname + window.location.search + '#' + tabId);
    }
    window.location.reload();  // 다시 읽으면 같은 탭을 연다(showTabFromHash)
  }

  function setBusy(on) {
    busy = on;
    root.querySelectorAll('button').forEach(function (btn) {
      if (on) {
        btn.setAttribute('data-cs-was-disabled', btn.disabled ? '1' : '0');
        btn.disabled = true;
      } else if (btn.getAttribute('data-cs-was-disabled') === '0') {
        btn.disabled = false;
      }
    });
  }

  async function postJson(url, body) {
    var response;
    var data = null;
    try {
      response = await fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(body)
      });
    } catch (err) {
      return { ok: false, status: 0, data: null, error: '서버에 닿지 못했습니다. 네트워크를 확인해 주세요.' };
    }
    try {
      data = await response.json();
    } catch (err) {
      data = null;
    }
    if (!data || typeof data !== 'object') {
      return { ok: false, status: response.status, data: null, error: '응답을 읽지 못했습니다(' + response.status + ').' };
    }
    if (!response.ok || !data.success) {
      return { ok: false, status: response.status, data: data.data || null,
        error: data.error || '저장하지 못했습니다(' + response.status + ').' };
    }
    return { ok: true, status: response.status, data: data.data || {}, error: null };
  }

  async function send(url, body, tabId) {
    if (busy) return null;
    setBusy(true);
    var result = await postJson(url, body);
    if (result.ok) {
      var done = result.data.changed === false ? '이미 그 값입니다.' : '저장했습니다. 다음 차례부터 적용됩니다.';
      message('success', done);
      keepFlash(done);
      reloadAt(tabId);
      return result;
    }
    setBusy(false);
    message(result.status === 409 ? 'warning' : 'danger', result.error);
    return result;
  }

  function onLoopClick(btn) {
    var turnOn = btn.getAttribute('data-cs-loop') === 'on';
    var question = turnOn
      ? '감시 루프를 다시 켤까요? 다음 바퀴부터 상태 맞추기 · 보고 · 초안(스위치대로)이 다시 돕니다.'
      : '감시 루프를 멈출까요? 다음 바퀴부터 상태 맞추기 · 아침 보고 · 경보 · 초안이 모두 쉽니다.';
    if (!window.confirm(question)) return;
    send(root.getAttribute('data-loop-url'), { on: turnOn }, 'cs-tab-switch');
  }

  function onDraftClick(btn) {
    if (btn.getAttribute('aria-pressed') === 'true') return;
    var mode = btn.getAttribute('data-cs-draft');
    var questions = {
      off: '초안을 끌까요? 감시 · 보고는 그대로 돕니다.',
      store: '초안을 "저장만"으로 둘까요? 채널톡에는 아무것도 올리지 않습니다.',
      memo: '초안을 채널톡 상담에 직원만 보는 내부 메모로 올릴까요? 손님에게는 보내지 않습니다.'
    };
    if (!window.confirm(questions[mode] || '초안 스위치를 바꿀까요?')) return;
    send(root.getAttribute('data-draft-url'), { mode: mode }, 'cs-tab-switch');
  }

  function fieldValue(input) {
    var kind = input.getAttribute('data-kind');
    var raw = input.value;
    if (kind === 'bool') return raw === 'true';
    if (kind === 'choice-number') return Number(raw);
    if (kind === 'money') return raw.trim() === '' ? null : raw.trim();
    if (kind === 'int') {
      var number = Number(raw);
      return raw.trim() !== '' && Number.isInteger(number) ? number : raw;  // 틀린 값은 그대로 — 서버가 칸 이름으로 거절한다
    }
    return raw;
  }

  function markInvalid(form, fields) {
    form.querySelectorAll('[data-setting]').forEach(function (input) {
      input.classList.toggle('is-invalid', fields.indexOf(input.getAttribute('data-setting')) !== -1);
    });
  }

  async function onSettingsSubmit(form) {
    var values = {};
    form.querySelectorAll('[data-setting]').forEach(function (input) {
      if (input.disabled) return;  // 다음 단계 칸 — 보내지 않는다
      values[input.getAttribute('data-setting')] = fieldValue(input);
    });
    markInvalid(form, []);
    var version = Number(form.getAttribute('data-version'));
    var result = await send(root.getAttribute('data-settings-url'),
      { values: values, expected_version: version }, 'cs-tab-brain');
    if (!result || result.ok) return;
    if (result.status === 400 && result.data && Array.isArray(result.data.fields)) {
      markInvalid(form, result.data.fields);
    }
    if (result.status === 409 && window.confirm(result.error + '\n지금 값을 새로 불러올까요? 입력한 값은 사라집니다.')) {
      reloadAt('cs-tab-brain');
    }
  }

  function showTabFromHash() {
    var id = (window.location.hash || '').replace('#', '');
    if (!id || !window.bootstrap || !window.bootstrap.Tab) return;
    var button = root.querySelector('[data-bs-target="#' + id + '"]');
    if (button) window.bootstrap.Tab.getOrCreateInstance(button).show();
  }

  root.addEventListener('click', function (event) {
    var loopBtn = event.target.closest('[data-cs-loop]');
    if (loopBtn) { onLoopClick(loopBtn); return; }
    var draftBtn = event.target.closest('[data-cs-draft]');
    if (draftBtn) { onDraftClick(draftBtn); return; }
    if (event.target.closest('[data-cs-reload]')) reloadAt('cs-tab-records');
  });

  root.addEventListener('submit', function (event) {
    var form = event.target.closest('[data-cs-settings]');
    if (!form) return;
    event.preventDefault();
    onSettingsSubmit(form);
  });

  root.addEventListener('shown.bs.tab', function (event) {
    var target = (event.target.getAttribute('data-bs-target') || '').replace('#', '');
    if (target && window.history && window.history.replaceState) {
      window.history.replaceState(null, '', '#' + target);
    }
  });

  showTabFromHash();
  showFlash();
})();
