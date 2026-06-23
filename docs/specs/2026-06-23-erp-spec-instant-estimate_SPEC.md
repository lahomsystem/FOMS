# ERP 현장 스펙 즉시견적·자동연동 Spec
> 작성일: 2026-06-23 | 상태: 🟡 승인대기
> 작성: CEO 리뷰(gstack plan-ceo-review 방법론) + 정밀 코드 리뷰 기반

## 0. 결정 요약 (사용자 승인 게이트 결과)
- **아키텍처**: A안 — erporder 스펙 폼 안에서 WDCalculator 가격엔진 재사용 + 저장 시 WDC 견적 동시기록(dual-write) + 주문 자동매칭.
- **필드 설정 소스**: 기존 `wdcalculator_product_settings` 확장(단일 설정 화면).
- **범위**: 모바일 + 데스크톱 동시. 안전을 위해 feature flag(cohort) 뒤에서 출시.

---

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
실측/영업 담당자가 **erporder(주문 수정/신규) 한 화면에서**:
1. 제품 항목의 **제품명을 드롭다운(또는 직접입력)** 으로 고르고, 규격(폭) 입력 → **그 자리에서 가격이 자동 계산**되어 항목 금액에 채워진다.
2. 색상·옵션·손잡이·내부·기타/설치위치를 **드롭다운 프리셋(없으면 직접입력)** 으로 빠르게 채운다.
3. 저장 한 번에 (a) ERP 주문(`structured_data`)이 저장되고, (b) **계산기 견적(WDC `Estimate`)이 동일 내용으로 생성/갱신**되며, (c) 그 견적이 **이 주문과 자동 매칭(`EstimateOrderMatch`)** 된다.
4. 드롭다운 프리셋·제품 단가는 **계산기 제품설정 화면(`/wdcalculator/product-settings`)에서 한 곳으로 관리**한다.

### 1.2 기능 요구사항
1. **즉시 계산**: 제품(카탈로그) + 폭(mm) [+ 옵션] 입력/변경 시 `wdcComputeCurrentEstimateMath`로 즉시 단가 계산하여 항목 가격 표시·반영. 계산 비활성 항목은 기존처럼 금액 수동입력 유지.
2. **필드 드롭다운+직접입력**: 제품명(=제품 카탈로그), 옵션(=추가옵션 카테고리/가격), 색상·손잡이·내부·기타·설치위치(=텍스트 프리셋). 모든 필드는 "직접입력" 선택 시 자유 텍스트 허용.
3. **프리셋 설정·저장**: `wdcalculator_product_settings`에 `spec_field_presets`(색상/손잡이/내부/기타 프리셋) 추가. 제품설정 화면에서 CRUD.
4. **저장 시 dual-write + 자동매칭**: ERP `PUT /structured` 성공 후, 계산결과를 WDC `Estimate`로 upsert + `EstimateOrderMatch` 멱등 보장. 견적 id는 `structured_data.meta.wdc_estimate_id`에 보존하여 재저장 시 갱신.
5. **모바일 UX**: 한 손 조작·큰 터치타깃(48px)·즉시 가격 피드백·단일 저장. 기존 모바일 빌더/아코디언 패턴과 일관.
6. **데스크톱**: 동일 기능을 데스크톱 폼에도 제공(콤보 컨트롤).
7. **출시 게이트**: `FOMS_ERP_SPEC_CALC_ENABLED` + cohort. 미활성 시 현행 동작 100% 유지.

### 1.3 예외/제약 조건
- **하위호환 절대 유지**: `pricing`이 없는 레거시 항목은 지금과 똑같이 렌더(자유입력 + 수동금액). 신규 키는 전부 optional.
- **fail-open + 가시적 오류**: ERP 주문 저장(`PUT /structured`)은 항상 SSOT. WDC 견적 동기화 실패는 주문 저장을 막지 않되 **사용자에게 보이는 경고 + 서버 로그**를 남긴다(묵시적 무시 금지 — AGENTS.md/CLAUDE.md 규칙).
- **성능 가드(G1/G2)**: `pricing-core.js`·제품 카탈로그는 erporder 페이지 기본 로드에 **동기 추가 금지**. 계산 활성화 시점 **lazy-load**(html2canvas 패턴과 동일).
- **idempotent(G4)**: 재실행되는 바인딩/리스너는 `window.__erpSpecCalcBound` 단일 가드로 중복 방지.
- **복합 폭 표기 보존**: W 칸은 `5700(2402+1864+1638)` 같은 복합 표기를 그대로 보존(기존 계약). 계산용 폭(mm)은 별도 파생값으로 산출하며 원문 `spec`/`spec_rows`를 훼손하지 않는다.
- **두 세션 경계**: FOMS `db`와 `wd_calculator_session`은 별도 커밋. 부분실패를 명시적으로 처리(아래 §2.4).
- **스코프 단순화(명시)**: ERP 항목 1개 = 계산기 base component 1개(제품×폭) 기준. 다중 base component·할인쿠폰·배송 등 고급 견적은 풀 계산기에 남긴다(NOT in scope, §6).

