/**
 * ERP 현장 스펙 즉시견적 (erp-order-shared.js 보조 모듈).
 *
 * 동작은 전적으로 window.ERP_SPEC_CALC_ENABLED 플래그에 게이트된다.
 * 플래그 off → enhanceItemRow/collectPricing이 호출돼도 즉시 반환(무영향).
 *
 * UX 원칙(실측/영업 persona): "기본 1칸 + ▾ 트리거". 각 스펙 칸은 기존 입력 컨트롤
 * (모바일=자동 늘어나는 textarea, 제품명=input)을 그대로 유지해 직접입력·autosize를 보존하고,
 * 우측에 작은 ▾ 트리거 버튼을 붙인다. 트리거 → 검증된 피커(ErpSpecPicker: 단일=드롭다운/바텀시트,
 * 옵션=검색+체크박스 시트)가 열리고, 선택 값을 칸에 써넣은 뒤 input 이벤트를 디스패치 →
 * 기존 계산/해석 로직이 그대로 동작. (native <datalist>는 모바일에서 열리지 않아 폐기)
 *
 * 책임:
 *  - 제품명 칸: 카탈로그 피커 + 이름→product_id 해석 → 즉시 가격계산
 *    · 제품명에 슬라이딩/피닉스바/푸쉬 포함 시 손잡이 칸 자동 입력(신규 선택 시 1회)
 *  - 색상/손잡이/기타 칸: 스펙 프리셋 단일 피커(+직접입력)
 *  - 내부 칸: 추가옵션 '내부구성' 카테고리 다중 피커(+직접입력, 콤마 표기)
 *  - 옵션 칸: 다중 피커(검색+체크박스) → 콤마로 누적 표기 + 가격 합산
 *  - 제품+계산폭(복합 W 자동합산)으로 WDC 가격엔진(pricing-core.js) 즉시 계산
 *  - 계산 활성 항목의 금액은 기본 읽기전용(수동전환 토글 제공)
 *  - 저장 시 항목별 pricing 스냅샷을 structured_data.items[].pricing으로 수집
 *
 * 성능 가드: 가격엔진/카탈로그는 첫 항목 enhance 시점 lazy-load. 단일 바인딩 가드(G4).
 */
