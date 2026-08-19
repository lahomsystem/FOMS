# 핀포인트 복원 GUI (RESTORE-GUI-01) — 스펙

- 작성: 2026-08-19
- 상태: **승인 대기** (Research 완료 → Plan)
- 기준 코드: deploy `9dcd89a3` / production `ad640344`
- 선행: ORDER-DIFF-00·01(`order_field_changes` 운영 배포됨), DATA-DOCTOR-01(`tools/ops/data_doctor.py`, **deploy 전용**)

## 1. 문제

2026-08-14 AS 대시보드 증발 사고(55건)의 복구는 **사람 손 + CLI + DSN 직결**로 했다.
근거 원장은 이미 있는데(감사행·이벤트·필드 원장) 그 근거를 **화면에서 집어 되돌리는 수단이 없다**.
사고가 또 나면 같은 비용을 다시 치른다.

현재 가진 것과 없는 것:

| 있는 것 | 위치 |
|---|---|
| 필드 단위 변경 원장(before/after·행위자·사유) | `order_field_changes` (운영 배포) |
| 그 원장을 사람 문장으로 읽는 조회 API | `GET /api/orders/<id>/field-changes` |
| 사고 창 일괄 복구 엔진 | `tools/ops/data_doctor.py` (deploy 전용, CLI) |
| 고위험 작업 승인 게이트 + 화면 | OPS-APPROVAL, `/admin/ops/approvals/<id>` |
| 정규 뮤테이터(version·If-Match·receipt) | `execute_order_mutation` (`foms/services/orders/revision.py:223`) |

| 없는 것 |
|---|
| 필드 변경 이력을 **보는 화면** — `field-changes` API 를 소비하는 UI 가 0개다 |
| 한 건 되돌리기 — `_COMPENSATION_REGISTRY` 에 `DRAWING_ASSIGNEE_SET` 1종뿐 |
| data_doctor 의 화면 — CLI + DSN 직결만, production 에는 파일 자체가 없다 |

## 2. 목표 / 비목표

**목표**
1. 주문 상세에서 필드 변경 이력을 보고 **한 건씩 되돌린다**(T1).
2. 관리자 화면에서 사고 창을 조사 → 복구안 미리보기 → 승인 → 적용 → 롤백한다(T2).
3. 복원 자체가 원장에 남는다(복원이 유령 변경이 되지 않게).

**비목표**
- **임의 JSON-path write primitive 부활** — 이미 보안 위험으로 제거된 설계다(`foms/api/events.py:243`). 되살리지 않는다.
- 첨부·도면·관계 테이블(`OrderScheduleDate`·`OrderASCycle`·`ProductionRun`) 복원 — before 값 자체가 없다. PITR fork 영역.
- 절단된 값 복원(§3.3).
- 단계(`workflow.stage`) 값 되쓰기 — 전이 규칙·부수효과가 있어 값 복원으로 다루면 안 된다(T2 축).

## 3. T1 — 필드 단위 되돌리기

### 3.1 읽기

`GET /api/orders/<id>/field-changes` 를 **그대로 재사용**한다. 이미 change_set 단위로
`{at, actor, reason, changes:[{path, label, text, before, after, op, item}]}` 를 돌려준다.
신규 화면은 주문 상세의 탭 하나이며 서버 라우트를 새로 만들지 않는다.

### 3.2 되돌리기 API

```
POST /api/orders/<order_id>/field-changes/<change_id>/restore
body: {"reason": "<필수>"}
```

**요청은 `change_id`(PK) 하나만 받는다.** 경로·이전값은 서버가 원장 행에서 읽는다 —
요청이 target 을 지정할 수 없으므로 임의 경로 write 가 성립하지 않는다(기존 typed
compensation 의 원칙을 데이터 주도로 확장한 것).

### 3.3 안전 장치 4개

1. **복원 가능 경로 화이트리스트** `RESTORABLE_PATHS`. 원장 행의 `path_template` 이 여기
   없으면 400. 계약 테스트로 `RESTORABLE_PATHS ⊆ SCALAR_PATHS` 를 강제한다.
2. **절단 값 차단**. `structured_diff._VALUE_LIMIT = 120` 이라 긴 값은 `…` 가 붙어 저장된다.
   `before_value` 가 `…` 로 끝나면 400 — **복원이 곧 데이터 훼손**이기 때문이다.
   화면은 그 행의 버튼을 비활성화하고 이유를 적는다.
3. **현재값 대조**. 현재 `structured_data` 의 그 경로 값이 원장의 `after_value` 와 다르면 409.
   사고 후 사람이 이미 고친 값을 덮지 않는다(`data_doctor` 의 skip 규율과 동일).
4. **정규 뮤테이터 경유**. `execute_order_mutation(policy_id="ORDER_FIELD_RESTORE",
   expected_versions={order_id: version}, idempotency_key=...)` 로 감싼다. 직접
   `flag_modified` 금지 — mutation writer 인벤토리에서 EXTERNAL 로 새지 않게.

### 3.4 v1 화이트리스트 (15경로)

```
schedule.measurement.date / .time
schedule.construction.date / .time
schedule.as_visit.date / .time
flags.urgent / flags.urgent_reason
assignments.owner_team
shipment.sales_delivery / .construction_time / .construction_workers
shipment.trip / .as_billing / .as_pending
```

**v1 에서 뺀 것과 이유**
- `totals.*` — 파생값이다. 단독 복원하면 `items` 합계와 어긋난다(출고가=grand total 규약).
  금액은 재계산 훅을 붙인 뒤 v2 에서 연다.
