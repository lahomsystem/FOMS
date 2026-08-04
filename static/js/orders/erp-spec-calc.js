/**
 * ERP 현장 스펙 피커 (erp-order-shared.js 보조 모듈).
 *
 * 동작은 전적으로 window.ERP_SPEC_PICKER_ENABLED 플래그와 발주사 "라홈"에 게이트된다.
 * 플래그 off 또는 발주사≠라홈 → enhanceItemRow/collectPricing이 호출돼도 즉시 반환(무영향).
 *
 * 2026-08-04: 자동 가격계산(WDC 가격엔진 연동·금액 자동기입·읽기전용 잠금·수동전환 토글)을
 * 전면 제거했다. 항목 금액은 항상 사용자가 직접 입력한다(= 저장 스냅샷 manual_override 고정).
 * 피커(제품/색상/손잡이/내부/옵션 선택 UI)와 저장 스냅샷(structured_data.items[].pricing)의
 * 구조는 유지해 하위 소비자(견적서 렌더 등) 호환을 보존한다.
 *
 * UX 원칙(실측/영업 persona): "기본 1칸 + ▾ 트리거". 각 스펙 칸은 기존 입력 컨트롤
 * (모바일=자동 늘어나는 textarea, 제품명=input)을 그대로 유지해 직접입력·autosize를 보존하고,
 * 우측에 작은 ▾ 트리거 버튼을 붙인다. 트리거 → 검증된 피커(ErpSpecPicker: 단일=드롭다운/바텀시트,
 * 옵션=검색+체크박스 시트)가 열리고, 선택 값을 칸에 써넣은 뒤 input 이벤트를 디스패치한다.
 * (native <datalist>는 모바일에서 열리지 않아 폐기)
 *
 * 책임:
 *  - 제품명 칸: 카탈로그 피커 + 이름→product_id 해석(저장 스냅샷용)
 *    · 제품명에 슬라이딩/피닉스바/푸쉬 포함 시 손잡이 칸 자동 입력(신규 선택 시 1회)
 *  - 색상/손잡이/기타 칸: 스펙 프리셋 단일 피커(+직접입력)
 *  - 내부 칸: 추가옵션 '내부구성' 카테고리 다중 피커(+직접입력, 콤마 표기)
 *  - 옵션 칸: 다중 피커(검색+체크박스) → 콤마로 누적 표기
 *  - 저장 시 항목별 pricing 스냅샷(수동 금액 기준)을 structured_data.items[].pricing으로 수집
 *
 * 성능 가드: 카탈로그는 첫 항목 enhance 시점 lazy-load. 단일 바인딩 가드(G4).
 */
