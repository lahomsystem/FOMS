# WDCalculator static JS — Wave 5 canonical chunk map

이 디렉터리는 **WDCalculator** bounded context의 런타임 모듈이다. Wave 5에서는 네 개의 **canonical chunk**로 수렴하는 것이 목표이며, “얇은 host-bootstrap” 파일 증식은 금지다.

## Authoritative chunk targets

| Chunk | Target file | Batch |
|-------|-------------|-------|
| composition | `composition.js` | W5-B2 |
| primary-form | `primary-form.js` | W5-B3 |
| estimate-lifecycle | `estimate-lifecycle.js` | W5-B4 |
| pricing-core | `pricing-core.js` | W5-B5 |

상세 **disposition matrix**(현재 56개 `.js` 파일 전부)는  
`docs/plans/2026-04-14-wave5-batch1-wdcalculator-contract-freeze-run-record.md`를 SoT로 한다.

## Load order (public contract)

1. **Jinja:** `templates/wdcalculator/partials/wdcalculator_scripts_config.html` — `wdCalculatorCategories`, 노트 카테고리 변수 주입 후 `<script src>` 나열.
2. **항상 먼저:** `shared.js` → `unsaved-exit-guard.js` → `layout-sync-wiring.js` — 이 세 파일은 W5-B1에서 **`keep`**로 분류(레이아웃·이탈·공용 유틸).
3. **`composition.js` (W5-B2):** 예전 bootstrap / host-bootstrap 밴드 22개 파일을 한 청크로 수렴. 개별 `*-bootstrap.js` 경로는 제거됨; 계약 검증은 `composition.js`를 로드한 뒤 동일 `WdCalculator*` 헬퍼를 사용한다.
4. **`primary-form.js` (W5-B3):** 다음 7개 모듈 본문을 단일 청크로 병합했고 개별 파일은 제거됨: `notes-ui.js`, `base-components-ui.js`, `coupon-display-helpers.js`, `additional-options-ui.js`, `add-option-button.js`, `calculate-button.js`, `product-catalog-ui.js`. 구간은 소스 주석 `/* --- included: … --- */`로 표시. `wdcalculator_scripts_config.html`에서는 `composition.js` 다음에 `primary-form.js` 한 번 로드 후 `current-estimate-orchestration.js` 등이 이어짐.
5. 이후 순서는 **config partial의 `<script src>` 순서가 계약**이다. chunk 병합 시에도 동일 의미의 초기화 순서를 깨지 말 것.

## Cross-cutting `window` helpers (`shared.js`)

다른 모듈이 직접 의존하는 대표 이름(변경 시 동일 batch bridge + removal plan 필요):

- `syncWdCalculatorViewportLayout`, `requestWdCalculatorLayoutSync`
- `ceilToTens`, `computeAutoPrice1cmFrom30cm`, `generateEstimateId`
- `isSameId`, `normalizeId`, `formatPrice`, `parsePrice`, `escapeHtml`, `formatNumber`

## 수학 / API 진입점 (freeze)

- `window.wdcComputeCurrentEstimateMath` — `current-estimate-math.js`에서 노출.
- `window.wdcComputeAggregateTotals` — `estimate-totals.js`에서 노출.
- `calculation-resolvers.js`가 위 두 함수를 호출.

## URL / fetch

- `url-bootstrap.js`: 쿼리 파라미터 **`estimate_id`**, `GET /api/wdcalculator/estimate/<id>`.

## Anti-patterns (금지)

- 신규 `*-host-bootstrap.js` 추가.
- wrapper-only 파일만 추가하고 retirement 조건 없이 남기기.
- `WdCalculator*` / `wdcCompute*` 이름을 bridge 없이 변경.

## Merge / retire 방향 (요약)

- **merge:** 기존 micro 모듈 → 위 네 canonical 파일로 흡수(W5-B2~B5, `delete → merge → extend → add`).
- **retire-later (W5-B2에서 청산 완료):** composition 밴드에 병합·삭제된 22개 모듈(구 `*bootstrap.js` / `*-host-bootstrap.js` 일부). Node contract 테스트는 `composition.js` 단일 소스를 `vm`에서 실행해 동일 헬퍼 계약을 검증한다.
