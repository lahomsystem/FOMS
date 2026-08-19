# 실측 완료 승인 → 도면 단계 전이 배선 복구 (STATE-QUEST-01 route 이관)

- 작성일: 2026-08-19
- 상태: **승인 대기** (사용자 승인 전 구현 착수 금지)
- 등급: 핵심 코어(상태 머신 + mutation API) → RPI 필수
- 관련: `STATE-QUEST-01`(`9b8a3f79`), `AUTH-QUEST-01`(`2391174c`), `STATE-CORE-00`(`1ab65f78`)

## 1. 문제

모바일 주문 상세·태블릿 실측 폼의 **"실측 완료 → 도면 전달"** 버튼을 눌러도 workflow 단계가
`MEASURE`에 머문다. 도면팀 화면에 주문이 뜨지 않는다.

### 근본 원인 — 배선 누락 (회귀)

`POST /api/orders/<id>/quest/approve` ([foms/api/quest.py:242](../../foms/api/quest.py))는 승인
기록만 하고 전이하지 않는다:

```python
auto_transitioned = False   # 하드코딩, 전이 호출 없음
```

전이 담당 서비스 `quest_transition_service.advance_stage_on_quest_completion()`은 **이미 구현·
테스트까지 되어 있으나 호출하는 코드가 전 저장소에 없다**(참조: `tests/domains/test_state_quest.py`,
`tools/harness/order_mutation_writer_scan.py` 뿐).

| 시점 | 커밋 | 내용 |
|---|---|---|
| 2026-07-26 | `2391174c` (AUTH-QUEST-01) | 라우트의 기존 자동 전이 코드(`auto_transitioned = True`, `STAGE_AUTO_TRANSITIONED` 이벤트, 다음 quest 생성) **삭제**. "전이는 STATE-QUEST-01 하류" |
| 이후 | `9b8a3f79` (STATE-QUEST-01) | 전이 서비스 신설. 원장 문구: "HTTP route/monkeypatch 없이 서비스 직접" = **route 이관 미포함** |

→ 2026-07-26부터 오늘까지 약 3.5주간 전이 경로가 끊긴 상태. 태블릿 JS 주석
([tablet-measure-form.js:1578](../../static/js/foms/tablet-measure-form.js))은 아직 "서버가
MEASURE→DRAWING 전환까지 처리한다"고 적혀 있어 실제 동작과 불일치.

### 영향 연쇄

1. **도면 작업실 미노출** — 워크벤치는 `stage_code == 'DRAWING'`(또는 `drawing_status == 'RETURNED'`,
   컨펌 포함 옵션)만 목록에 넣는다([workbench.py:437-441](../../foms/web/drawing/workbench.py)).
2. **주문 변경 → 도면팀 알림 미발화** — `should_alert_drawing_team()`
   ([drawing_order_change.py:111-121](../../foms/services/notifications/drawing_order_change.py))의 세 조건
   (`drawing_status ∈ {IN_PROGRESS,TRANSFERRED,RETURNED,CONFIRMED}` / DRAWING 담당자 지정 /
   stage rank ≥ DRAWING)이 모두 불발. 실측 내용을 고쳐도 도면팀에 알림 0.
3. **도면 수정 요청 진입 불가** — `POST /api/orders/<id>/request-revision`은 "도면 전달(확정 대기)
   상태에서만" 허용([erp_orders_revision.py:97](../../foms/api/drawing/erp_orders_revision.py)).
4. 현재 현장 우회 = 관리자가 단계 강제 변경(`stage-override`)으로 수동 이동.

### 실측 규모 (스테이징 DB, 2026-08-19 읽기전용 조회)

| 항목 | 건수 |
|---|---|
| `MEASURE` 단계 + 담당자 승인 완료 (= 끼인 주문) | **7** |
| `MEASURE` 단계 전체 | 306 |
| `RECEIVED` 단계 + 팀 승인 기록 존재 | 6 |
| `DRAWING` 단계 전체 | 38 |

운영 DB 수치는 미조사(사용자 승인 후 읽기전용 1회 측정 필요).

## 2. 목표 / 비목표

**목표**
- 실측 담당자 승인이 최종 승인이면 같은 트랜잭션에서 `MEASURE → DRAWING` 전이가 일어난다.
- 전이는 `order_transition_service.transition_order`(정본 엔진) 경유 — 라우트에서 stage 직접 쓰기 0.
- 승인 기록과 단계 전이가 **원자적**이다(한쪽만 남는 상태 없음).
- 전이 후 도면 작업실 노출·도면팀 변경 알림·수정 요청 경로가 정상 발화한다.

