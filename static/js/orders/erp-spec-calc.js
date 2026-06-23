/**
 * ERP 현장 스펙 즉시견적 (erp-order-shared.js 보조 모듈).
 *
 * 동작은 전적으로 window.ERP_SPEC_CALC_ENABLED 플래그에 게이트된다.
 * 플래그 off → enhanceItemRow/collectPricing이 호출돼도 즉시 반환(무영향).
 *
 * UX 원칙(실측/영업 persona): "기본 1칸". 각 스펙 칸은 별도 드롭다운을 쌓지 않고
 * 기존 입력 칸 자체를 datalist 콤보박스로 강화한다 → 타이핑(직접입력)과 목록 선택이
 * 한 칸에서 모두 가능. 모바일에서 textarea로 렌더된 칸은 강화 시점에만 단일행 input으로
 * 치환한다(플래그 off면 원본 그대로 → 회귀 불가).
 *
 * 책임:
 *  - 제품명 칸: 카탈로그 datalist + 이름→product_id 해석 → 즉시 가격계산
 *    · 제품명에 슬라이딩/피닉스바/푸쉬 포함 시 손잡이 칸 자동 입력(신규 선택 시 1회)
 *  - 색상/손잡이/기타 칸: 스펙 프리셋 datalist(+직접입력)
 *  - 내부 칸: 추가옵션 '내부구성' 카테고리 값 datalist(+직접입력)
 *  - 옵션 칸: '＋ 옵션 추가' adder(다중선택) → 콤마로 누적 표기 + 가격 합산
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

  // datalist 콤보박스로 강화할 텍스트 칸(제품명은 별도 처리, 옵션은 adder 처리).
  var PRESET_FIELDS = ['color', 'handle', 'internal', 'misc'];
  var INTERNAL_CATEGORY = '내부구성';            // 내부 칸 데이터 출처(추가옵션 카테고리명)
  var PRICING_ENGINE_SRC = '/static/js/wdcalculator/pricing-core.js';

  var _uid = 0;               // datalist id 유일성 카운터
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

  // ----- DOM 강화(콤보박스) -----
  /** data-erp 칸을 input으로 보장. 모바일 textarea면 값/속성을 보존해 단일행 input으로 치환. */
  function _ensureInputControl(row, field) {
    var el = row.querySelector('[data-erp="' + field + '"]');
    if (!el) return null;
    if (el.tagName === 'INPUT') return el;
    var input = document.createElement('input');
    input.type = 'text';
    input.setAttribute('data-erp', field);
    input.value = el.value || '';
    if (el.getAttribute('placeholder')) input.setAttribute('placeholder', el.getAttribute('placeholder'));
    input.setAttribute('lang', el.getAttribute('lang') || 'ko');
    // 모바일 단일행 입력 클래스(제품명/금액 칸과 동일 룩) + 강화 식별자
    input.className = 'foms-input erp-calc-converted';
    el.parentNode.replaceChild(input, el);
    return input;
  }

  /** input에 datalist 콤보박스를 부착(빈 datalist 생성). 값은 카탈로그 로드 후 채운다. */
  function _attachDatalist(input, key) {
    if (!input || input.dataset.erpCalcCombo === '1') return;
    input.dataset.erpCalcCombo = '1';
    input.classList.add('erp-calc-combo');
    var id = 'erp-dl-' + key + '-' + (_uid++);
    var dl = document.createElement('datalist');
    dl.id = id;
    input.setAttribute('list', id);
    input.parentNode.appendChild(dl);
    input.__erpDatalist = dl; // 마운트 타이밍 무관하게 채우기 위한 직접 참조
  }

  function _enhanceProductField(row) {
    var input = row.querySelector('[data-erp="product_name"]'); // 제품명은 항상 input
    if (input) _attachDatalist(input, 'product');
  }

  function _enhancePresetFields(row) {
    PRESET_FIELDS.forEach(function (field) {
      var input = _ensureInputControl(row, field);
      if (input) _attachDatalist(input, field);
    });
  }

  /** 옵션 칸: 다중선택 adder(category optgroup) + 기존 콤마 텍스트 칸 유지. */
  function _enhanceOptionField(row) {
    var ctrl = row.querySelector('[data-erp="option_detail"]');
    if (!ctrl || row.querySelector('.erp-calc-option-adder')) return;
    var mobile = ctrl.className && ctrl.className.indexOf('foms-') >= 0;
    var sel = document.createElement('select');
    sel.className = (mobile ? 'foms-input' : 'form-select form-select-sm') + ' erp-calc-select erp-calc-option-adder mb-1';
    var ph = document.createElement('option');
    ph.value = '';
    ph.textContent = '＋ 옵션 추가… (여러 개 선택 가능)';
    sel.appendChild(ph);
    ctrl.parentNode.insertBefore(sel, ctrl);
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

  // ----- 채우기(catalog 로드 후) -----
  function _populateDatalist(row, field, values) {
    var input = row.querySelector('[data-erp="' + field + '"]');
    if (!input) return;
    var dl = input.__erpDatalist; // 직접 참조(detached 상태에서도 안전)
    if (!dl || dl.dataset.populated === '1') return;
    dl.textContent = '';
    (values || []).forEach(function (v) {
      if (v == null || v === '') return;
      var o = document.createElement('option');
      o.value = String(v);     // .value 설정 → 인용/특수문자 이스케이프 불필요(DOM 안전)
      dl.appendChild(o);
    });
    dl.dataset.populated = '1';
  }

  function _presetNames(field) {
    var list = (_presets && Array.isArray(_presets[field])) ? _presets[field] : [];
    return list.map(function (p) { return p && p.name; }).filter(Boolean);
  }

  function _populateOptionAdder(row) {
    var sel = row.querySelector('.erp-calc-option-adder');
    if (!sel || sel.dataset.populated === '1' || !_optionList) return;
    var byCat = {};
    var order = [];
    _optionList.forEach(function (e, idx) {
      var c = e.category || '기타';
      if (!byCat[c]) { byCat[c] = []; order.push(c); }
      byCat[c].push({ idx: idx, e: e });
    });
    sel.textContent = '';
    var ph = document.createElement('option');
    ph.value = '';
    ph.textContent = '＋ 옵션 추가… (여러 개 선택 가능)';
    sel.appendChild(ph);
    order.forEach(function (c) {
      var og = document.createElement('optgroup');
      og.label = c;
      byCat[c].forEach(function (item) {
        var o = document.createElement('option');
        o.value = String(item.idx);
        var price = item.e.price > 0 ? (' (' + item.e.price.toLocaleString() + '원)') : '';
        o.textContent = item.e.name + price;
        og.appendChild(o);
      });
      sel.appendChild(og);
    });
    sel.dataset.populated = '1';
  }

  function _populateRow(row) {
    _populateDatalist(row, 'product_name', _productNames || []);
    _populateDatalist(row, 'color', _presetNames('color'));
    _populateDatalist(row, 'handle', _presetNames('handle'));
    _populateDatalist(row, 'internal', (_optionsByCategory && _optionsByCategory[INTERNAL_CATEGORY]) || []);
    _populateDatalist(row, 'misc', _presetNames('misc'));
    _populateOptionAdder(row);
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
      if (e && e.price > 0) rows.push({ name: e.token, price: e.price, quantity: 1 });
    });
    return rows;
  }

  function _onOptionTextChange(row) {
    var st = row.__erpPricing;
    if (!st) return;
    var ctrl = row.querySelector('[data-erp="option_detail"]');
    st.option_rows = _parseOptionRows(ctrl ? ctrl.value : '');
    _recalc(row);
  }

  function _onOptionAdderPick(row, sel) {
    var idx = sel.value;
    sel.value = ''; // adder는 항상 placeholder로 복귀(다음 추가 대기)
    if (idx === '' || !_optionList) return;
    var e = _optionList[Number(idx)];
    if (!e) return;
    var ctrl = row.querySelector('[data-erp="option_detail"]');
    if (!ctrl) return;
    var cur = String(ctrl.value || '').trim();
    if (cur === '' || cur === '상담') cur = ''; // 기본값 '상담'은 첫 추가 시 치환
    var tokens = cur ? cur.split(',').map(function (s) { return s.trim(); }).filter(Boolean) : [];
    if (tokens.indexOf(e.token) === -1) tokens.push(e.token); // 중복 추가 방지
    ctrl.value = tokens.join(', ');
    ctrl.dispatchEvent(new Event('input', { bubbles: true }));
    _onOptionTextChange(row);
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
      else if (t.matches('[data-erp="option_detail"]')) _onOptionTextChange(row);
    });
    var pInput = row.querySelector('[data-erp="product_name"]');
    if (pInput) {
      // datalist 선택은 input 이벤트로 들어옴 → 즉시 해석(사용자 조작이므로 손잡이 자동입력 허용)
      pInput.addEventListener('input', function () { _resolveProduct(row, true); });
      pInput.addEventListener('change', function () { _resolveProduct(row, true); });
    }
    var adder = row.querySelector('.erp-calc-option-adder');
    if (adder) adder.addEventListener('change', function () { _onOptionAdderPick(row, adder); });
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
})();
