/**
 * ERP 현장 스펙 즉시견적 (erp-order-shared.js 보조 모듈).
 *
 * 동작은 전적으로 window.ERP_SPEC_CALC_ENABLED 플래그에 게이트된다.
 * 플래그 off → enhanceItemRow/collectPricing이 호출돼도 즉시 반환(무영향).
 *
 * 책임:
 *  - 제품명 칸에 카탈로그 드롭다운(+직접입력) 부착 → 제품 선택 시 product_id 확보
 *  - 색상/손잡이/내부/기타 칸에 프리셋 드롭다운(+직접입력) 부착
 *  - 옵션 칸에 추가옵션(가격연동) 드롭다운(+직접입력) 부착
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

  var PRESET_FIELDS = ['color', 'handle', 'internal', 'misc'];
  var PRICING_ENGINE_SRC = '/static/js/wdcalculator/pricing-core.js';

  var _enginePromise = null;
  var _catalogPromise = null;
  var _products = null;       // 제품 카탈로그
  var _presets = null;        // {field: [{id,name}]}
  var _optionList = null;     // [{name, price, label}] (추가옵션 평면화)

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

  function _ensureCatalog() {
    if (_catalogPromise) return _catalogPromise;
    _catalogPromise = Promise.all([
      _ensureEngine(),
      _fetchJson('/api/wdcalculator/products').then(function (d) {
        _products = (d && d.success && Array.isArray(d.products)) ? d.products : [];
      }).catch(function () { _products = []; }),
      _fetchJson('/api/wdcalculator/spec-field-presets').then(function (d) {
        _presets = (d && d.success && d.spec_field_presets) ? d.spec_field_presets : {};
      }).catch(function () { _presets = {}; }),
      _fetchJson('/api/wdcalculator/additional-options/categories').then(function (d) {
        var cats = (d && d.success && Array.isArray(d.categories)) ? d.categories : [];
        _optionList = [];
        cats.forEach(function (cat) {
          (cat.options || []).forEach(function (o) {
            if (o && o.name) {
              _optionList.push({ name: o.name, price: Number(o.price) || 0, label: (cat.name || '') + ' › ' + o.name });
            }
          });
        });
      }).catch(function () { _optionList = []; })
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

  function _selectClass(refInput) {
    var mobile = refInput && refInput.className && refInput.className.indexOf('foms-') >= 0;
    return (mobile ? 'foms-input' : 'form-select form-select-sm') + ' erp-calc-select mb-1';
  }

  // ----- DOM 주입 -----
  function _injectProductControl(row) {
    var input = row.querySelector('[data-erp="product_name"]');
    if (!input || row.querySelector('.erp-calc-product-select')) return;
    var sel = document.createElement('select');
    sel.className = _selectClass(input) + ' erp-calc-product-select';
    sel.innerHTML = '<option value="">제품 선택… (또는 아래 직접입력)</option><option value="__manual__">직접입력</option>';
    input.parentNode.insertBefore(sel, input);
  }

  function _injectPresetControls(row) {
    PRESET_FIELDS.forEach(function (field) {
      var ctrl = row.querySelector('[data-erp="' + field + '"]');
      if (!ctrl || row.querySelector('.erp-calc-preset-select[data-target-field="' + field + '"]')) return;
      var sel = document.createElement('select');
      sel.className = _selectClass(ctrl) + ' erp-calc-preset-select';
      sel.setAttribute('data-target-field', field);
      sel.innerHTML = '<option value="">선택… (또는 아래 직접입력)</option>';
      ctrl.parentNode.insertBefore(sel, ctrl);
    });
  }

  function _injectOptionControl(row) {
    var ctrl = row.querySelector('[data-erp="option_detail"]');
    if (!ctrl || row.querySelector('.erp-calc-option-select')) return;
    var sel = document.createElement('select');
    sel.className = _selectClass(ctrl) + ' erp-calc-option-select';
    sel.innerHTML = '<option value="">옵션 선택… (또는 아래 직접입력)</option>';
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
  function _populateProductSelect(row) {
    var sel = row.querySelector('.erp-calc-product-select');
    if (!sel || sel.dataset.populated === '1' || !_products) return;
    var opts = ['<option value="">제품 선택… (또는 아래 직접입력)</option>'];
    var sorted = _products.slice().sort(function (a, b) {
      var ca = (a.category || '힣'), cb = (b.category || '힣');
      if (ca !== cb) return ca < cb ? -1 : 1;
      return String(a.name || '') < String(b.name || '') ? -1 : 1;
    });
    sorted.forEach(function (p) {
      var label = (p.category ? '[' + p.category + '] ' : '') + (p.name || '');
      opts.push('<option value="' + p.id + '">' + _escape(label) + '</option>');
    });
    opts.push('<option value="__manual__">직접입력</option>');
    sel.innerHTML = opts.join('');
    sel.dataset.populated = '1';
  }

  function _populatePresetSelects(row) {
    if (!_presets) return;
    row.querySelectorAll('.erp-calc-preset-select').forEach(function (sel) {
      if (sel.dataset.populated === '1') return;
      var field = sel.getAttribute('data-target-field');
      var list = (_presets[field] && Array.isArray(_presets[field])) ? _presets[field] : [];
      var opts = ['<option value="">선택… (또는 아래 직접입력)</option>'];
      list.forEach(function (p) {
        if (p && p.name) opts.push('<option value="' + _escape(p.name) + '">' + _escape(p.name) + '</option>');
      });
      sel.innerHTML = opts.join('');
      sel.dataset.populated = '1';
    });
  }

  function _populateOptionSelect(row) {
    var sel = row.querySelector('.erp-calc-option-select');
    if (!sel || sel.dataset.populated === '1' || !_optionList) return;
    var opts = ['<option value="">옵션 선택… (또는 아래 직접입력)</option>'];
    _optionList.forEach(function (o, idx) {
      var price = o.price > 0 ? (' (' + o.price.toLocaleString() + '원)') : '';
      opts.push('<option value="' + idx + '">' + _escape(o.label + price) + '</option>');
    });
    sel.innerHTML = opts.join('');
    sel.dataset.populated = '1';
  }

  function _syncSelectionsFromState(row) {
    var st = row.__erpPricing;
    if (!st) return;
    if (st.product_id) {
      var psel = row.querySelector('.erp-calc-product-select');
      if (psel) psel.value = String(st.product_id);
    }
  }

  function _escape(text) {
    var div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  // ----- 이벤트 -----
  function _setTextControl(ctrl, value) {
    if (!ctrl) return;
    ctrl.value = value;
    ctrl.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function _onProductChange(row, value) {
    var st = row.__erpPricing;
    var input = row.querySelector('[data-erp="product_name"]');
    if (value === '' || value === '__manual__') {
      st.enabled = false;
      st.product_id = null;
      st.manual_override = false;
      if (value === '__manual__' && input) { input.focus(); }
      _recalc(row);
      return;
    }
    var prod = _findProduct(value);
    if (prod) {
      st.product_id = Number(value);
      st.enabled = true;
      st.manual_override = false; // 새 제품 선택 → 자동계산 복귀
      if (input) _setTextControl(input, prod.name || input.value);
    }
    _recalc(row);
  }

  function _onPresetChange(row, sel) {
    var field = sel.getAttribute('data-target-field');
    var ctrl = row.querySelector('[data-erp="' + field + '"]');
    if (sel.value) _setTextControl(ctrl, sel.value);
  }

  function _onOptionChange(row, sel) {
    var st = row.__erpPricing;
    var ctrl = row.querySelector('[data-erp="option_detail"]');
    if (sel.value === '' || !_optionList) {
      st.option_rows = [];
      _recalc(row);
      return;
    }
    var opt = _optionList[Number(sel.value)];
    if (opt) {
      _setTextControl(ctrl, opt.name);
      st.option_rows = opt.price > 0 ? [{ name: opt.name, price: opt.price, quantity: 1 }] : [];
    }
    _recalc(row);
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
    row.addEventListener('input', function (e) {
      var t = e.target;
      if (t && t.matches && t.matches('[data-erp="spec_width"]')) _recalc(row);
    });
    var psel = row.querySelector('.erp-calc-product-select');
    if (psel) psel.addEventListener('change', function () { _onProductChange(row, psel.value); });
    row.querySelectorAll('.erp-calc-preset-select').forEach(function (sel) {
      sel.addEventListener('change', function () { _onPresetChange(row, sel); });
    });
    var osel = row.querySelector('.erp-calc-option-select');
    if (osel) osel.addEventListener('change', function () { _onOptionChange(row, osel); });
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
      _injectProductControl(row);
      _injectPresetControls(row);
      _injectOptionControl(row);
      _injectPriceMeta(row);
      _bindRow(row);
      _ensureCatalog().then(function () {
        _populateProductSelect(row);
        _populatePresetSelects(row);
        _populateOptionSelect(row);
        _syncSelectionsFromState(row);
        _recalc(row);
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

  window.ErpSpecCalc = ErpSpecCalc;
})();