(function () {
  'use strict';

  if (window.__erpSpecCalcBound) return;
  window.__erpSpecCalcBound = true;

  // 단일 피커로 강화할 텍스트 칸(제품명은 별도 처리, 옵션은 다중 피커 처리).
  var PRESET_FIELDS = ['color', 'handle', 'internal', 'misc'];
  var FIELD_LABELS = { color: '색상', handle: '손잡이', internal: '내부', misc: '기타 / 설치위치' };
  var INTERNAL_CATEGORY = '내부구성';            // 내부 칸 데이터 출처(추가옵션 카테고리명)
  var PRICING_ENGINE_SRC = '/static/js/wdcalculator/pricing-core.js';

  var _enginePromise = null;
  var _catalogPromise = null;
  var _products = null;       // 제품 카탈로그(엔진 입력 원본 유지)
  var _productNames = null;   // [name] (trim, 제품명 datalist용)
  var _productByName = null;  // Map<normName, product>
  var _presets = null;        // {field: [{id,name}]}
  var _optionList = null;     // [{name, price, category, token}] (추가옵션 평면화)
  var _optionsByCategory = null; // {categoryName: [optionName,...]}
  var _optionLookup = null;   // Map<normToken|normName, optionEntry>

  // ----- lazy 로더 -----
  function _ensureEngine() {
    if (typeof window.wdcComputeCurrentEstimateMath === 'function') {
      return Promise.resolve(true);
    }
    if (_enginePromise) return _enginePromise;
    _enginePromise = new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[data-erp-pricing-engine="1"]');
      if (existing) {
        existing.addEventListener('load', function () { resolve(true); });
        existing.addEventListener('error', reject);
        return;
      }
      var s = document.createElement('script');
      s.src = PRICING_ENGINE_SRC;
      s.async = true;
      s.setAttribute('data-erp-pricing-engine', '1');
      s.onload = function () { resolve(true); };
      s.onerror = function () { reject(new Error('pricing-core.js 로드 실패')); };
      document.head.appendChild(s);
    });
    return _enginePromise;
  }

  function _fetchJson(url) {
    return fetch(url, { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); });
  }

  /** 매칭 정규화: 공백 제거 + '›'→'>' 통일 + 소문자. */
  function _norm(s) {
    return String(s == null ? '' : s).replace(/\s+/g, '').replace(/›/g, '>').toLowerCase();
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
    _products = products || [];
    _productNames = [];
    _productByName = new Map();
    _products.forEach(function (p) {
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
      _ensureEngine(),
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
  function _findProduct(productId) {
    if (!_products || productId == null) return null;
    var pid = Number(productId);
    for (var i = 0; i < _products.length; i++) {
      if (_products[i] && Number(_products[i].id) === pid) return _products[i];
    }
    return null;
  }

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

  function _escape(text) {
    var div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
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
    btn.innerHTML = '<span aria-hidden="true">\u25be</span>';
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

  function _injectPriceMeta(row) {
    var priceInput = row.querySelector('[data-erp="price"]');
    if (!priceInput || row.querySelector('.erp-calc-price-meta')) return;
    var meta = document.createElement('div');
    meta.className = 'erp-calc-price-meta small mt-1 d-flex flex-wrap gap-2 align-items-center';
    meta.innerHTML =
      '<span class="erp-calc-width-label text-muted"></span>' +
      '<span class="erp-calc-price-label text-success fw-semibold"></span>' +
      '<a href="#" class="erp-calc-unlock-link text-decoration-none" style="display:none;">수동 금액으로 전환</a>';
    priceInput.parentNode.appendChild(meta);
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
    _recalc(row);
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

  /** 제품명 텍스트 → product_id/enabled 해석. allowHandleFill=true이고 제품이 새로 바뀌면 손잡이 자동입력. */
  function _resolveProduct(row, allowHandleFill) {
    var st = row.__erpPricing;
    if (!st) return;
    var input = row.querySelector('[data-erp="product_name"]');
    var name = input ? String(input.value || '').trim() : '';
    var prod = name ? _findProductByName(name) : null;
    var prevId = st.product_id;
    if (prod) {
      st.product_id = Number(prod.id);
      st.enabled = true;
      if (prevId !== st.product_id) {
        st.manual_override = false; // 새 제품 선택 → 자동계산 복귀
        if (allowHandleFill) _autoFillHandle(row, prod);
      }
    } else {
      st.product_id = null;
      st.enabled = false;
    }
    _recalc(row);
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

  function _dedupeOptionRows(rows) {
    var seen = {};
    return (rows || []).filter(function (row) {
      var key = row && row.name;
      if (!key || seen[key]) return false;
      seen[key] = true;
      return true;
    });
  }

  function _syncOptionRows(row) {
    var st = row.__erpPricing;
    if (!st) return;
    var ctrl = row.querySelector('[data-erp="option_detail"]');
    st.option_rows = _dedupeOptionRows(
      _parseCategoryOptionRows(row, 'internal', INTERNAL_CATEGORY)
        .concat(_parseOptionRows(ctrl ? ctrl.value : ''))
    );
    _recalc(row);
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
    var freeTokens = tokens.filter(function (t) {
      if (t === '상담') return false;
      return !_optionLookup || !_optionLookup.has(_norm(t));
    });
    var combined = [];
    freeTokens.concat((payloads || []).map(function (p) { return p.token; })).forEach(function (t) {
      if (t && combined.indexOf(t) === -1) combined.push(t);
    });
    ctrl.value = combined.join(', ');
    ctrl.dispatchEvent(new Event('input', { bubbles: true }));
    _onOptionTextChange(row);
  }

  /**
   * 내부 다중 피커 확인 → 내부 칸 재구성. 화면에는 카테고리 없는 이름만 남기고,
   * 계산 시에는 _syncOptionRows가 내부구성 토큰으로 변환해 가격엔진에 전달한다.
   */
  function _applyCategoryOptionSelection(row, ctrl, categoryName, payloads) {
    if (!ctrl) return;
    var current = String(ctrl.value || '').trim();
    var tokens = current ? current.split(',').map(function (s) { return s.trim(); }).filter(Boolean) : [];
    var freeTokens = tokens.filter(function (t) {
      if (t === '상담') return false;
      return !_findOptionInCategory(t, categoryName);
    });
    var combined = [];
    freeTokens.concat((payloads || []).map(function (p) { return p.name; })).forEach(function (t) {
      if (t && combined.indexOf(t) === -1) combined.push(t);
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

  /** 단일 권위: enabled+제품+폭>0+자동모드일 때만 금액 읽기전용 잠금 + 토글 노출. */
  function _applyPriceLockState(row) {
    var st = row.__erpPricing;
    var priceInput = row.querySelector('[data-erp="price"]');
    var unlock = row.querySelector('.erp-calc-unlock-link');
    var lock = !!(st.enabled && st.product_id && !st.manual_override && st.width_mm > 0);
    if (priceInput) priceInput.readOnly = lock;
    if (unlock) unlock.style.display = lock ? '' : 'none';
    return lock;
  }

  function _toggleManual(row) {
    var st = row.__erpPricing;
    st.manual_override = true;
    _applyPriceLockState(row);
    var priceInput = row.querySelector('[data-erp="price"]');
    if (priceInput) priceInput.focus();
  }

  function _recalc(row) {
    var st = row.__erpPricing;
    if (!st) return;
    var widthMm = _computeWidthMm(row);
    st.width_mm = widthMm;
    var widthLabel = row.querySelector('.erp-calc-width-label');
    var priceLabel = row.querySelector('.erp-calc-price-label');
    if (widthLabel) widthLabel.textContent = widthMm > 0 ? ('계산폭 ' + widthMm.toLocaleString() + 'mm') : '';

    // 계산 비활성/제품 미선택 → 금액은 사용자 수동 입력 유지(잠금 해제)
    if (!st.enabled || !st.product_id) {
      if (priceLabel) priceLabel.textContent = '';
      _applyPriceLockState(row);
      return;
    }
    if (typeof window.wdcComputeCurrentEstimateMath !== 'function' || !_products) {
      if (priceLabel) priceLabel.textContent = '';
      _applyPriceLockState(row);
      return;
    }
    var prod = _findProduct(st.product_id);
    if (!prod) {
      // 카탈로그에서 삭제된 제품 → 수동 금액 유지(덮어쓰지 않음)
      if (priceLabel) priceLabel.textContent = '제품 정보 없음(수동 금액 유지)';
      st.manual_override = true;
      _applyPriceLockState(row);
      return;
    }
    // 폭 미입력 → 0원으로 덮어쓰지 않고 입력 대기(수동 금액 보존)
    if (widthMm <= 0) {
      if (priceLabel) priceLabel.textContent = '계산폭 입력 대기';
      _applyPriceLockState(row);
      return;
    }
    try {
      var base = [{ mode: 'select', productId: st.product_id, widthMm: widthMm, widthInput: String(widthMm), additionalFees: [] }];
      var res = window.wdcComputeCurrentEstimateMath(base, _products, st.option_rows || []);
      var finalPrice = Math.round(res.totalPriceCalculate || 0);
      st.computed = {
        base_price: Math.round(res.basePriceCalculate || 0),
        additional_price: Math.round(res.additionalPrice || 0),
        total_price: finalPrice,
        final_price: finalPrice
      };
      if (priceLabel) priceLabel.textContent = '자동계산 ' + finalPrice.toLocaleString() + '원';
      var lock = _applyPriceLockState(row);
      if (lock) {
        var priceInput = row.querySelector('[data-erp="price"]');
        if (priceInput) {
          priceInput.value = String(finalPrice);
          priceInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
      }
    } catch (e) {
      console.warn('[erp-spec-calc] 계산 실패', e);
    }
  }

  function _bindRow(row) {
    // 위임: 폭 입력→재계산, 옵션 텍스트 직접편집→재파싱
    row.addEventListener('input', function (e) {
      var t = e.target;
      if (!t || !t.matches) return;
      if (t.matches('[data-erp="spec_width"]')) _recalc(row);
      else if (t.matches('[data-erp="internal"]')) _syncOptionRows(row);
      else if (t.matches('[data-erp="option_detail"]')) _onOptionTextChange(row);
    });
    var pInput = row.querySelector('[data-erp="product_name"]');
    if (pInput) {
      // 직접 타이핑 또는 피커 선택 모두 input 이벤트로 들어옴 → 즉시 해석(손잡이 자동입력 허용)
      pInput.addEventListener('input', function () { _resolveProduct(row, true); });
      pInput.addEventListener('change', function () { _resolveProduct(row, true); });
    }
    var unlock = row.querySelector('.erp-calc-unlock-link');
    if (unlock) unlock.addEventListener('click', function (e) { e.preventDefault(); _toggleManual(row); });
  }

  // ----- 공개 API -----
  var ErpSpecCalc = {
    enhanceItemRow: function (row, item) {
      if (!window.ERP_SPEC_CALC_ENABLED) return;
      if (!row || row.dataset.erpCalcEnhanced === '1') return;
      row.dataset.erpCalcEnhanced = '1';
      var pricing = (item && item.pricing && typeof item.pricing === 'object') ? item.pricing : null;
      row.__erpPricing = {
        enabled: pricing ? pricing.enabled !== false && !!pricing.product_id : false,
        product_id: pricing ? (pricing.product_id || null) : null,
        width_mm: pricing ? (Number(pricing.width_mm) || 0) : 0,
        option_rows: (pricing && Array.isArray(pricing.option_rows)) ? pricing.option_rows : [],
        manual_override: false,
        computed: (pricing && pricing.computed) ? pricing.computed : null
      };
      _enhanceProductField(row);
      _enhancePresetFields(row);
      _enhanceOptionField(row);
      _injectPriceMeta(row);
      _bindRow(row);
      _ensureCatalog().then(function () {
        _populateRow(row);
      }).catch(function (e) {
        console.warn('[erp-spec-calc] 카탈로그 로드 실패(직접입력만 가능)', e);
      });
    },

    collectPricing: function (row, obj) {
      if (!window.ERP_SPEC_CALC_ENABLED) return;
      var st = row && row.__erpPricing;
      if (!st || !st.enabled || !st.product_id) return; // 레거시/직접입력 항목은 pricing 미첨부
      obj.pricing = {
        enabled: true,
        product_id: st.product_id,
        width_mm: st.width_mm || 0,
        base_components: [{
          mode: 'select', productId: st.product_id, widthMm: st.width_mm || 0,
          widthInput: String(st.width_mm || 0), additionalFees: []
        }],
        option_rows: st.option_rows || [],
        coupon_value: 0,
        computed: st.computed || null,
        source: 'erp_spec_calc',
        computed_at: new Date().toISOString()
      };
    },

    /** ERP 항목 pricing → WDC estimate_data(견적서 렌더 가능한 표준 형태). 계산 항목 없으면 null. */
    buildEstimateData: function (structuredData) {
      var items = (structuredData && Array.isArray(structuredData.items)) ? structuredData.items : [];
      var estimates = [];
      var totalBase = 0, totalAdd = 0, totalPrice = 0;
      items.forEach(function (it) {
        var p = it && it.pricing;
        if (!p || p.enabled === false || !p.product_id) return;
        var c = p.computed || {};
        var base = Number(c.base_price) || 0;
        var add = Number(c.additional_price) || 0;
        var total = Number(c.total_price != null ? c.total_price : (base + add)) || 0;
        totalBase += base; totalAdd += add; totalPrice += total;
        estimates.push({
          productId: p.product_id,
          productName: (it.product_name || '기본 구성'),
          displayName: (it.product_name || '기본 구성'),
          widthMm: Number(p.width_mm) || 0,
          basePrice: base,
          options: Array.isArray(p.option_rows) ? p.option_rows : [],
          additionalPrice: add,
          totalPrice: total,
          baseComponents: Array.isArray(p.base_components) ? p.base_components : [],
          notes: (it.extra_input || '')
        });
      });
      if (!estimates.length) return null;
      return {
        estimates: estimates,
        totalBasePrice: totalBase,
        totalAdditionalPrice: totalAdd,
        totalPrice: totalPrice,
        coupon_discount: 0,
        shipping_cost: 0,
        shipping_included: true,
        notes: (structuredData && structuredData.notes && structuredData.notes.measurement_note) || '',
        source: 'erp_spec_calc'
      };
    },

    /**
     * ERP 주문 저장 성공 직후 호출 → WDC 견적 upsert + 자동매칭(서버 원자처리).
     * 계산 항목이 없으면 동기화 생략. 실패는 저장 결과에 영향 없음(fail-open).
     * 성공 시 estimate_id를 structured_data.meta에 반영해 다음 저장이 upsert되게 한다.
     */
    syncEstimate: function (orderId, structuredData) {
      if (!window.ERP_SPEC_CALC_ENABLED || !orderId) return Promise.resolve(null);
      var estimateData = this.buildEstimateData(structuredData);
      if (!estimateData) return Promise.resolve(null);
      var meta = (structuredData && structuredData.meta && typeof structuredData.meta === 'object')
        ? structuredData.meta : {};
      var customer = (structuredData && structuredData.parties && structuredData.parties.customer
        && structuredData.parties.customer.name) || '';
      var body = { customer_name: customer, estimate_data: estimateData };
      if (meta.wdc_estimate_id) body.estimate_id = meta.wdc_estimate_id;
      return fetch('/api/orders/' + orderId + '/wdc-estimate-sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      }).then(function (r) { return r.json(); }).then(function (data) {
        if (data && data.success && data.estimate_id) {
          if (structuredData && typeof structuredData === 'object') {
            if (!structuredData.meta || typeof structuredData.meta !== 'object') structuredData.meta = {};
            structuredData.meta.wdc_estimate_id = data.estimate_id;
          }
          var last = window.__erpLastStructuredData;
          if (last && typeof last === 'object') {
            if (!last.meta || typeof last.meta !== 'object') last.meta = {};
            last.meta.wdc_estimate_id = data.estimate_id;
          }
        }
        return data;
      });
    }
  };

  // _escape: 동적 텍스트를 innerHTML로 합성할 때만 사용(현재는 DOM .value/.textContent 사용).
  ErpSpecCalc._escape = _escape;

  window.ErpSpecCalc = ErpSpecCalc;

  function _enhanceExistingRows(root) {
    if (!window.ERP_SPEC_CALC_ENABLED) return;
    var scope = (root && typeof root.querySelectorAll === 'function') ? root : document;
    var rows = scope.querySelectorAll('#erp-items .erp-item-row');
    rows.forEach(function (row) {
      ErpSpecCalc.enhanceItemRow(row, {});
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
