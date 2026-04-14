# Wave 5 Batch W5-B2 — WDCalculator `composition` canonical chunk

> **batch ID:** W5-B2  
> **lane:** WDCalculator — `composition`  
> **실행일:** 2026-04-14  
> **선행:** W5-B0, W5-B1 (complete)

## Ordering discipline

`delete → merge → extend → add` — 22개 소스 파일 **삭제**, 내용은 기존 순서대로 `composition.js`에 **병합**, 템플릿은 단일 `<script src=composition.js>`로 **확장**, 신규 wrapper 파일 **추가 없음**.

## Delta registers

| Register | 내용 |
|----------|------|
| **product file delta** | `static/js/wdcalculator/composition.js` (canonical chunk; 22개 모듈 본문 포함). `templates/wdcalculator/partials/wdcalculator_scripts_config.html` — 22개 `<script src>` 제거, `composition.js` 1줄 추가. |
| **wrapper file delta** | 구 thin bootstrap 파일 22개 **삭제**(merge 수령). 신규 `*-host-bootstrap.js` **0**. |
| **test file delta** | `tests/support/wdcalculator_*_bootstrap_contract_node_checks.js` 등 — `helperPath`를 개별 `.js` → `composition.js`로 통일; VM sandbox에 `document: {}` 추가(전체 청크 실행 시 `document` 레퍼런스 만족). `tests/test_wdcalculator_product_settings.py` — 인라인 로드 순서 검증을 `composition.js` 단일 슬롯으로 갱신. |
| **canonical target** | `static/js/wdcalculator/composition.js` — W5-B1에서 정의한 **composition** 밴드의 단일 실행 가능 청크. |
| **removal target** | 아래 22개 파일 — 저장소에서 **제거 완료**(내용은 `composition.js` 주석 마커로 추적 가능). |
| **retirement condition** | 템플릿이 더 이상 개별 경로를 참조하지 않음; Node/pytest 계약이 `composition.js` 기준으로 통과하면 청산 완료. 후속 chunk(W5-B3~)는 `primary-form.js` 등 다음 canonical 파일로만 수령. |

### Removed file list (22)

`early-bootstrap.js`, `sidebar-bootstrap.js`, `primary-ui-bootstrap.js`, `catalog-buttons-bootstrap.js`, `catalog-buttons-host-bootstrap.js`, `coupon-search-render-bootstrap.js`, `coupon-search-render-host-bootstrap.js`, `late-bootstrap.js`, `startup-init.js`, `terminal-init.js`, `totals-startup-terminal-bootstrap.js`, `totals-startup-terminal-host-bootstrap.js`, `notes-ui-bootstrap.js`, `notes-ui-host-bootstrap.js`, `post-mutation-ui-bootstrap.js`, `post-mutation-ui-host-bootstrap.js`, `loading-database-bootstrap.js`, `loading-database-host-bootstrap.js`, `products-editing-bootstrap.js`, `products-editing-host-bootstrap.js`, `estimates-early-bootstrap.js`, `estimates-early-host-bootstrap.js`.

## Public load order (post-merge)

`wdcalculator_scripts_config.html`:  
`shared.js` → `unsaved-exit-guard.js` → `layout-sync-wiring.js` → **`composition.js`** → `sidebar-estimates.js` → … (나머지 비-composition 모듈, W5-B1 matrix와 동일한 상대 순서).

`wdcalculator_scripts.html` 인라인 giant script는 기존처럼 `WdCalculator*HostBootstrap` 호출을 유지 — 구현체는 `composition.js`에서 전역 등록.

## Verification (executed)

| 단계 | 명령 | 결과 |
|------|------|------|
| 앱 import | `python -c "import app; print('APP_OK')"` | APP_OK |
| Harness | `python tools/harness/verify_result.py --json` | success |
| Focused automated | `pytest` — `tests/test_wdcalculator_product_settings.py` (전체) | pass |
| Focused automated | `pytest` — `test_wdcalculator_*bootstrap*contract_node.py` (현재 저장소 기준 21개 파일) | 21 passed |
| 보완 | 상위 suite에 가깝게: product_settings 전체가 로드 순서 + 인라인 alias 계약을 함께 검증 | |

**Manual smoke (lane):** 로컬에서 `/wdcalculator` 로드 시 콘솔 에러 없음 가정 — 자동화 범위에서는 HTML 스크립트 태그 순서·pytest로 대체 검증.

## Parallel audit loop (W5 규칙)

### 첫 감리 (구현 직후)

| Reviewer | HIGH | MEDIUM | LOW / nit |
|----------|------|--------|-----------|
| code-reviewer | 0 | 1 | `docs/AI_STATUS.md`가 삭제된 개별 bootstrap 경로·구 테스트 설명을 여전히 정본처럼 나열. |
| evolution-architect | 0 | 0 | (chunk 크기 운영 리스크 언급 — 수용) |
| grand-develop-master | 0 | 0 | governance 위반 없음. |

### MEDIUM 해소 (docs-only)

- `docs/AI_STATUS.md`: `composition.js`·`wdcalculator_scripts_config.html` 순서로 갱신; 구 thin bootstrap 22개 행 제거; bootstrap contract 테스트 표를 **`composition.js` eval 기준**으로 통일; post-mutation UI / host support 행 복구; 진행 중·알려진 이슈 문구 W5-B2 현실에 맞게 수정; 최근 완료 상한 5개 내로 정리.

### 재감리 (MEDIUM 해소 후)

| Reviewer | HIGH | MEDIUM | LOW / nit |
|----------|------|--------|-----------|
| code-reviewer | 0 | 0 | — |
| evolution-architect | 0 | 0 | — |
| grand-develop-master | 0 | 0 | — |

## Direction Lock (batch 요약)

본 batch는 코드 batch; W5-B0 수준의 10문항 전부 재기록은 생략하고, **구조-only 해석**으로 composition 단일 청크 수령과 신규 wrapper 금지를 재확인함.

## Outcome

**PASS — W5-B3 (`primary-form`) 진행 가능.**
