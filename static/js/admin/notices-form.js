/**
 * FOMS 공지사항 쓰기 · 고치기(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §4 · §5).
 * - 받는 쪽 칩: GET /api/admin/notices/audience-options 의 teams · partners 로 그린다(본사 · 협력사 둘 다 고를 수 있다).
 * - 받는 사람 수: 같은 응답의 counts 로 칩을 누를 때마다 다시 센다.
 * - 저장: 새 공지 POST /api/admin/notices · 고치기 PUT /api/admin/notices/<id> (페이로드는 설계서 §4 그대로).
 * CSRF 토큰은 공용 csrf_bootstrap 의 fetch 래퍼가 붙인다. 글은 textContent 로만 넣는다(innerHTML 없음).
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-notice-form]');
  if (!root) return;
  var form = root.querySelector('[data-notice-form-el]');
  var messageBox = root.querySelector('[data-notice-message]');
  var countBox = root.querySelector('[data-audience-count]');
  var submitBtn = root.querySelector('[data-notice-submit]');
  var apiUrl = root.getAttribute('data-api-url') || '/api/admin/notices';
  var pageBase = root.getAttribute('data-page-base') || '/admin/notices';
  var isEdit = root.getAttribute('data-mode') === 'edit';
  var current = safeJsonParse(root.getAttribute('data-notice'), {});
  var counts = { staff_all: 0, by_team: {}, partner_all: 0, by_org: {} };
  var audience = { staffAll: false, teams: {}, partnerAll: false, orgs: {} };
  var busy = false;

  function safeJsonParse(val, fb) {
    try {
      var text = String(val || '').trim();
      if (!text) return fb;
      var parsed = JSON.parse(text);
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : fb;
    } catch (err) {
      return fb;
    }
  }

  function field(name) { return form.querySelector('[data-notice-field="' + name + '"]'); }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function message(kind, text) {
    if (!messageBox) return;
    messageBox.className = 'alert foms-notice-admin__message alert-' + kind;
    messageBox.textContent = text;
    messageBox.scrollIntoView({ block: 'nearest' });
  }

  async function requestJson(url, method, body) {
    var response;
    var data = null;
    var init = { method: method, credentials: 'same-origin', headers: { 'Accept': 'application/json' } };
    if (body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    try {
      response = await fetch(url, init);
    } catch (err) {
      return { ok: false, data: null, error: '서버에 닿지 못했습니다. 인터넷 연결을 확인해 주세요.' };
    }
    try {
      data = await response.json();
    } catch (err) {
      data = null;
    }
    if (!data || typeof data !== 'object') {
      return { ok: false, data: null, error: '응답을 읽지 못했습니다(' + response.status + ').' };
    }
    if (!response.ok || !data.success) {
      return { ok: false, data: null, error: data.error || '저장하지 못했습니다(' + response.status + ').' };
    }
    return { ok: true, data: data.data || {}, error: null };
  }

  // ── 받는 쪽 칩 ───────────────────────────────────────────────────────
  function chip(side, kind, value, label) {
    var button = el('button', 'foms-notice-chip foms-notice-chip--' + side, label);
    button.type = 'button';
    button.setAttribute('data-audience-chip', kind);
    button.setAttribute('data-value', String(value));
    button.setAttribute('aria-pressed', 'false');
    return button;
  }

  function renderOptions(data) {
    var staffBox = root.querySelector('[data-audience-chips="staff"]');
    var partnerBox = root.querySelector('[data-audience-chips="partner"]');
    (data.teams || []).forEach(function (team) {
      staffBox.appendChild(chip('staff', 'team', team.code, team.label || team.code));
    });
    var partners = data.partners || [];
    partners.forEach(function (org) {
      partnerBox.appendChild(chip('partner', 'org', org.id, org.name || ('협력사 ' + org.id)));
    });
    if (!partners.length) partnerBox.appendChild(el('span', 'foms-notice-help', '등록된 협력사가 없어요.'));
    if (data.counts) counts = data.counts;
  }

  function isPressed(button) {
    var kind = button.getAttribute('data-audience-chip');
    var value = button.getAttribute('data-value');
    if (kind === 'staff-all') return audience.staffAll;
    if (kind === 'partner-all') return audience.partnerAll;
    if (kind === 'team') return !!audience.teams[value];
    return !!audience.orgs[value];
  }

  function onChip(button) {
    var kind = button.getAttribute('data-audience-chip');
    var value = button.getAttribute('data-value');
    if (kind === 'staff-all') {
      audience.staffAll = !audience.staffAll;
      if (audience.staffAll) audience.teams = {};
    } else if (kind === 'partner-all') {
      audience.partnerAll = !audience.partnerAll;
      if (audience.partnerAll) audience.orgs = {};
    } else if (kind === 'team') {
      audience.staffAll = false;
      if (audience.teams[value]) delete audience.teams[value]; else audience.teams[value] = true;
    } else {
      audience.partnerAll = false;
      if (audience.orgs[value]) delete audience.orgs[value]; else audience.orgs[value] = true;
    }
    refresh();
  }

  function sumOf(map, keys) {
    return keys.reduce(function (total, key) { return total + (Number((map || {})[key]) || 0); }, 0);
  }

  function sides() {
    var staff = audience.staffAll || Object.keys(audience.teams).length > 0;
    var partner = audience.partnerAll || Object.keys(audience.orgs).length > 0;
    if (staff && partner) return 'both';
    if (staff) return 'staff';
    return partner ? 'partner' : 'none';
  }

  function renderCount() {
    if (sides() === 'none') {
      countBox.textContent = '받는 쪽을 골라 주세요.';
      return;
    }
    var staffN = audience.staffAll ? Number(counts.staff_all) || 0 : sumOf(counts.by_team, Object.keys(audience.teams));
    var partnerN = audience.partnerAll ? Number(counts.partner_all) || 0 : sumOf(counts.by_org, Object.keys(audience.orgs));
    countBox.textContent = '받는 사람 ' + (staffN + partnerN) + '명 · 본사 ' + staffN + '명 · 협력사 ' + partnerN + '명';
  }

  // ── 휴대폰 미리보기 ─────────────────────────────────────────────────
  function renderPreview() {
    var title = field('title').value.trim() || '제목이 여기에 보여요';
    var body = field('body').value.trim() || '내용이 여기에 보여요.';
    var popup = displayMode() === 'POPUP';
    var side = sides();
    root.querySelector('[data-preview-title]').textContent = title;
    root.querySelector('[data-preview-body]').textContent = body;
    root.querySelector('[data-preview-list-title]').textContent = title;
    root.querySelector('[data-preview-popup]').classList.toggle('d-none', !popup);
    root.querySelector('[data-preview-list]').classList.toggle('d-none', popup);
    root.querySelector('[data-preview-pin]').classList.toggle('d-none', !field('pinned').checked);
    root.querySelector('[data-preview-phone]').setAttribute('data-side', side);
    root.querySelector('[data-preview-bar]').textContent = side === 'partner' ? 'FOMS 협력사' : 'FOMS';
    root.querySelectorAll('[data-preview-side]').forEach(function (node) {
      node.classList.toggle('is-active', node.getAttribute('data-preview-side') === side);
    });
    root.querySelector('[data-preview-help]').textContent = popup
      ? '받는 사람이 화면을 열면 가운데 창이 뜨고, [확인]을 눌러야 닫혀요.'
      : '창은 안 뜨고, 공지사항 목록 맨 위(고정이면)나 새 글 자리에 보여요.';
  }

  function displayMode() {
    var checked = form.querySelector('[data-notice-field="display_mode"]:checked');
    return checked ? checked.value : 'POPUP';
  }

  function refresh() {
    root.querySelectorAll('[data-audience-chip]').forEach(function (button) {
      button.setAttribute('aria-pressed', isPressed(button) ? 'true' : 'false');
    });
    renderCount();
    renderPreview();
  }

  // ── 미리 채우기 · 저장 ─────────────────────────────────────────────
  function prefill() {
    if (!current || !current.id) return;
    var aud = current.audience || {};
    audience.staffAll = !!aud.staff_all;
    audience.partnerAll = !!aud.partner_all;
    (aud.staff_teams || []).forEach(function (code) { audience.teams[String(code)] = true; });
    (aud.partner_org_ids || []).forEach(function (id) { audience.orgs[String(id)] = true; });
    field('title').value = current.title || '';
    field('body').value = current.body || '';
    field('starts_at').value = current.starts_at || '';
    field('ends_at').value = current.ends_at || '';
    field('pinned').checked = !!current.pinned;
    var mode = form.querySelector('[data-notice-field="display_mode"][value="' + (current.display_mode || 'POPUP') + '"]');
    if (mode) mode.checked = true;
  }

  function payload() {
    return {
      title: field('title').value.trim(),
      body: field('body').value,
      audience: {
        staff_all: audience.staffAll,
        staff_teams: Object.keys(audience.teams),
        partner_all: audience.partnerAll,
        partner_org_ids: Object.keys(audience.orgs).map(Number)
      },
      display_mode: displayMode(),
      pinned: field('pinned').checked,
      starts_at: field('starts_at').value || '',
      ends_at: field('ends_at').value || ''
    };
  }

  function problem(data) {
    if (!data.title) return '제목을 써 주세요.';
    if (data.title.length > 200) return '제목은 200자까지 쓸 수 있어요.';
    if (sides() === 'none') return '받는 쪽을 하나 이상 골라 주세요.';
    if (data.starts_at && data.ends_at && data.ends_at <= data.starts_at) return '끝 시각은 시작 시각보다 뒤여야 해요.';
    return '';
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (busy) return;
    var data = payload();
    var why = problem(data);
    if (why) {
      message('warning', why);
      return;
    }
    busy = true;
    submitBtn.disabled = true;
    var url = isEdit ? apiUrl + '/' + current.id : apiUrl;
    var result = await requestJson(url, isEdit ? 'PUT' : 'POST', data);
    if (!result.ok) {
      busy = false;
      submitBtn.disabled = false;
      message('danger', result.error);
      return;
    }
    try {
      window.sessionStorage.setItem('foms-notice-flash', isEdit ? '고친 내용을 저장했어요.' : '공지를 올렸어요.');
    } catch (err) { /* sessionStorage 막힘 — 글만 안 보인다 */ }
    window.location.href = pageBase;
  }

  async function loadOptions() {
    var result = await requestJson(root.getAttribute('data-options-url'), 'GET');
    if (!result.ok) {
      message('danger', '받는 쪽 목록을 불러오지 못했어요. ' + result.error);
      return;
    }
    renderOptions(result.data);
    refresh();
  }

  root.addEventListener('click', function (event) {
    var button = event.target.closest('[data-audience-chip]');
    if (button) onChip(button);
  });
  form.addEventListener('input', renderPreview);
  form.addEventListener('change', renderPreview);
  form.addEventListener('submit', onSubmit);

  prefill();
  refresh();
  loadOptions();
})();