**비목표**
- 새 수정 요청 프로세스 신설 — 기존 (a) 주문 변경 알림 (b) 도면 수정 요청으로 충분. 진입만 복구한다.
- `DRAWING`/`CONFIRM` standalone 승인 전이 — 전용 command 전용 정책 유지(409).
- 도면 quest 자동 생성 — `_STAGE_ADVANCE`의 `MEASURE` 행이 `make_next_quest=False`. 정책 유지.
- 전이 엔진·mutation 정책·모델·마이그레이션 변경 없음.

## 3. 설계

### 3-1. 라우트 배선 (`foms/api/quest.py`)

승인 기록(JSONB) 직후, **같은 세션·같은 트랜잭션**에서 전이 서비스를 호출하고 커밋은 1회.

```
[권한 게이트] → [승인 기록: sd 갱신 + flag_modified]
   → [advance_stage_on_quest_completion(...)]     # is_complete 일 때만
   → [sync_erp_flat_columns] → [db.commit()] → [대시보드 캐시 무효화]
```

호출 인자(기존 production/construction 라우트 패턴과 동일하게 맞춘다):

| 인자 | 값 |
|---|---|
| `actor_user_id` | `session['user_id']` |
| `scope_hash` | `sha256("QUEST_APPROVE:{order_id}")` — 기존 `_scope_hash` 헬퍼와 동일 규약 |
| `request_hash` | `sha256(정규화 body)` |
| `idempotency_key` | body `idempotency_key` (없으면 None) |
| `expected_version` | None (이 라우트는 If-Match 미사용 — 현행 유지) |
| `reason` / `source_screen` | `"{stage} 최종 승인"` / 요청 화면 문자열 |

**구현 제약 (검증 필수)**: 엔진은 내부에서 order를 FOR UPDATE로 잠그고
`copy.deepcopy(order.structured_data)`로 시작한다. 라우트가 먼저 대입한 승인 기록이 엔진의
deepcopy 시점에 반영돼 있어야 하므로, 승인 기록 → `order.structured_data` 대입 → `flag_modified`
→ 전이 호출 순서를 지키고, **승인 + 전이가 한 커밋에 모두 남는지 테스트로 고정**한다.

### 3-2. 적용 범위 결정 필요 — `RECEIVED` 포함 여부

`_STAGE_ADVANCE`는 `RECEIVED`(팀 승인 → `MEASURE`, fresh MEASURE quest 생성)도 정의한다.
서비스를 그대로 호출하면 접수 단계 팀 승인 완료 시에도 자동으로 실측 단계로 넘어간다.

- **안 A (서비스 전체 배선)**: 설계 의도 그대로. RECEIVED도 복구(회귀 이전 동작과 동일).
- **안 B (MEASURE만 우선)**: 이번엔 `MEASURE`만 전이하고 `RECEIVED`는 후속 결정.

→ **권고: 안 A.** 삭제된 원 코드가 두 단계 모두 전이시켰으므로 회귀 복구 = 안 A. 스테이징 영향
대상 6건으로 작다.

### 3-3. 응답·오류 계약

성공 응답의 기존 필드를 실제 값으로 채운다(형태 불변, 프런트 호환).

```json
{"success": true, "all_approved": true, "auto_transitioned": true, "next_stage": "도면", "quest": {...}}
```

| 상황 | HTTP | code |
|---|---|---|
| 최종 승인 아님(팀 일부만) | 200 | `auto_transitioned=false` (전이 미호출) |
| `DRAWING`/`CONFIRM` standalone | 409 | `STAGE_COMMAND_REQUIRED` (기존 라우트 선행 가드와 동일 결론) |
| quest 미완인데 전이 시도 | 409 | `QUEST_INCOMPLETE` |
| stage 실제값이 expected_from과 불일치(동시 편집) | 409 | 엔진 `TransitionError` 매핑 |
| 전이 실패 | — | 전체 롤백(승인 기록도 남지 않음) |

### 3-4. 프런트엔드

- [order_detail_mobile_v2.html](../../templates/orders/partials/order_detail_mobile_v2.html) 인라인 스크립트:
  현재 성공 시 페이지 리로드 → 단계 변경이 그대로 반영되므로 **로직 변경 불필요**. 실패 메시지에
  서버 `code` 노출만 보강.
- [tablet-measure-form.js](../../static/js/foms/tablet-measure-form.js): 성공 후 `load()` 재조회 →
  동작 그대로. **사실과 어긋난 주석 갱신 + `?v=` 범프 필수**(SW staticCacheFirst).

### 3-5. 기존 끼인 주문 백필