- `payment.*` — 확인 행위가 `PAYMENT_CONFIRMED` 로 따로 남는 축이라 값만 되돌리면 두 축이 어긋난다.
- `parties.*` — PII. 되돌리기 권한과 열람 권한이 같지 않다.
- `site.address_*` — 정본이 "full == main 합본 / detail 빈값" 규약이라 한 쪽만 복원하면 깨진다.
- `notes` — 장문이라 절단 확률이 높다(§3.3 에서 어차피 대부분 막힌다).
- `items.*` — 인덱스 드리프트. `item_uid` 로 안정 참조는 가능하나 별도 검증이 필요해 v2.
- `workflow.stage` — §2 비목표.

### 3.5 권한·기록

- 권한: `ADMIN` 또는 그 변경의 `actor_user_id` 본인(기존 `compensate` 규칙 그대로).
- 사유 필수(빈 문자열 400).
- 기록 3벌: 새 `order_field_changes` 행(복원도 변경이다) + `SecurityLog` `ORDER_FIELD_RESTORED`
  + `OrderEvent` `CHANGE_REVERTED`(`restored_change_id` 포함).

### 3.6 마이그레이션

**없다.** 기존 테이블만 읽고 쓴다.

## 4. T2 — 사고 창 일괄 복구 (`/admin/data-doctor`)

### 4.1 구조 분리

`tools/ops/data_doctor.py`(650줄, psycopg2 직결)를 `foms/services/orders/data_doctor.py`
(SQLAlchemy 세션 기반)로 옮기고 CLI 는 얇은 래퍼로 남긴다. **로직 이중화 금지** —
CLI 와 화면이 같은 계획 생성기를 쓴다.

### 4.2 화면 3단

1. **조사** — 기간(naive UTC)·행위자로 사고 창의 변경 건수 요약(읽기 전용).
2. **복구안** — 주문별 `현재값 → 복원값 / confidence(exact>logged>event>inferred) / 제외 사유` 표.
   상한 500 유지, 넘으면 범위를 좁히게 한다.
3. **적용** — **OPS-APPROVAL 게이트 필수**.
   `consume_same_db(operation_id="DATA_DOCTOR_APPLY", artifact_sha256=<계획 canonical sha256>)`.
   승인된 계획과 다른 계획은 consume 단계에서 거부된다(`offline_recovery.py` 패턴 그대로).
   dry-run 이 기본이고 승인 토큰을 소비하지 않는다.

### 4.3 롤백

적용 전 스냅샷을 파일이 아니라 DB 에 남기고 `/admin/data-doctor/rollback` 에서 되돌린다.
신규 테이블 `data_doctor_snapshots`(마이그레이션 1개) — FK 없음(감사 원장 규약, AUDIT-LOG T9).

### 4.4 승격 선행 조건

`data_doctor.py` 는 **production 에 없다**(deploy 전용). T2 는 그 승격이 선행이다.
AS-AXIS-01 과 달리 마이그레이션 의존이 없어 단독 cherry-pick 가능해 보이나, 착수 전 재확인한다.

## 5. 근거 품질 (T1·T2 공통)

복원 신뢰도는 근거 층에 달려 있다.

| confidence | 근거 | 현재 확보 |
|---|---|---|
| `exact` | 사고 직전 DB 사본 | PITR fork 필요(수동). **오프사이트 논리 백업이 6시간 주기가 되면 상시 확보** |
| `logged` | `security_logs.detail.before` / `order_field_changes.before_value` | 상시 |
| `event` | `order_events` `from_status` | 상시 |
| `inferred` | AS 이벤트 유도 | 상시(사람 확인 필요) |

오프사이트 백업은 2026-08-19 에 되살아났고(일 1회), 주기를 6시간으로 줄이면 `exact` 가
fork 없이도 상시 근거가 된다. T3 로 분리.

## 6. 검증

- 단위: 화이트리스트 밖 400 / 절단 값 400 / 현재값 불일치 409 / 정상 200 후 값 복원 + 새 원장 행 1건
- 계약: `RESTORABLE_PATHS ⊆ SCALAR_PATHS`, 요청 스키마에 path 계열 필드 부재
- 통합(스테이징 실브라우저): 실측일 변경 → 이력에서 되돌리기 → 원값 복귀 + 이력 2행 + 사유 표시
- 인벤토리: mutation writer 인벤토리에서 신규 쓰기가 `CANONICAL` 로 분류되는지(EXTERNAL 증가 0)

## 7. 위험

1. **임의 write primitive 재도입** — `change_id` 만 받는 설계로 차단. 리뷰 시 이 지점을 최우선으로 본다.
2. **파생값 불일치** — v1 화이트리스트에서 파생·연동 축을 전부 뺐다(§3.4).
3. **복원의 복원** — 복원도 원장 행을 남기므로 그 행을 다시 되돌릴 수 있다. 무한 왕복은
   현재값 대조(§3.3-3)가 자연히 막는다(되돌린 직후의 현재값 = 그 행의 after).
4. **권한 오판** — 본인 변경 되돌리기는 허용하되, 화이트리스트가 좁아 피해 범위가 일정 축으로 제한된다.

## 8. 단계

| 단계 | 내용 | 마이그레이션 |
|---|---|---|
| T1 | 필드 단위 되돌리기 + 주문 상세 이력 탭 | 없음 |
| T2 | `/admin/data-doctor` + OPS-APPROVAL + 롤백 | 1개 |
| T3 | 오프사이트 백업 6시간 주기 → `exact` 상시화 | 없음 |
