# Wave 3 Batch W3-B4 — Aggregate-read candidate lock (`personal_board` vs `events`)

> **batch ID:** W3-B4  
> **risk axis:** docs / contract (medium — candidate selection only)  
> **실행일:** 2026-04-13

## Scope lock

- **문서만** `docs/plans/2026-04-13-wave3-batch4-aggregate-read-lock-run-record.md` 생성·갱신.  
- **런타임 코드·controlling spec 본문·plan 파일 금지.**  
- 후보 **두 컨텍스트 비교 후 winner 1개**만 잠금.

## Inputs consumed

- `docs/plans/2026-04-13-wave3-batch3-address-canonicalization-run-record.md` (선행 코드 배치 완료)
- `apps/api/personal_board.py`, `apps/api/events.py` 소스 대조 (비교 시점 기준)
- `docs/plans/2026-04-13-wave3-api-canonicalization-execution-plan.md` §2.4 tie-break (`personal_board` → `events`)
- `docs/plans/2026-04-13-wave2-batch6-closeout-run-record.md` (W2-B6 API shortlist — 본 배치와 충돌 시 override 아래 기술)

## Wave 2 key normalization

| 후보 | registry lane | spec domain | FR20 context key |
|------|---------------|-------------|------------------|
| personal_board | ERP aux API (`personal_board_bp`) | Wave 3 API canonicalization | `personal_board` |
| events | Auxiliary events (`events_bp`) | Wave 3 API canonicalization | `events` |

## Candidate comparison table

| 필드 | personal_board | events |
|------|------------------|--------|
| module path (비교 시점) | `apps.api.personal_board` | `apps.api.events` |
| blueprint symbol | `personal_board_bp` | `events_bp` |
| `url_prefix` | `/api/personal-board` | `/api` (`events_bp`; 하위 경로에 `change-events` 포함) |
| route 수 | **1** (`GET …/summary`) | **4** (`GET`×3 + `POST`×1) |
| read vs mutation | **read-only** (GET만) | **read-heavy + mutation** (`POST …/revert`) |
| DB aggregation 폭 | 넓음 (Order/Task/Notification/Chat/OrderEvent 등 읽기 집계) | GET 경로는 로그·이벤트 집계; POST는 주문/이벤트 되돌림 |
| JSONB / `flag_modified` | 집계 응답만 — **스키마 변이 없음** | **POST revert**에서 `copy.deepcopy` + `flag_modified` 등 **쓰기 경로** |
| hidden side effect | 세션·DB 읽기, ERP 표시 헬퍼 lazy import | 되돌림 시 주문/보안 로그·상태 변경 가능성 |
| provisional tier (계획 §2.3) | Tier 2 medium (aggregate-read) | Tier 2 medium + **mutation lane → 사실상 분리 전까지 canonicalize 부적합** |
| canonical target (목표) | `foms/api/personal_board` | `foms/api/events` (장기) |

## Contract table (winner 후보 — `personal_board`)

| route path | methods | decorator stack | auth | response shape |
|------------|---------|-----------------|------|----------------|
| `/api/personal-board/summary` | `GET` | `@personal_board_bp.route` → `@login_required` | 로그인 필요 | JSON: `success`, 브리핑 위젯 payload (기존과 동일 freeze) |

## Hidden side effect inventory (winner — `personal_board`)

- DB: 다테이블 SELECT/집계 (읽기 전용).
- `session`: 사용자 컨텍스트 읽기.
- 외부 네트워크: 없음.
- storage / presigned / realtime: 없음.

## FR19 decision

- **N/A (docs-only batch)** — 코드 변경 없음. 후속 W3-B5에서 winner에 대해 **extend** 단일 모듈 `foms/api/personal_board` 예정.

## Changes made

- 본 run record만.

## Spec §4 delta summary

- product / wrapper / test: **변경 없음** (docs-only).

## Verification

| 검사 | 결과 |
|------|------|
| docs-only batch | ✅ |
| winner 단일 컨텍스트 | ✅ `personal_board` |
| medium-risk 증거 (mutation·JSONB) 누락 없음 | ✅ `events` POST 경로 명시 |

## FR20 / README gate

- 본 배치는 코드 없음. winner canonical이 단일 모듈로 가면 FR20 **README 생략** 후보(W3-B5에서 확정).

## Test footprint decision

- 본 배치 테스트 추가 없음.

## Direction Lock answers

1. SSOT 방향: winner 선택으로 다음 배치에서 `foms.api.personal_board`로 집중 — **예**  
2. split-brain: `events`는 동시 이전 안 함 — **예, 임시 shim 증가 없음**  
3. delete/merge/extend 검토: docs-only — **해당**  
4. —  
5–6. 파일 수: 본 배치 증가 없음 — **예**  
7. README: W3-B5에서 단일 모듈이면 생략 — **조건부 예**  
8. 반복 시 폴더 정리: API SSOT 패턴 일관 — **예**  
9. 경계: `events` mutation은 Wave 3 mainline에서 분리 — **예**  
10. 구조만 — **예**

## Drift / stop decision

- **Stop 없음.** `W2-B6` shortlist는 `notifications`/`erp_map` 우선순위를 제시했으나, **Wave 3 실행 계획 §4는 `personal_board` vs `events`만 비교**하도록 고정되어 있음.  
- **Override reason:** 계획 §2.4 tie-break 및 W3-B0 queue에서 aggregate-read 후보로 `personal_board`가 `events`보다 앞서며, `events`는 POST revert로 **한 blueprint 내 read+mutation 공존** → 본 Wave의 aggregate-read **단일 winner**로 부적합.

## Winner lock decision

- **Winner: `personal_board`**  
- **Loser (next candidate): `events`**

## Loser next-step note (`events`)

- **Unblock 조건:**  
  1. `POST /orders/<id>/change-events/<event_id>/revert`를 **read aggregate canonicalization과 분리**할 contract freeze(또는 별도 Tier 3 batch)를 먼저 수행하거나,  
  2. GET-only 서브셋을 **별 blueprint/모듈 경계**로 나눌 수 있는지 엔지니어링 검토 후에만 `foms/api/events` 이전 검토.  
- **권장 다음 wave:** Wave 3 범위 밖 **defer** → 후속 API wave 또는 `erp_orders_*` 인접 정책과 합의된 batch.

## Next step or defer

- **W3-B5** — winner `personal_board`만 canonicalize (`foms/api/personal_board` + thin `apps/api/personal_board`).

---

**touched files:** 본 run record만