승인은 됐는데 `MEASURE`에 남아 있는 주문(스테이징 7건, 운영 미조사) 처리안:

- **안 1 (권고)**: 일회성 스크립트 `tools/ops/`에서 동일 서비스로 전이(dry-run 기본, 대상 목록
  출력 후 apply). 감사 이벤트가 정상적으로 남는다.
- 안 2: 관리자 수동 `stage-override` — 건수 적으면 가능하나 감사 사유가 "강제 변경"으로 남는다.
- 안 3: 방치 — 다음 승인 시도 시 전이되므로 자연 해소되나, 재승인 버튼이 안 보여 실질 불가.

## 4. 변경 파일 (예상)

| 파일 | 내용 |
|---|---|
| `foms/api/quest.py` | 전이 서비스 호출 배선, 응답 필드 실제화, 오류 매핑 |
| `static/js/foms/tablet-measure-form.js` | 주석 정정(+`?v=` 범프) |
| `templates/orders/partials/order_detail_mobile_v2.html` | 실패 메시지 보강(선택) |
| `tests/domains/test_state_quest.py` | 라우트 경유 케이스 추가 |
| `tests/domains/test_auth_quest_approve.py` | 전이 발생/미발생 계약 |
| `tools/ops/backfill_measure_quest_stage.py` | (안 1 채택 시) 백필 스크립트 |
| `docs/harness/foms_state_writer_inventory.json` | 필요 시 재생성(정본 엔진 경유라 EXTERNAL 증가 없어야 정상) |

마이그레이션 없음. mutation manifest 2종은 이미 이 라우트를 등재하고 있어 신규 등록 불필요.

## 5. 검증 계획

1. **red→green 단위**: 라우트 POST → `workflow.stage == 'DRAWING'`, `erp_stage_code` 동기,
   `order.status` projection, `MEASUREMENT_COMPLETED` 이벤트, 승인 기록 동시 존재.
2. **원자성**: 전이 실패 주입 시 승인 기록도 롤백.
3. **멱등**: 같은 `idempotency_key` 재요청 시 전이·이벤트 중복 0.
4. **거부 계약**: `DRAWING`/`CONFIRM` standalone 409, 팀 일부 승인 시 전이 0.
5. **연쇄 확인**: 전이 후 도면 작업실 목록 노출, 주문 편집 시 `ERP_ORDER_CHANGED` 알림 발화,
   `request-revision` 진입 가능.
6. **회귀**: `pytest tests/domains tests/contracts`, PG 레인, `pre_push_smoke exit 0`.
7. **스테이징 E2E**: `claude_master`로 실제 주문 1건 승인 → 도면 작업실 노출까지 HTTP로 확인.

## 6. 리스크

| 리스크 | 대응 |
|---|---|
| 승인 즉시 단계 이동 → 실측 대시보드에서 사라짐(사용자 체감 변화) | 회귀 이전 동작과 동일. 릴리스 노트 고지 |
| 전이가 알림 fan-out을 유발해 도면팀에 대량 알림 | 백필은 dry-run으로 건수 확인 후 적용, 필요 시 알림 억제 옵션 |
| 접수 단계까지 자동 전이(안 A) | 스테이징 6건. 원 동작 복구이며 테스트로 고정 |
| 동시 편집 중 전이 충돌 | 엔진 FOR UPDATE + expected-from 검증이 409로 차단 |

## 7. 롤백

라우트 배선 1커밋으로 격리 → `git revert` 시 즉시 회귀 이전(현 상태)으로 복귀. 백필은 별도
커밋·별도 실행이라 코드 롤백과 무관.

## 8. 결정 사항 (2026-08-19 사용자 확정)

1. 적용 범위: **안 A — `RECEIVED`+`MEASURE` 둘 다 전이**(회귀 이전 동작 복구).
2. 백필: **안 3 — 방치**. 백필 스크립트를 만들지 않는다.
   - 알려진 부작용: 이미 승인이 기록된 주문(스테이징 7건)은 승인 버튼이 더 이상 노출되지 않으므로
     이번 수정 후에도 자동으로는 도면 단계로 올라가지 않는다. 필요해지면 관리자가
     `stage-override`로 개별 이동한다. 변경 파일 목록에서 `tools/ops/backfill_...` 제외.
3. 운영 DB 끼인 주문 건수 측정: **보류**(필요 시 배포 직전 사용자 요청으로 1회 읽기전용 측정).

## 9. 남은 승인 게이트

- 구현 착수 승인(이 문서 기준). 승인 후: 라우트 배선 → 테스트 red→green → pre_push_smoke →
  deploy 푸시 → CI 전 워크플로 확인 → 스테이징 E2E 확인.
