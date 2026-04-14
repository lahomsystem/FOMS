# Wave 4 Batch W4-B4 — Dashboard family next lock

> **batch ID:** W4-B4  
> **risk axis:** docs / truth  
> **실행일:** 2026-04-14

## Scope lock

- **허용:** 본 run record만.  
- **금지:** runtime, templates, blueprints.

## Inputs consumed

| # | 소스 |
|---|------|
| 1 | W4-B0 — `pilot_context=cs` (이미 소비). `production`·`construction`은 dashboard 후보로 잔존 |
| 2 | 계획 §5.5 — `pilot_context=cs`이므로 **production vs construction** 비교 branch |

## Consumed pilot exclusion

- **`cs` (completion):** W4-B2/W4-B3에서 소비됨 — 본 배치 후보에서 제외.

## Dashboard family comparison (`production` vs `construction`)

| 필드 | production (`apps.erp_production_page` → `foms/web/production`) | construction (`apps.erp_construction_page`) |
|------|--------------------------------|-----------------------------------------------|
| Primary route | `GET /erp/production/dashboard` | `GET /erp/construction/dashboard` (live 코드 기준 동일 패턴) |
| Page module shape | 단일 대시보드 뷰 + 필터/페이지네이션 로직 (`foms/web/production/dashboard.py`) | 단일 대시보드 + 시공 특화 필터/ mine gating (별도 모듈) |
| Partial family | filters, filters_grid, mobile_filters, mobile_queue, modals, scripts, styles | 동등 partial family + `erp_construction_scripts` hotspot |
| Inline script hotspot | `partials/erp_production_scripts.html` (Wave 5 defer) | `partials/erp_construction_scripts.html` (Wave 5 defer) |
| Self-measurement / mine | `erp_mine_only` 등 생산 큐 권한 필터 | 시공 팀 mine / assigned 필터 — **교차 의존 더 복잡** |
| Dedicated static | 없음 (본 Wave에서 빈 static dir 생성 안 함) | 없음 |
| Canonical target | `foms/web/production` | `foms/web/construction` |

## Tie-break table

| 메트릭 | production | construction |
|--------|------------|----------------|
| shared partial count (유사 패턴) | 기준선 | 동일 tier |
| shared shell dependency | 동일 (layout/sub_nav freeze) | 동일 |
| API/page coupling | 주문 큐 읽기 중심 | mine/권한 분기 추가 |
| dedicated static asset count | 0 | 0 |
| self-measurement / mine-filter special path count | 낮음 (대시보드 큐 중심) | **높음** (시공자 배정 필터) |
| **winner reason** | **동일 Wave에서 dashboard-family 두 번째 슬롯으로 생산 큐가 상대적으로 단순**하고, 계획 §2.4의 production vs construction 비교에서 **먼저 잠글 후보로 production이 선행** | loser — **Wave 4 본 mainline에서 후속 코드 batch에 포함하지 않음** |

## Winner lock decision

| 항목 | 값 |
|------|-----|
| **dashboard family winner** | **`production`** |
| **FR20 key** | `production` (canonical namespace `foms/web/production`, `templates/production/`) |

## Deferred-next order (문서 잠금)

1. **construction** — W4-B4 loser; **Wave 4 continuation / 다음 웨이브**에서 `foms/web/construction` + `templates/construction/` 후보  
2. **drawing** — **즉시 승격 금지**: 2-route cluster + shared drawing partials — 계획 §5.5.3; construction이 막히면 그래도 drawing으로 미끄러지지 않고 **stop → W4-B7** 규칙은 본 웨이브에서 **construction을 아직 코드 배치하지 않았으므로** 후속 웨이브에서 재평가  
3. **shipment-dashboard / shipment-settings** — Tier 3 dual-lane — W4-B7 defer  
4. **as** — giant shell — defer  
5. **main ERP shell / regional** — Wave 5

## Why not `drawing` in this wave branch

- 계획 **§2.4 / §5.5**: `cs` pilot 이후 dashboard 승자는 **production vs construction** 비교이며, **`drawing`은 대체 후보로 즉시 올리지 않는다** (detail+dashboard cluster).

## Spec §4 delta summary

| 항목 | 값 |
|------|-----|
| product file delta | 0 (docs-only) |

## Verification

| 검사 | 결과 |
|------|------|
| docs-only | ✅ |
| compare branch 두 후보 동일 필드 평가 | ✅ |
| winner 외 context code batch 미포함 | ✅ |

## Direction Lock (10문항)

| # | 답 | 한 줄 근거 |
|---|-----|------------|
| 1 | yes | 다음 dashboard SoT 후보 하나만 잠금 |
| 2 | yes | loser 명시적 defer |
| 3 | yes | 코드 추가 없음 |
| 4 | yes | 단일 결정 테이블 |
| 5 | yes | 파일 증가 없음 |
| 6 | N/A | |
| 7 | N/A | |
| 8 | yes | |
| 9 | yes | |
| 10 | yes | 문서-only |

## Next batch

- **W4-B5** — `production` page owner → `foms/web/production/dashboard.py` (완료 시 본 기록과 일치 확인).