---

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `wdcalculator_models.py` | `WDCalculatorProductSettings`에 `spec_field_presets` JSON 컬럼 추가(default dict) |
| `wdcalculator_db.py` | `init_wdcalculator_db()`에 컬럼 멱등 ensure(`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, PG/SQLite 분기) |
| `foms/api/wdcalculator/blueprint.py` | `load_spec_field_presets()/save_spec_field_presets()` 헬퍼; `GET/POST/DELETE /api/wdcalculator/spec-field-presets*`; **신규** `POST /api/orders/<int:order_id>/wdc-estimate-sync`(upsert+멱등 매칭); `_build_settings_seed()`에 presets 시드 |
| `data/spec_field_presets.json` (신규) | 색상/손잡이/내부/기타 기본 프리셋 시드 |
| `templates/wdcalculator/product_settings.html` | "현장 스펙 프리셋" 관리 섹션(필드별 add/remove) + JS |
| `static/js/orders/erp-order-shared.js` | `erpNewItemRow` 콤보 컨트롤(제품명/옵션/색상·손잡이·내부·기타) + 계산 폭 입력 + 항목 가격 표시; `_ensureWdcPricingEngine()` lazy 로더; 제품/프리셋 캐시 로더; 라이브 계산 바인딩; `erpCollectStructured`에 `obj.pricing` 첨부; `erpSaveStructuredOnce`에 dual-write 단계 추가 |
| `templates/orders/partials/erp_order_js.html` | (lazy 로더가 주입하므로 정적 `<script>` 추가는 하지 않음) flag 전달 확인 |
| `templates/orders/partials/edit_order_body.html` / `erp_order_tab*.html` | `flag_spec_calc` 전달, 항목 가격 readout/배지용 컨테이너(필요 시) |
| 라우트(주문 수정/신규 렌더 뷰) | `flag_spec_calc = is_enabled_for_user('FOMS_ERP_SPEC_CALC_ENABLED', user_id, cohort_key='FOMS_ERP_SPEC_CALC_COHORT')` 주입 |
| `static/css/...` (erp-pro 또는 신규 page-scoped) | 콤보 컨트롤·가격 readout 스타일(인라인 금지) |
| `tests/...` | §4 참조 |

### 2.2 데이터 모델 설계

**(a) `structured_data.items[]` — 가격 확장(additive, optional)**
```jsonc
items[n] = {
  // ---- 기존 키(불변) ----
  "product_name": "몰딩(푸쉬)",
  "spec_rows": [{"spec_width":"2400","spec_depth":"600","spec_height":"720"}],
  "spec_width":"2400","spec_depth":"600","spec_height":"720","spec":"2400x600x720",
  "internal":"상담","color":"화이트","option_detail":"상담","handle":"상담","misc":"주방",
  "price": 675200,            // 계산 활성 시 pricing.computed.final_price로 자동기입(읽기전용); 비활성 시 수동
  "extra_input":"", "measurement_date":"", "construction_date":"",
  // ---- 신규 키(optional) ----
  "pricing": {
    "enabled": true,
    "product_id": 2,                 // 제품명 드롭다운 선택 = 카탈로그 product.id
    "width_mm": 2400,                // 계산용 폭(복합 W에서 파생; 원문 spec 불변)
    "base_components": [             // 엔진 입력(단순화: 1개)
      {"mode":"select","productId":2,"widthMm":2400,"additionalFees":[],"widthInput":"2400"}
    ],
    "option_rows": [                 // 옵션(가격 영향) — 추가옵션 카테고리에서 선택
      {"name":"여닫이 5자 적용","price":0,"quantity":1}
    ],
    "coupon_value": 0,
    "computed": {"base_price":675200,"additional_price":0,"total_price":675200,"final_price":675200},
    "source":"erp_spec_calc",
    "computed_at":"2026-06-23T09:10:00+09:00"
  }
}
```
- 레거시 항목: `pricing` 없음 → 기존 자유입력 UI + 수동 금액. (erpNewItemRow 분기)
- `width_mm` 파생: W 칸 원문에서 숫자/합산 파싱(백엔드 `eval_spec_width_mm`와 동일 규칙의 경량 클라 파서, 또는 단일 정수 그대로). 원문 `spec`/`spec_rows`는 변경하지 않는다.

**(b) `WDCalculatorProductSettings.spec_field_presets` (신규 컬럼)**
```jsonc
spec_field_presets = {
  "color":    [{"id":1,"name":"화이트"},{"id":2,"name":"그레이"}],
  "handle":   [{"id":1,"name":"히든손잡이"},{"id":2,"name":"바형"}],
  "internal": [{"id":1,"name":"기본"},{"id":2,"name":"서랍형"}],
  "misc":     [{"id":1,"name":"주방"},{"id":2,"name":"드레스룸"}]
}
```
- `option_detail`(옵션) 프리셋은 신설하지 않고 **기존 `additional_options` 카테고리/가격**을 재사용(가격 연동 목적).
- `product_name`(제품명)은 **기존 `products` 카탈로그** 재사용(선택 시 `product_id` 세팅 → 가격 계산).

**(c) WDC `Estimate.estimate_data` — ERP 동기화 페이로드(기존 형식 준수)**
```jsonc
estimate_data = {
  "estimates": [ /* 각 ERP 항목의 pricing을 계산기 라인 형식으로 매핑 */
    {"id":null,"productId":2,"productName":"몰딩(푸쉬)","displayName":"몰딩(푸쉬)",
     "widthMm":2400,"basePrice":675200,"options":[],"additionalPrice":0,
     "totalPrice":675200,"baseComponents":[...],"notes":""}
  ],
  "totalBasePrice":675200,"totalAdditionalPrice":0,"totalPrice":675200,
  "coupon_discount":0,"shipping_cost":0,"shipping_included":false,
  "notes":"", "source":"erp_spec_calc", "order_id": 123
}
```
- 계산기에서 불러와도 깨지지 않도록 기존 `buildEstimateData`/`hydrateEstimateItems` 형식과 동일 키 유지.

### 2.3 아키텍처 방향
- **엔진 재사용(DRY)**: 가격은 `window.wdcComputeCurrentEstimateMath`(순수함수, `pricing-core.js`) 그대로 호출. 가격 로직 복제 금지.
- **설정 단일화**: 제품/옵션/비고/스펙프리셋 모두 `wdcalculator_product_settings` 싱글턴. 기존 `load_*/save_*` 패턴 그대로 확장.
- **저장 책임 분리**: `PUT /structured`(SSOT, 불변 책임) → 성공 후 `POST /api/orders/<id>/wdc-estimate-sync`(보조, 멱등, 자기 오류 보고). 핵심 ERP 엔드포인트에 WDC 의존을 넣지 않는다.
- **lazy 로드**: `_ensureWdcPricingEngine()`가 `pricing-core.js`를 1회 주입(Promise 캐시). 제품 카탈로그는 `GET /api/wdcalculator/products` 1회 fetch 후 `window.__erpWdcProducts` 캐시.
- **참고 기존 패턴**: `estimate-preview.js`의 `_ensureHtml2canvas()` lazy 패턴, `match-order` 두 DB 접근(`get_db`+`get_wdcalculator_db`), `is_enabled_for_user` cohort 게이트.

### 2.4 신규 서버 엔드포인트 — `POST /api/orders/<int:order_id>/wdc-estimate-sync`
위치: `foms/api/wdcalculator/blueprint.py`(두 DB 세션 이미 import). 권한: `@login_required`(+ 주문 수정 권한과 동일 role 검토).

요청:
```jsonc
{ "estimate_id": 0|<int>, "customer_name":"홍길동", "estimate_data": { ... } }
```
로직(단일 `wd_db` 트랜잭션 + FOMS 주문 존재 검증):
1. `order = foms_db.query(Order).filter(Order.id==order_id, Order.active_filter()).first()` → 없으면 `success:false`.
2. `estimate` upsert: `estimate_id` 있으면 갱신(+`EstimateHistory` 스냅샷), 없으면 생성. `customer_name`/`estimate_data` 반영.
3. **멱등 매칭**: `EstimateOrderMatch(estimate_id, order_id)` 존재하면 그대로, 없으면 insert. (기존 `match-order`처럼 중복을 오류로 보지 않음)
4. `wd_db.commit()`. 실패 시 `wd_db.rollback()` + `success:false`(메시지).
5. 반환 `{success, estimate_id, matched:true}`.

부분실패 정책: 2~4 중 실패 → 클라이언트는 "주문은 저장됐고 견적 동기화는 실패" 경고 표시 + 재시도 버튼. 서버는 예외를 로그로 남긴다(빈 except 금지).

### 2.5 프런트엔드 동작 설계 (`erp-order-shared.js`)
1. **lazy 로더**: `_ensureWdcPricingEngine()`(script inject, 1회), `_ensureWdcProducts()`(fetch+캐시), `_ensureSpecPresets()`(fetch+캐시). flag on이고 첫 항목 렌더/포커스 시 트리거.
2. **`erpNewItemRow` 분기(flag on)**:
   - 제품명: `<select>`(카탈로그 + "직접입력") + 숨은 text. 선택 시 `pricing.product_id` 세팅·계산. "직접입력" 시 자유 텍스트(계산 비활성).
   - 계산 폭(mm): 기존 W 칸 사용(복합 표기 보존) + 파생 `width_mm`. 필요 시 보조 "계산폭" 표시.
   - 옵션: 추가옵션 카테고리 드롭다운(가격 포함) → `option_rows` 추가 + "직접입력" 텍스트(설명용 `option_detail`).
   - 색상/손잡이/내부/기타·설치위치: 프리셋 `<select>` + "직접입력" 콤보(`erpMobileFlexibleControl` 확장).
   - 항목 가격 readout: 계산값 실시간 표시. `price` input은 계산 활성 시 read-only(자동기입), 비활성 시 수동.
3. **라이브 계산**: 제품/폭/옵션 input·change 시 `wdcComputeCurrentEstimateMath([baseComp], products, optionRows)` → readout/`price`/`row.__erpPricing.computed` 갱신. 단일 가드 `__erpSpecCalcBound`.
4. **수집**: `erpCollectStructured`에서 각 row의 `row.__erpPricing`을 `obj.pricing`으로 첨부(없으면 미첨부). `obj.price`는 계산값과 동기.
5. **저장 오케스트레이션**(`erpSaveStructuredOnce`): 기존 `PUT /structured` 성공 후, flag on & 계산 항목 ≥1 이면:
   - `estimate_data` 조립(§2.2c), `estimate_id = __erpLastStructuredData.meta.wdc_estimate_id || 0`.
   - `POST /api/orders/<id>/wdc-estimate-sync`.
   - 성공: `structured_data.meta.wdc_estimate_id = res.estimate_id`(+`window.__erpLastStructuredData.meta` 갱신). meta는 PUT 보존키이므로 다음 저장에서 자동 유지.
   - 실패: `erpSetStatus(..., true)` 경고 + 콘솔 로그. 주문 저장 자체는 성공 처리.

### 2.6 의존성 및 영향 범위
- **DB 변경**: `wdcalculator` 스키마 `wdcalculator_product_settings`에 컬럼 1개 추가(create_all 관리 테이블 → 멱등 ALTER 필요). 단일 DB 통합 모드 = 같은 Postgres 인스턴스의 별도 스키마(분리 DB 모드도 호환).
- **영향 모듈**: WDCalculator 설정/견적/매칭 API, ERP 주문 폼 JS, 제품설정 템플릿. 계산기 본체 페이지·데스크톱(≥992px) 무영향(엔진 함수만 공유).
- **마이그레이션**: Alembic 아님(WDC는 create_all). `init_wdcalculator_db()`에 idempotent column ensure 추가. 운영 적용은 앱 부팅 시 자동(로그 확인).
- **성능**: erporder 기본 페이로드 불변(lazy). 계산은 클라 순수함수(서버 부하 0). 추가 fetch는 제품/프리셋 1회씩(캐시).

---

## 3. Steps — 실행 단계 (순차 구현 + 단계별 1:1 리뷰)

- [ ] **Phase 1 — 백엔드 데이터/엔드포인트**: `spec_field_presets` 컬럼 + 멱등 ensure + 시드; `load/save_spec_field_presets` + CRUD 라우트; `wdc-estimate-sync` 엔드포인트. → 단위테스트 → **1:1 리뷰**.
- [ ] **Phase 2 — 제품설정 UI**: `product_settings.html` 스펙 프리셋 섹션 + JS(CRUD). → **1:1 리뷰**.
- [ ] **Phase 3 — 프런트 엔진 통합**: lazy 로더, 제품/프리셋 캐시, `erpNewItemRow` 콤보 컨트롤 + 계산 폭 + 라이브 계산, `erpCollectStructured` pricing 첨부. → Node 계약테스트 → **1:1 리뷰**.
- [ ] **Phase 4 — 저장 dual-write/자동매칭**: `erpSaveStructuredOnce` 동기화 단계 + `meta.wdc_estimate_id`. → 엔드포인트 통합테스트 → **1:1 리뷰**.
- [ ] **Phase 5 — 모바일 UX persona 마감**: 48px 터치타깃, 즉시 가격 펄스, 콤보 가독성, 데스크톱 회귀. → 시각/구조 계약 → **1:1 리뷰**.
- [ ] **Phase 6 — Full inspection**: `APP_OK`, 관련 pytest subset, `python tools/perf/perf_scan.py --guard`, 모바일/데스크톱 e2e, flag off 회귀.

각 Phase는 독립 동작/검증 가능하도록 분할(flag off면 무영향). Phase 1·2는 사용자에게 기능 노출 없음(안전).

---

## 4. 검증 기준
- [ ] `python -c "import app; print('APP_OK')"` → `APP_OK`
- [ ] `/edit/<id>`·`/add` 200 OK (flag on/off 양쪽)
- [ ] flag **off**: 기존 ERP 폼 동작·테스트 100% 통과(`test_erp_orders_structured_put.py`, `test_erp_order_shared_form_scripts.py`, `test_erp_order_edit_mobile_form.py`)
- [ ] flag **on**: 제품 선택+폭 입력 → 가격 즉시 표시; 저장 → `structured_data.items[].pricing` 기록 + WDC `Estimate` 생성 + `EstimateOrderMatch` 1건(재저장 시 update, 중복 매칭 0건)
- [ ] `meta.wdc_estimate_id` 재저장 멱등(견적 누적 생성 안 됨)
- [ ] 스펙 프리셋 CRUD 라운드트립(설정 저장 → 폼 드롭다운 반영)
- [ ] WDC 동기화 강제 실패 시 주문 저장 성공 + 가시적 경고 + 서버 로그(묵시적 무시 없음)
- [ ] `python tools/perf/perf_scan.py --guard` exit 0 (render-blocking/CDN 동기 스크립트 신규 0)
- [ ] 신규 컬럼 ensure가 기존 DB에서 멱등(2회 부팅 안전)

## 5. 위험 / 실패 모드 (Eng 리뷰)
| # | 위험 | 영향 | 완화 |
|---|------|------|------|
| R1 | 두 세션 부분실패(주문 저장 후 WDC 실패) | 견적 미동기 | 순서 고정(PUT 먼저), 멱등 재시도, 가시적 경고+로그, 재저장 시 자동 복구 |
| R2 | create_all 테이블 컬럼 추가 누락 | 신규 필드 저장 실패 | 부팅 멱등 ALTER(PG `IF NOT EXISTS`, SQLite PRAGMA 가드) + 부팅 로그 |
| R3 | 복합 폭(`5700(...)`) → 계산폭 오파싱 | 단가 오류 | 원문 보존 + 명시적 계산폭 파서(합산/괄호 규칙) + 항목별 readout로 사용자 확인 |
| R4 | erporder 페이지 무거워짐 | TTFB/렌더 저하 | 엔진/카탈로그 lazy, 기본 페이로드 불변, perf guard 게이트 |
| R5 | 중복 리스너/MutationObserver | 모바일 재실행 중복 | `window.__erpSpecCalcBound` 단일 가드(G4) |
| R6 | 레거시 항목 회귀 | 기존 주문 깨짐 | `pricing` optional, flag off 경로 보존, 계약테스트 |
| R7 | 권한 경계(견적 동기화) | 무단 견적생성 | 엔드포인트 role 검증 = 주문 수정 권한과 동일, 주문 존재/active 검증 |

## 6. NOT in scope (명시적 제외 — 추후 별도)
- 다중 base component·할인쿠폰·배송비 등 풀 계산기 고급 기능(풀 계산기 유지).
- WDC 견적 → ERP 역방향 자동 반영(현재는 ERP→WDC 단방향).
- 정식 견적서/계약서(`OrderEstimate`, `foms/api/erp_estimates.py`)와의 통합(별개 시스템).
- 데스크톱 전용 신규 레이아웃(기존 폼에 콤보만 추가).

## 7. 참고 자료
- 관련 결정: DECISIONS `2026-05-31 Mobile tablet redesign`(feature flag+cohort), `2026-05-28 Caveman default`, `2026-04-19 견적 결제정보`.
- 코드: `pricing-core.js`(`wdcComputeCurrentEstimateMath` L306), `erp-order-shared.js`(`erpNewItemRow` L773, `erpCollectStructured` L1393, `erpSaveStructuredOnce` L1691), `foms/api/wdcalculator/blueprint.py`(save-estimate L762, match-order L834, settings CRUD L442~759), `wdcalculator_models.py`, `wdcalculator_db.py`, `foms/services/feature_flags.py`.
- 성능: `docs/guides/PERFORMANCE_GUARDRAILS.md` (G1/G2/G4).
