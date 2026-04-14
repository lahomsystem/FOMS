# Wave 2 Batch W2-B5 — FR20 README coverage pass

> **batch ID:** W2-B5  
> **risk axis:** AI/human entrypoint docs  
> **실행일:** 2026-04-13

## 1. 선행 확인 (Wave 1 `src/`)

- `docs/plans/2026-04-13-wave1-batch2-src-classification-run-record.md` 재확인: `src/`는 **non-product / tooling-adjacent**; `src/README.md`는 FR20 context 앵커 후보가 **아님** (계획서 README 역할 분리와 정합).

## 2. FR20 기계적 판정 (gate + ladder)

### 후보 context

| Context | runtime 모듈 수 (canonical `foms` 기준) | web/api/services 교차 | FR20 후보? | 앵커 결정 |
|---------|------------------------------------------|------------------------|------------|-----------|
| Measurement | web 2+, api 2+, services 2+ | 예 (3층+) | **예** | 기존 `foms/web/measurement/` — **page-first** → `foms/web/measurement/README.md` |
| Orders (API cluster) | `foms/api/orders` 다모듈 + 분산 order 서비스 | 예 (api + services) | **예** | API-first — `foms/web/orders` 패키지 없음 → **`foms/api/orders/README.md`** |
| WDCalculator | canonical `foms/web/wdcalculator` 등 패키지 **부재** | (측정 불가) | **defer** | 새 패키지 루트 생성 금지 — Wave 5 + `BD-013` 재개 |

## 3. 생성한 README

| Path | 역할 |
|------|------|
| `foms/README.md` | product namespace 전역 진입점 |
| `foms/web/measurement/README.md` | Measurement 단일 앵커 |
| `foms/api/orders/README.md` | Orders API 단일 앵커 |

## 4. Defer 표

| Context | 이유 | 재개 wave / 조건 |
|---------|------|-------------------|
| WDCalculator | `foms/web/wdcalculator` 등 앵커 디렉터리 없음; 새 디렉터리 생성은 W2-B5 금지 | Wave 5 (large FE island); `BD-013` |
| Channel / Auth / 전체 ERP | FR20 이중 조건 미충족 또는 앵커 tie-break 모호 | Wave 3+에서 context별 재판정 |

## 5. Verification

| 검사 | 결과 |
|------|------|
| context당 README 1개 | ✅ (Measurement·Orders 각 1; `foms/README`는 global) |
| 목적·모듈·읽기 순서·금지/overlay | ✅ 각 파일에 포함 |
| 새 디렉터리 생성 없음 | ✅ |

## 6. Direction Lock

7–8: README **중복 없음**; defer는 wave 명시.

---

**touched files:** `foms/README.md`, `foms/web/measurement/README.md`, `foms/api/orders/README.md`, 본 파일  
**verification result:** PASS  
**residual risk:** WDCalculator FR20 앵커는 Wave 5에서 재오픈
