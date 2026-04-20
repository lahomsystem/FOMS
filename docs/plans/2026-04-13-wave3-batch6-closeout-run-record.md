# Wave 3 Batch W3-B6 — Mixed/high-risk backlog freeze + closeout

> **batch ID:** W3-B6  
> **risk axis:** docs / handoff (Wave 3 종료)  
> **실행일:** 2026-04-13

## Scope lock

- **문서만:** 본 run record + 계획에 허용된 spec/archive 참조 갱신.  
- **런타임 코드·신규 API canonicalization 착수 금지.**

## Inputs consumed

- `docs/plans/2026-04-13-wave3-batch5-aggregate-read-canonicalization-run-record.md`
- `foms/platform/blueprints.py` (import·등록 목록 — 누락 증명)
- `docs/plans/2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md` (레지스트리 대조)

## Wave 2 key normalization

| 항목 | 값 |
|------|-----|
| registry lane | 전역 API 레지스트리 (`blueprints.py`) |
| spec domain | Wave 3 API canonicalization **closeout** |
| FR20 context key | 해당 없음 (docs-only) |

## Contract table

- 본 배치는 contract freeze 대상 아님 — **N/A**.

## Hidden side effect inventory

- **N/A** (docs-only).

## FR19 decision

- **N/A** — 코드 변경 없음.

## Changes made

- `docs/plans/2026-04-13-wave3-batch6-closeout-run-record.md` (본 문서)
- `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` §5 Wave 3 run record 링크 보강
- `docs/ARCHIVE_INDEX.md` — Wave 3 batch run record 행 추가

## Spec §4 delta summary

- 문서 참조·인덱스만 — 제품 코드 delta 없음.

## Verification

| 검사 | 결과 |
|------|------|
| docs-only closeout | ✅ |
| defer register에 계획 §5.7 최소 surface 포함 | ✅ + `blueprints.py` 대조 보강 행 |
| Wave 4/6/8 경계 서술 | ✅ 아래 |

## FR20 / README gate

- 본 배치 코드 없음 — **N/A**.

## Test footprint decision

- 추가 테스트 없음.

## Direction Lock answers

1–10: 문서-only closeout, 동작·구조 코드 미변경 — **전부 해당 (구조 문서 정합만)**

## Drift / stop decision

- Wave 3 전 배치 완료 — **정상 closeout.**

## Wave 3 완료 범위 요약 (done)

| Batch | 내용 |
|-------|------|
| W3-B0 | Readiness gate + queue lock |
| W3-B1 | `files` contract freeze |
| W3-B2 | `foms/api/files` + thin `apps/api/files` |
| W3-B3 | `foms/api/address` + thin `apps/api/address` |
| W3-B4 | aggregate-read 후보 `personal_board` vs `events` → **winner `personal_board`** |
| W3-B5 | `foms/api/personal_board` + thin `apps/api/personal_board` |
| W3-B6 | 본 closeout |

## `blueprints.py` 대조 — 계획 최소 backlog에 없는 API (누락 방지)

| Import | 처리 |
|--------|------|
| `apps.api.erp_shipment_settings` (`erp_shipment_bp`) | 출고 설정 API — CRUD/설정 성격 → **defer** (아래 표) |
| `apps.storage_dashboard` | 페이지 Blueprint — Wave 4 대상, Wave 3 API canonicalization **범위 외** |
| 기타 `apps.*_page` | 페이지 레인 — Wave 4 |

## Defer / backlog register (high-risk & Wave 3 미처리 API)

계획 §5.7 최소 목록 + W3-B4 loser + `blueprints` 보강.

