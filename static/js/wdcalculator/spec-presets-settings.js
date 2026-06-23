/**
 * 현장 스펙 프리셋 관리 (제품 설정 페이지)
 *
 * ERP 주문 현장 스펙 입력의 드롭다운 소스(색상/손잡이/내부/기타)를 CRUD한다.
 * 백엔드: /api/wdcalculator/spec-field-presets (GET/POST/DELETE).
 * defer 로드 + 단일 바인딩 가드(중복 실행 방지, 성능 가드 G4).
 */
(function () {
  'use strict';

  if (window.__wdcSpecPresetsBound) return;
  window.__wdcSpecPresetsBound = true;

  var ENDPOINT = '/api/wdcalculator/spec-field-presets';

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  function showToast(message, isSuccess) {
    var toastEl = document.getElementById('status-toast');
    if (!toastEl || !window.bootstrap || !window.bootstrap.Toast) {
      // 폴백: 최소한의 알림(토스트 미가용 시)
      if (!isSuccess) console.warn('[spec-presets]', message);
      return;
    }
    var body = toastEl.querySelector('.toast-body');
    if (body) body.textContent = message;
    toastEl.classList.remove('bg-danger', 'bg-success', 'text-white');
    toastEl.classList.add(isSuccess ? 'bg-success' : 'bg-danger', 'text-white');
    window.bootstrap.Toast.getOrCreateInstance(toastEl).show();
  }

  function parseInitial() {
    try {
      var el = document.getElementById('initial-spec-presets');
      if (!el) return {};
      return JSON.parse(el.textContent || '{}') || {};
    } catch (err) {
      console.error('[spec-presets] 초기 데이터 파싱 실패', err);
      return {};
    }
  }

  function chipHtml(field, preset) {
    return (
      '<span class="badge bg-light text-dark border d-inline-flex align-items-center gap-1 spec-preset-chip" ' +
      'data-preset-id="' + escapeHtml(preset.id) + '" style="padding:.5rem .6rem;font-size:.9rem;">' +
      '<span class="spec-preset-chip-name">' + escapeHtml(preset.name) + '</span>' +
      '<button type="button" class="btn-close btn-close-sm spec-preset-del-btn" ' +
      'aria-label="삭제" title="삭제" style="font-size:.6rem;"></button>' +
      '</span>'
    );
  }

  function renderChips(group, presets) {
    var container = group.querySelector('.spec-preset-chips');
    if (!container) return;
    var field = group.getAttribute('data-spec-field');
    var list = Array.isArray(presets) ? presets : [];
    if (!list.length) {
      container.innerHTML = '<span class="text-muted small">등록된 값이 없습니다. 입력 후 추가하세요.</span>';
      return;
    }
    container.innerHTML = list.map(function (p) { return chipHtml(field, p); }).join('');
  }

  function renderAll(allPresets) {
    document.querySelectorAll('.spec-preset-group').forEach(function (group) {
      var field = group.getAttribute('data-spec-field');
      renderChips(group, allPresets[field] || []);
    });
  }

  function addPreset(group) {
    var field = group.getAttribute('data-spec-field');
    var input = group.querySelector('.spec-preset-input');
    var addBtn = group.querySelector('.spec-preset-add-btn');
    var name = (input && input.value || '').trim();
    if (!name) {
      showToast('값을 입력해주세요.', false);
      return;
    }
    if (addBtn) addBtn.disabled = true;
    fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ field: field, name: name })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.success) {
          var fieldPresets = (data.spec_field_presets && data.spec_field_presets[field]) || [];
          renderChips(group, fieldPresets);
          if (input) { input.value = ''; input.focus(); }
          showToast('프리셋이 추가되었습니다.', true);
        } else {
          showToast((data && data.message) || '추가에 실패했습니다.', false);
        }
      })
      .catch(function (err) {
        console.error('[spec-presets] 추가 오류', err);
        showToast('서버 통신 중 오류가 발생했습니다.', false);
      })
      .finally(function () {
        if (addBtn) addBtn.disabled = false;
      });
  }

  function deletePreset(group, chip) {
    var field = group.getAttribute('data-spec-field');
    var presetId = chip.getAttribute('data-preset-id');
    if (!presetId) return;
    var nameEl = chip.querySelector('.spec-preset-chip-name');
    var name = nameEl ? nameEl.textContent : '';
    if (!confirm('"' + name + '" 프리셋을 삭제하시겠습니까?')) return;
    chip.style.opacity = '0.5';
    fetch(ENDPOINT + '/' + encodeURIComponent(field) + '/' + encodeURIComponent(presetId), {
      method: 'DELETE'
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.success) {
          chip.remove();
          var container = group.querySelector('.spec-preset-chips');
          if (container && !container.querySelector('.spec-preset-chip')) {
            renderChips(group, []);
          }
          showToast('프리셋이 삭제되었습니다.', true);
        } else {
          chip.style.opacity = '1';
          showToast((data && data.message) || '삭제에 실패했습니다.', false);
        }
      })
      .catch(function (err) {
        chip.style.opacity = '1';
        console.error('[spec-presets] 삭제 오류', err);
        showToast('서버 통신 중 오류가 발생했습니다.', false);
      });
  }

  function bind() {
    var root = document.getElementById('specPresetGroups');
    if (!root) return;

    renderAll(parseInitial());

    root.addEventListener('click', function (e) {
      var addBtn = e.target.closest('.spec-preset-add-btn');
      if (addBtn) {
        var grpAdd = addBtn.closest('.spec-preset-group');
        if (grpAdd) addPreset(grpAdd);
        return;
      }
      var delBtn = e.target.closest('.spec-preset-del-btn');
      if (delBtn) {
        var chip = delBtn.closest('.spec-preset-chip');
        var grpDel = delBtn.closest('.spec-preset-group');
        if (chip && grpDel) deletePreset(grpDel, chip);
      }
    });

    root.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      var input = e.target.closest('.spec-preset-input');
      if (!input) return;
      e.preventDefault();
      var grp = input.closest('.spec-preset-group');
      if (grp) addPreset(grp);
    });
  }

  ready(bind);
})();