(function () {
  'use strict';

  if (window.__erpSpecCalcBound) return;
  window.__erpSpecCalcBound = true;

  // 단일 피커로 강화할 텍스트 칸(제품명은 별도 처리, 옵션은 다중 피커 처리).
  var PRESET_FIELDS = ['color', 'handle', 'internal', 'misc'];
  var FIELD_LABELS = { color: '색상', handle: '손잡이', internal: '내부', misc: '기타 / 설치위치' };
  var INTERNAL_CATEGORY = '내부구성';            // 내부 칸 데이터 출처(추가옵션 카테고리명)

  var _catalogPromise = null;
  var _productNames = null;   // [name] (trim, 제품명 피커용)
  var _productByName = null;  // Map<normName, product>
  var _presets = null;        // {field: [{id,name}]}
  var _optionList = null;     // [{name, price, category, token}] (추가옵션 평면화)
  var _optionsByCategory = null; // {categoryName: [optionName,...]}
  var _optionLookup = null;   // Map<normToken|normName, optionEntry>

  // ----- lazy 로더 -----
  function _fetchJson(url) {
    return fetch(url, { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); });
  }

  /** 매칭 정규화: 공백 제거 + '›'→'>' 통일 + 소문자. */
  function _norm(s) {
    return String(s == null ? '' : s).replace(/\s+/g, '').replace(/›/g, '>').toLowerCase();
  }

  function _structuredOrdererName(structuredData) {
    var parties = structuredData && structuredData.parties;
    var orderer = parties && parties.orderer;
    if (!orderer) return '';
    if (typeof orderer === 'string') return orderer;
    return orderer.name || orderer.value || '';
  }

  function _currentOrdererName() {
    var direct = document.getElementById('erp-orderer-direct');
    var selectEl = document.getElementById('erp-orderer-select');
    var input = document.getElementById('erp-orderer');
    if (direct && direct.checked && input) return input.value || '';
    if (selectEl) return selectEl.value || '';
    return input ? input.value : '';
  }

  function _isLahomOrderer(structuredData) {
    var ordererName = structuredData ? _structuredOrdererName(structuredData) : _currentOrdererName();
    return String(ordererName || '') === '라홈';
  }

  function _buildOptionIndex(cats) {
    _optionList = [];
    _optionsByCategory = {};
    _optionLookup = new Map();
    cats.forEach(function (cat) {
      var catName = (cat && cat.name) ? String(cat.name) : '';
      var names = [];
      (cat && cat.options ? cat.options : []).forEach(function (o) {
        if (!(o && o.name)) return;
        var entry = {
          name: String(o.name),
          price: Number(o.price) || 0,
          category: catName,
          token: (catName ? catName + ' > ' : '') + o.name
        };
        _optionList.push(entry);
        names.push(entry.name);
        _optionLookup.set(_norm(entry.token), entry);
        var nk = _norm(entry.name);
        if (!_optionLookup.has(nk)) _optionLookup.set(nk, entry); // 이름 단독 매칭(첫 항목 우선)
      });
      if (catName) _optionsByCategory[catName] = names;
    });
  }

  function _buildProductIndex(products) {
    _productNames = [];
    _productByName = new Map();
    (products || []).forEach(function (p) {
      var nm = String((p && p.name) || '').trim();
      if (!nm) return;
      _productNames.push(nm);
      var k = _norm(nm);
      if (!_productByName.has(k)) _productByName.set(k, p);
    });
    _productNames.sort(function (a, b) { return a < b ? -1 : (a > b ? 1 : 0); });
  }

  function _ensureCatalog() {
    if (_catalogPromise) return _catalogPromise;
    _catalogPromise = Promise.all([
      _fetchJson('/api/wdcalculator/products').then(function (d) {
        _buildProductIndex((d && d.success && Array.isArray(d.products)) ? d.products : []);
      }).catch(function () { _buildProductIndex([]); }),
      _fetchJson('/api/wdcalculator/spec-field-presets').then(function (d) {
        _presets = (d && d.success && d.spec_field_presets) ? d.spec_field_presets : {};
      }).catch(function () { _presets = {}; }),
      _fetchJson('/api/wdcalculator/additional-options/categories').then(function (d) {
        _buildOptionIndex((d && d.success && Array.isArray(d.categories)) ? d.categories : []);
      }).catch(function () { _buildOptionIndex([]); })
    ]);
    return _catalogPromise;
  }

  // ----- 유틸 -----
  function _findProductByName(name) {
    if (!_productByName) return null;
    return _productByName.get(_norm(name)) || null;
  }

  /** 복합 W 표기에서 계산폭(mm)을 산출: 모든 숫자 토큰을 합산(괄호 내부는 분해의 일부로 보고 제외). */
  function _computeWidthMm(row) {
    var firstW = row.querySelector('.erp-spec-row [data-erp="spec_width"]');
    var raw = firstW ? String(firstW.value || '').trim() : '';
    if (!raw) return 0;
    // 괄호 안 분해 표기(예: 5700(2402+1864+1638))는 앞 총폭이 합과 같으므로 괄호 부분 제거 후 합산
    var stripped = raw.replace(/\([^)]*\)/g, ' ');
    var tokens = stripped.match(/\d+(?:\.\d+)?/g);
    if (!tokens || !tokens.length) return 0;
    var sum = 0;
    for (var i = 0; i < tokens.length; i++) sum += Number(tokens[i]) || 0;
    return Math.round(sum);
  }

  // ----- DOM 강화(▾ 트리거 + 피커) -----
  /**
   * 기존 입력 컨트롤(textarea/input)을 보존한 채 우측에 ▾ 트리거 버튼을 붙인다.
   * 컨트롤을 .erp-calc-field 래퍼로 감싸 트리거를 우상단에 절대배치 → textarea가
   * 늘어나도 트리거 위치는 고정. onOpen(anchorEl)에서 ErpSpecPicker를 연다.
   */
  function _attachTrigger(control, label, onOpen) {
    if (!control || control.dataset.erpCalcTrigger === '1') return;
    control.dataset.erpCalcTrigger = '1';
    control.classList.add('erp-calc-has-trigger');
    var wrap = document.createElement('div');
    wrap.className = 'erp-calc-field';
    control.parentNode.insertBefore(wrap, control);
    wrap.appendChild(control);
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'erp-calc-trigger';
    btn.tabIndex = -1;
    btn.setAttribute('aria-label', label + ' 목록 열기');
    btn.innerHTML = '<span aria-hidden="true">▾</span>';
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      onOpen(wrap);
    });
    wrap.appendChild(btn);
  }

  function _enhanceProductField(row) {
    var input = row.querySelector('[data-erp="product_name"]'); // 제품명은 항상 input
    if (input) _attachTrigger(input, '제품명', function (anchor) { _openProductPicker(row, anchor); });
  }

  function _enhancePresetFields(row) {
    PRESET_FIELDS.forEach(function (field) {
      var ctrl = row.querySelector('[data-erp="' + field + '"]');
      if (ctrl) _attachTrigger(ctrl, FIELD_LABELS[field] || field, function (anchor) { _openPresetPicker(row, field, anchor); });
    });
  }

  function _enhanceOptionField(row) {
    var ctrl = row.querySelector('[data-erp="option_detail"]');
    if (ctrl) _attachTrigger(ctrl, '옵션', function (anchor) { _openOptionPicker(row, anchor); });
  }

  // ----- 카탈로그 로드 후 행 동기화 -----
  function _presetNames(field) {
    var list = (_presets && Array.isArray(_presets[field])) ? _presets[field] : [];
    return list.map(function (p) { return p && p.name; }).filter(Boolean);
  }

  /** 단일 피커용 항목 변환: 값/표시 동일한 평면 목록. */
  function _singleItems(values) {
    return (values || []).filter(function (v) { return v != null && v !== ''; })
      .map(function (v) { return { value: String(v), text: String(v) }; });
  }

  /** 옵션 다중 피커용 그룹: _optionList를 카테고리별로 묶고 토큰을 key로 사용. */
  function _buildOptionGroups() {
    var byCat = {};
    var order = [];
    (_optionList || []).forEach(function (e) {
      var c = e.category || '기타';
      if (!byCat[c]) { byCat[c] = []; order.push(c); }
      byCat[c].push({
        key: e.token,
        label: e.name,
        meta: e.price > 0 ? (e.price.toLocaleString() + '원') : '',
        payload: e
      });
    });
    return order.map(function (c) { return { label: c, items: byCat[c] }; });
  }

  /** 특정 추가옵션 카테고리를 다중 피커 그룹으로 변환한다(내부구성 전용). */
  function _buildCategoryOptionGroups(categoryName) {
    var items = [];
    (_optionList || []).forEach(function (e) {
      if (!e || e.category !== categoryName) return;
      items.push({
        key: e.token,
        label: e.name,
        meta: e.price > 0 ? (e.price.toLocaleString() + '원') : '',
        payload: e
      });
    });
    return [{ label: categoryName, items: items }];
  }

  /** 현재 옵션 칸 텍스트에서 카탈로그와 매칭되는 토큰(피커 사전선택 key)을 추출. */
  function _currentOptionKeys(ctrl) {
    var keys = [];
    if (!ctrl || !_optionLookup) return keys;
    String(ctrl.value || '').split(',').forEach(function (tok) {
      var t = tok.trim();
      if (!t) return;
      var e = _optionLookup.get(_norm(t));
      if (e && keys.indexOf(e.token) === -1) keys.push(e.token);
    });
    return keys;
  }

  /** 현재 카테고리 필드 텍스트에서 카탈로그와 매칭되는 토큰(피커 사전선택 key)을 추출. */
  function _currentCategoryOptionKeys(ctrl, categoryName) {
    var keys = [];
    if (!ctrl) return keys;
    String(ctrl.value || '').split(',').forEach(function (tok) {
      var t = tok.trim();
      if (!t) return;
      var e = _findOptionInCategory(t, categoryName);
      if (e && keys.indexOf(e.token) === -1) keys.push(e.token);
    });
    return keys;
  }

  function _populateRow(row) {
    _resolveProduct(row, false);   // 로드 시: 저장된 제품명 → product_id 확정(손잡이 자동입력 금지)
    _onOptionTextChange(row);      // 로드 시: 콤마 텍스트 → option_rows 재구성
  }

  // ----- 이벤트 -----
  function _setTextControl(ctrl, value) {
    if (!ctrl) return;
    ctrl.value = value;
    ctrl.dispatchEvent(new Event('input', { bubbles: true }));
  }

  /** 제품명에 따라 손잡이 자동 입력(슬라이딩 > 피닉스바 > 푸쉬). 미해당이면 손잡이 보존. */
  function _autoFillHandle(row, product) {
    var name = String((product && product.name) || '');
    var handle = '';
    if (name.indexOf('슬라이딩') >= 0) handle = '슬라이딩';
    else if (name.indexOf('피닉스바') >= 0) handle = '피닉스바';
    else if (name.indexOf('푸쉬') >= 0) handle = '푸쉬';
    if (!handle) return;
    var hInput = row.querySelector('[data-erp="handle"]');
    if (hInput) _setTextControl(hInput, handle);
  }

  /** 제품명 텍스트 → product_id/enabled 해석(저장 스냅샷용). allowHandleFill=true이고 제품이 새로 바뀌면 손잡이 자동입력. */
  function _resolveProduct(row, allowHandleFill) {
    var st = row.__erpPricing;
    if (!st) return;
    var input = row.querySelector('[data-erp="product_name"]');
    var name = input ? String(input.value || '').trim() : '';
    var prod = name ? _findProductByName(name) : null;
    var prevId = st.product_id;
    if (prod) {
      var newId = Number(prod.id);
      if (prevId !== newId && allowHandleFill) _autoFillHandle(row, prod);
      st.product_id = newId;
      st.enabled = true;
    } else {
      st.product_id = null;
      st.enabled = false;
    }
  }

  function _parseOptionRows(text) {
    var rows = [];
    if (!_optionLookup) return rows;
    String(text || '').split(',').forEach(function (tok) {
      var t = tok.trim();
      if (!t) return;
      var e = _optionLookup.get(_norm(t));
      if (e && e.price >= 0) rows.push({ name: e.token, price: e.price, quantity: 1 });
    });
    return rows;
  }

  function _optionTokenCounts(text, finder) {
    var counts = new Map();
    String(text || '').split(',').forEach(function (tok) {
      var t = tok.trim();
      if (!t || t === '상담') return;
      var e = finder(t);
      if (!e) return;
      counts.set(e.token, (counts.get(e.token) || 0) + 1);
    });
    return counts;
  }

  function _findOptionInCategory(value, categoryName) {
    var needle = _norm(value);
    if (!needle || !_optionList) return null;
    for (var i = 0; i < _optionList.length; i += 1) {
      var e = _optionList[i];
      if (!e || e.category !== categoryName) continue;
      if (_norm(e.name) === needle || _norm(e.token) === needle) return e;
    }
    return null;
  }

  function _parseCategoryOptionRows(row, field, categoryName) {
    var ctrl = row.querySelector('[data-erp="' + field + '"]');
    var rows = [];
    if (!ctrl) return rows;
    String(ctrl.value || '').split(',').forEach(function (tok) {
      var t = tok.trim();
      if (!t || t === '상담') return;
      var e = _findOptionInCategory(t, categoryName);
      if (e && e.price >= 0) rows.push({ name: e.token, price: e.price, quantity: 1 });
    });
    return rows;
  }

  function _aggregateOptionRows(rows) {
    var byName = new Map();
    (rows || []).forEach(function (row) {
      if (!row || !row.name) return;
      var qty = Number(row.quantity) || 1;
      if (byName.has(row.name)) {
        byName.get(row.name).quantity += qty;
        return;
      }
      byName.set(row.name, { name: row.name, price: row.price, quantity: qty });
    });
    return Array.from(byName.values());
  }

  function _syncOptionRows(row) {
    var st = row.__erpPricing;
    if (!st) return;
    var ctrl = row.querySelector('[data-erp="option_detail"]');
    st.option_rows = _aggregateOptionRows(
      _parseCategoryOptionRows(row, 'internal', INTERNAL_CATEGORY)
        .concat(_parseOptionRows(ctrl ? ctrl.value : ''))
    );
  }

  function _onOptionTextChange(row) {
    _syncOptionRows(row);
  }

  /**
   * 다중 피커 확인 → 옵션 칸 재구성. 카탈로그 옵션은 피커가 SSOT로 관리(체크/해제),
   * 카탈로그에 없는 자유 입력 토큰은 보존. 기본 placeholder '상담'은 제거.
   */
  function _applyOptionSelection(row, ctrl, payloads) {
    if (!ctrl) return;
    var current = String(ctrl.value || '').trim();
    var tokens = current ? current.split(',').map(function (s) { return s.trim(); }).filter(Boolean) : [];
    var counts = _optionTokenCounts(current, function (t) {
      return _optionLookup ? _optionLookup.get(_norm(t)) : null;
    });
    var freeTokens = tokens.filter(function (t) {
      if (t === '상담') return false;
      return !_optionLookup || !_optionLookup.has(_norm(t));
    });
    var combined = [];
    freeTokens.forEach(function (t) {
      if (t) combined.push(t);
    });
    (payloads || []).forEach(function (p) {
      var n = counts.get(p.token) || 1;
      for (var i = 0; i < n; i += 1) combined.push(p.token);
    });
    ctrl.value = combined.join(', ');
    ctrl.dispatchEvent(new Event('input', { bubbles: true }));
    _onOptionTextChange(row);
  }

  /**
   * 내부 다중 피커 확인 → 내부 칸 재구성. 화면에는 카테고리 없는 이름만 남기고,
   * 저장 시에는 _syncOptionRows가 내부구성 토큰으로 변환해 스냅샷에 담는다.
   */
  function _applyCategoryOptionSelection(row, ctrl, categoryName, payloads) {
    if (!ctrl) return;
    var current = String(ctrl.value || '').trim();
    var tokens = current ? current.split(',').map(function (s) { return s.trim(); }).filter(Boolean) : [];
    var counts = _optionTokenCounts(current, function (t) {
      return _findOptionInCategory(t, categoryName);
    });
    var freeTokens = tokens.filter(function (t) {
      if (t === '상담') return false;
      return !_findOptionInCategory(t, categoryName);
    });
    var combined = [];
    freeTokens.forEach(function (t) {
      if (t) combined.push(t);
    });
    (payloads || []).forEach(function (p) {
      var n = counts.get(p.token) || 1;
      for (var i = 0; i < n; i += 1) combined.push(p.name);
    });
    ctrl.value = combined.join(', ');
    ctrl.dispatchEvent(new Event('input', { bubbles: true }));
    _syncOptionRows(row);
  }

  // ----- 피커 오픈 핸들러(카탈로그 준비 보장 후 ErpSpecPicker 호출) -----
  function _openProductPicker(row, anchor) {
    if (!window.ErpSpecPicker) return;
    _ensureCatalog().then(function () {
      var input = row.querySelector('[data-erp="product_name"]');
      window.ErpSpecPicker.openSingle({
        title: '제품 선택',
        anchor: anchor,
        current: input ? input.value : '',
        topItems: _singleItems(_productNames || []),
        onPick: function (value) { _setTextControl(input, value); } // input 리스너가 제품 해석/손잡이 자동
      });
    });
  }

  function _openPresetPicker(row, field, anchor) {
    if (!window.ErpSpecPicker) return;
    _ensureCatalog().then(function () {
      var ctrl = row.querySelector('[data-erp="' + field + '"]');
      if (field === 'internal') {
        window.ErpSpecPicker.openMulti({
          title: '내부 선택',
          groups: _buildCategoryOptionGroups(INTERNAL_CATEGORY),
          selectedKeys: _currentCategoryOptionKeys(ctrl, INTERNAL_CATEGORY),
          onConfirm: function (payloads) { _applyCategoryOptionSelection(row, ctrl, INTERNAL_CATEGORY, payloads); }
        });
        return;
      }
      var values = _presetNames(field);
      window.ErpSpecPicker.openSingle({
        title: (FIELD_LABELS[field] || field) + ' 선택',
        anchor: anchor,
        current: ctrl ? ctrl.value : '',
        topItems: _singleItems(values),
        onPick: function (value) { _setTextControl(ctrl, value); }
      });
    });
  }

  function _openOptionPicker(row, anchor) {
    if (!window.ErpSpecPicker) return;
    _ensureCatalog().then(function () {
      var ctrl = row.querySelector('[data-erp="option_detail"]');
      window.ErpSpecPicker.openMulti({
        title: '옵션 선택',
        anchor: anchor,
        groups: _buildOptionGroups(),
        selectedKeys: _currentOptionKeys(ctrl),
        onConfirm: function (payloads) { _applyOptionSelection(row, ctrl, payloads); }
      });
    });
  }

  function _manualPriceFromRow(row) {
    var priceInput = row.querySelector('[data-erp="price"]');
    if (!priceInput) return 0;
    var digits = String(priceInput.value || '').replace(/[^0-9]/g, '');
    return digits ? parseInt(digits, 10) : 0;
  }

  function _bindRow(row) {
    // 위임: 내부/옵션 텍스트 직접편집 → 스냅샷 option_rows 재파싱
    row.addEventListener('input', function (e) {
      var t = e.target;
      if (!t || !t.matches) return;
      if (t.matches('[data-erp="internal"]')) _syncOptionRows(row);
      else if (t.matches('[data-erp="option_detail"]')) _onOptionTextChange(row);
    });
    var pInput = row.querySelector('[data-erp="product_name"]');
    if (pInput) {
      // 직접 타이핑 또는 피커 선택 모두 input 이벤트로 들어옴 → 즉시 해석(손잡이 자동입력 허용)
      pInput.addEventListener('input', function () { _resolveProduct(row, true); });
      pInput.addEventListener('change', function () { _resolveProduct(row, true); });
    }
  }

  // ----- 공개 API -----
  var ErpSpecCalc = {
    enhanceItemRow: function (row, item) {
      if (!window.ERP_SPEC_PICKER_ENABLED || !_isLahomOrderer()) return;
      if (!row || row.dataset.erpCalcEnhanced === '1') return;
      row.dataset.erpCalcEnhanced = '1';
      var pricing = (item && item.pricing && typeof item.pricing === 'object') ? item.pricing : null;
      row.__erpPricing = {
        enabled: pricing ? pricing.enabled !== false && !!pricing.product_id : false,
        product_id: pricing ? (pricing.product_id || null) : null,
        option_rows: (pricing && Array.isArray(pricing.option_rows)) ? pricing.option_rows : []
      };
      _enhanceProductField(row);
      _enhancePresetFields(row);
      _enhanceOptionField(row);
      _bindRow(row);
      _ensureCatalog().then(function () {
        _populateRow(row);
      }).catch(function (e) {
        console.warn('[erp-spec-calc] 카탈로그 로드 실패(직접입력만 가능)', e);
      });
    },

    /** 저장 스냅샷 수집: 금액은 항상 수동 입력이므로 manual_override 고정 + computed=수동 금액. */
    collectPricing: function (row, obj) {
      if (!window.ERP_SPEC_PICKER_ENABLED || !_isLahomOrderer()) return;
      var st = row && row.__erpPricing;
      if (!st || !st.enabled || !st.product_id) return; // 레거시/직접입력 항목은 pricing 미첨부
      var manualPrice = _manualPriceFromRow(row);
      var widthMm = _computeWidthMm(row);
      obj.pricing = {
        enabled: true,
        product_id: st.product_id,
        width_mm: widthMm,
        base_components: [{
          mode: 'select', productId: st.product_id, widthMm: widthMm,
          widthInput: String(widthMm), additionalFees: []
        }],
        option_rows: st.option_rows || [],
        coupon_value: 0,
        manual_override: true,
        computed: {
          base_price: manualPrice,
          additional_price: 0,
          total_price: manualPrice,
          final_price: manualPrice
        },
        source: 'erp_spec_calc',
        computed_at: new Date().toISOString()
      };
    },

    refreshForOrderer: function (root) {
      _enhanceExistingRows(root || document);
    }
  };

  window.ErpSpecCalc = ErpSpecCalc;

  function _enhanceExistingRows(root) {
    if (!window.ERP_SPEC_PICKER_ENABLED) return;
    var scope = (root && typeof root.querySelectorAll === 'function') ? root : document;
    var rows = scope.querySelectorAll('#erp-items .erp-item-row');
    rows.forEach(function (row) {
      if (_isLahomOrderer() && !row.__erpPricing) {
        ErpSpecCalc.enhanceItemRow(row, {});
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { _enhanceExistingRows(document); });
  } else {
    setTimeout(function () { _enhanceExistingRows(document); }, 0);
  }
  document.addEventListener('foms:main-content-swapped', function () {
    setTimeout(function () { _enhanceExistingRows(document); }, 0);
  });
})();