| Surface | Current owner (요약) | Why not now | Required prep | Suggested next wave / batch type |
|---------|---------------------|-------------|---------------|----------------------------------|
| `erp_estimates` | `apps.api.erp_estimates` | GET/POST/PUT/DELETE 혼재 | read vs mutation split contract | Wave 4+ dedicated API batch |
| `notifications` | `apps.api.notifications` | 다수 POST·broadcast | write lane 분리·실시간 정책 | Wave 4+ / Tier 2 API batch |
| `tasks` | `apps.api.tasks` | full CRUD | CRUD contract freeze | Wave 4+ API batch |
| `erp_map` | `apps.api.erp_map` | map gen + mutator 혼재 | read/mutator split | Wave 4+ (measurement family) |
| `erp_measurement` (mutation) | `apps.api.erp_measurement` | POST/PUT side | 선례와 mutation lane 분리 명시 | Dedicated measurement API batch |
| `erp_orders_*` (다수 BP) | `apps.api.erp_orders_*` | 단계·구조화 데이터 mutation | 주문 도메인 정책 동반 | Wave 4+ 또는 orders 전용 batch |
| `erp_shipment_settings` | `apps.api.erp_shipment_settings` | 출고 설정 mutation | 설정 API contract | Wave 4+ API batch |
| `attachments` (+ internal) | `apps.api.attachments` | storage·thumbnail·legacy 경로 | dedicated prep | Tier 3 prep 후 |
| `chat` | `apps.api.chat` | Socket.IO binding | realtime 구조 유지 전제 | Wave 5+ / platform 결합 |
| `channel_*` | `apps.api.channel_*` | webhook/WAM 다중 BP | 시그니처·멱등 | Wave 4+ integration batch |
| `backup` | `apps.api.backup` | 운영 mutation | ops contract | Defer / ops batch |
| `quest` | `apps.api.quest` | 워크플로 side effect | 도메인 묶음 | Wave 4+ |
| `debug` | `apps.api.debug` | 디버그 표면 | quarantine 정책 | Defer / tooling |
| `wdcalculator` | `apps.api.wdcalculator` | giant FE 결합 | Wave 5 rebaseline | **Wave 5** (spec) |
| **`events`** | `apps.api.events` | **W3-B4 loser** — GET+**POST revert** 공존 | read-only subset 분리 또는 revert Tier 3 freeze | Post-W3 aggregate batch 또는 orders 인접 |

## Wave 4 / Wave 6 / Wave 8 boundary (재확인)

- **Wave 4:** page/template/static slice, ERP 페이지 Blueprint — API-only 이전과 분리.  
- **Wave 6:** `foms/services`·루트 `services/` namespace rationalization — API canonicalization과 분리.  
- **Wave 8:** `apps/`·루트 bridge retirement — W3에서 남긴 shim(`apps.api.files` 등) 제거 조건 실행.

## Next step or defer

- **Wave 4** 웹/페이지 슬라이스 또는 다음 **API 전용** 계획에서 backlog 우선순위 재평가.  
- Wave 3 **코드 작업은 본 closeout으로 종료.**

## Post-closeout 감리 보정 (GDM/코드리뷰 반복 루프)

Wave 3 배치 종료 후 **초정밀 감리**에서 나온 HIGH/MEDIUM에 대해 아래를 **최소 범위**로 반영했다 (플랜 파일 비수정).

| 이슈 | 조치 |
|------|------|
| `tests/test_foms_namespace_imports.py`가 `apps.api.files`에 `get_storage` 바인딩을 기대하는데 thin shim에 없음 (HIGH) | `apps/api/files.py`에 `from foms.services.storage import get_storage` re-export 및 `__all__` 추가 |
| `foms.api.personal_board`가 `apps.api.erp_orders_completion.TARGET_STATUSES`에 역의존 (MEDIUM) | `ORDER_SETTLEMENT_ALERT_TARGET_STATUSES`를 `foms/services/erp_policy_internal/constants.py`에 두고 `foms.services.erp_policy`로 re-export; `personal_board`·`erp_orders_completion`이 동일 SSOT 사용 |
| `foms/api/files.py`, `foms/api/address.py`의 `print`+`str(e)` 500 응답 (MEDIUM) | `logging`+`logger.exception`으로 서버 로깅, 클라이언트 메시지는 일반 문구로 통일 (JSON 키 `success`/`message` 유지) |

**추가 touched files (감리 후):** `foms/services/erp_policy_internal/constants.py`, `foms/services/erp_policy.py`, `foms/api/files.py`, `foms/api/address.py`, `foms/api/personal_board.py`, `apps/api/files.py`, `apps/api/erp_orders_completion.py`

---

**touched files:** 본 run record, `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` (§5), `docs/ARCHIVE_INDEX.md`
