# 감사 로깅 이월 과제 계획 (2026-08-08)

> **진행 상태 (2026-08-08 갱신)**
> | 과제 | 상태 | 결과 |
> |---|---|---|
> | C2 `access_logs` JSONB 승격 | **DONE** | `accesslog_detail_00` — domains 4203·PG 719·APP_OK |
> | C1 `security_logs` 정렬 인덱스 | **DONE** | `seclog_time_00` — PG EXPLAIN 으로 Sort 제거 실증(대조 테스트 포함) |
> | C3-a 트리아지 | **DONE** | `docs/plans/2026-08-08-external-writer-triage.md` — 22곳 전부 판정 |
> | C3-b 재분류 | **DONE** | EXTERNAL 22 → **19** (17 아님 — 사유는 트리아지 문서 "C3-b 로 실제로 낮출 수 있는 수") |
> | C3-c 패킷 전환 | 미착수 | 트리아지 §C3-c 권장 순서대로 **패킷별 별건 승인** 필요 |
>
> **계획 대비 편차 1건**: 아래 C3-b 완료 기준은 "`baselines.external` 이 판정표 A군 수와
> 정확히 일치"였으나, 실제 도달값은 19(A군은 17)다. 생성기 분류가 **경로 단위**라
> `quest_transition_service.py`(B+사문 혼재)와 `blueprint_projection.py`(A/B/C 호출자 혼재)를
> 안전하게 등재할 수 없기 때문이다. 억지로 맞추려면 A 경로까지 면제되어 게이트가 거짓말을 한다.


선행 정본: 스펙 `docs/specs/2026-08-05-system-audit-logging-design.md` /
플랜 `docs/plans/2026-08-05-system-audit-logging-plan.md` /
원장 `docs/plans/2026-08-05-system-audit-logging-ledger.md` /
보존기간 분석 `docs/plans/2026-08-07-audit-retention-analysis.md` /
인수인계 `docs/harness/runtime/HANDOFF_AUDIT_LOGGING.md`

기준 커밋: `origin/deploy` = `3782b11f` (CI 4/4 green — FOMS CI·Harness·PG Lane·perf-gate).
alembic 단일 head = `auditlife_00` (T9, `migrations/versions/auditlife_00_order_events_fk_drop.py`).

> **작업 전 필수 — 로컬 워킹트리 낙후**
> 로컬 `deploy` 는 `origin/deploy` 보다 21커밋 뒤이고, 이월 과제가 건드릴
> `foms/web/admin/audit.py`·`foms/services/user_deletion.py` 등 6파일 771줄이 로컬에 없다.
> 구현은 **`origin/deploy` tip 기준 워크트리**(`python tools/harness/session_worktree.py create`,
> 또는 `c:/tmp` 짧은 경로)에서 시작한다. 로컬 tip 에서 시작하면 T12 코드를 지우는 diff 가 나온다.

---

## 배경 실측 (재조사 결과, 2026-08-08)

| 항목 | 실측값 | 출처 |
|---|---|---|
| `security_logs` 인덱스 | `ix_security_logs_target`(target_type, target_id, timestamp) + `ix_security_logs_message_trgm`(GIN). **timestamp 선행 인덱스 없음** | `models.py:1016-1018` (origin/deploy) |
| `security_logs` 규모 | 24,572행 / 20.64 MB / 71.9행일 (승격 후 추정 95행일) | 보존기간 분석 표 A |
| `access_logs` 인덱스 | `ix_access_logs_user_id_timestamp`, `ix_access_logs_timestamp` | `models.py:973-976` |
| `access_logs` 규모 | **119행 / 0.09 MB / 0행일 (휴면)** — 승격 후 추정 150행일 | 보존기간 분석 표 A |
| `access_logs.additional_data` | `Column(Text)` — JSON **문자열** | `models.py:983` |
| 운영 DB 적용 상태 | `seclog_struct_00`(T8)·`access_log_00`(T6) **모두 미적용** — 운영엔 감사 화면 스키마 자체가 없다 | 보존기간 분석 §서두 |
| EXTERNAL mutation writer | 22곳 / 16파일 / owner 패킷 11종, 전부 `kind=flag_modified_structured_data` | `docs/harness/foms_order_mutation_writer_inventory.json` (`baselines.external=22`) |

핵심 판단 재료 2가지:

1. **`access_logs` 가 아직 119행 휴면이다.** JSONB 전환의 백필 비용이 지금은 사실상 0.
   승격 후엔 150행/일로 켜지므로 1년 뒤엔 5.5만행 백필 + 락. **저비용 창은 승격 전 지금뿐.**
2. **`security_logs` 24k행은 지금 당장 느리지 않다.** Seq Scan 이 수 ms 수준.
   인덱스는 3년 보존(≈10만행) 대비 예방 조치이고, 비용이 작아 같은 창에서 처리하는 게 낫다.

---

## 권장 순서와 이유

```
C2 (access_logs JSONB)  →  C1 (security_logs 인덱스)  →  C3-a/b (트리아지·재분류)  →  C3-c (패킷별 전환)
   승격 전 유일한 저비용 창        같은 마이그레이션 창에서 동반        코드 위험 0, 게이트만            패킷별 별건 승인
```

C1·C2 는 둘 다 alembic revision 이라 한 세션에서 연속 처리하되 **revision 은 분리**(롤백 단위 보존).
C3 는 성격이 다르고 프론트 계약(If-Match/409/428)까지 번질 수 있어 별건으로 뗀다.

---

## C1 — `security_logs` 정렬 인덱스

**문제.** 감사 화면 기본 조회가 `ORDER BY timestamp DESC, id DESC` +
`count(*)` 인데(`foms/web/admin/audit.py:186,191`), 존재하는 인덱스는 선행 컬럼이
`target_type` 이라 정렬에 쓸 수 없다. GIN trgm 은 `message` 전용. 결과: 매 페이지 Seq Scan + Sort.

**설계.**
- 단독 `timestamp` 가 아니라 **`(timestamp, id)` 복합 btree**를 만든다.
  화면 정렬 키가 `timestamp DESC, id DESC` 이므로 tie-break 까지 인덱스 하나로 해결되고,
  PG 가 backward index scan 으로 DESC 를 처리한다(별도 DESC 인덱스 불필요).
- 이름: `ix_security_logs_timestamp_id`.
- `models.py` `SecurityLog.__table_args__` 와 마이그레이션에 **같은 이름·같은 컬럼 구성**으로 추가.
  (SEC-LOG-STRUCT-00 주석이 명시한 규약 — create_all 부트스트랩 레인과 alembic 레인 정합을
  `tests/postgres` 체인 왕복 테스트가 강제한다.)
- 마이그레이션: 신규 revision, `down_revision = 'auditlife_00'`. `downgrade()` 는 `drop_index`.
- **`CONCURRENTLY` 쓰지 않는다** — alembic 이 트랜잭션 안에서 실행하므로 불가하고,
  24k행이면 `CREATE INDEX` 락이 1초 미만이다.
- 기존 `ix_security_logs_target`·trgm 인덱스는 무접촉.

**완료 기준.**
- `pytest tests/postgres -q` green (체인 왕복 + 스키마 정합).
- 로컬 PG 레인에서 `EXPLAIN` 상 화면 기본 조회의 `Seq Scan on security_logs` 소멸 —
  before/after 를 원장에 실측 기록(추정치 금지).
- `python -c "import app; print('APP_OK')"` + `scripts/ops/pre_push_smoke.ps1` exit 0.

**리스크.** 낮음. 읽기 경로만 영향, 추가 디스크 ≈ 1 MB(24k행 btree 2컬럼).

---

## C2 — `access_logs` 주문 축 조회를 JSONB 로

**문제.** T12 주문번호 필터가 JSON **문자열** LIKE 2종 OR 이다
(`audit.py:116-119`, `'%"order_id": {id},%'` / `'%"order_id": {id}}%'`).
인덱스를 쓸 수 없어 전체 스캔이고, 구분자를 손으로 붙여 접두 오탐(주문 12 ↔ 123)을 막고 있다 —
정확하지만 취약한 계약이다. 파일 키 필터도 `ilike` 전체 스캔.

**설계 — T8 `security_logs.detail` 선례를 그대로 따른다.**
- `additional_data`(Text) 를 **in-place `ALTER TYPE jsonb` 하지 않는다.**
  비-JSON 행 1건만 있어도 마이그레이션이 파산하고, 과거 writer 의 자유 형식을 신뢰할 수 없다.
- 대신 **신규 컬럼 `detail JSONB nullable`** 추가 + 백필 + writer 전환 + 읽기 폴백.
  T8 이 `security_logs` 에서 이미 검증한 패턴이라 새 위험이 없다.
- 백필: 119행 → 마이그레이션 안에서 1회 처리. 파싱 실패 행은 `detail = NULL` 로 남기고
  **원문 `additional_data` 는 보존**(감사 원장은 원문을 지우지 않는다).
- 인덱스: `Index('ix_access_logs_detail_order_id', text("((detail->>'order_id'))"))` btree.
  주문 축 단일 조회만 필요하므로 GIN jsonb_path_ops 보다 싸다.
  (파일 키 `ilike` 는 감사 화면 cold path 로 남기고 인덱스 만들지 않는다 — 현 규모에서 불필요.)
- 화면: `_apply_access_log_filters` 의 주문 분기를
  `AccessLog.detail['order_id'].astext == str(order_id)` 로 교체.
  **기존 계약 테스트 13건은 그대로 통과해야 한다** — 특히 접두 오탐 가드(12↔123)는
  구현이 바뀌어도 의미가 유지되는지 확인하는 회귀 앵커다. 삭제 금지.
- writer(`foms/services/audit/…` 파일 접근 기록)는 `detail` 에 dict 를 쓰고
  `additional_data` 는 과도기 동안 병기(이중 쓰기) → 승격 후 별건으로 단일화.

**완료 기준.**
- 기존 `tests/domains/test_file_access_log_screen.py` 13건 무수정 green.
- 신규: 백필 왕복 테스트(마이그레이션 upgrade→downgrade→upgrade), 비-JSON 행 내성 테스트,
  JSONB 경로 접두 오탐 테스트.
- `pytest tests/postgres -q` green(SQLite 레인은 JSONB 미지원이라 PG 레인이 정본).
- `APP_OK` + smoke exit 0.

**리스크.** 중. 컬럼 추가·백필이지만 대상 119행. 롤백은 `drop_column` 으로 완전 가역
(원문 Text 컬럼을 남기므로 데이터 손실 0).

**타이밍이 이 과제의 전부다.** 승격 후로 미루면 백필 대상이 5만행대로 커진다.

---

## C3 — EXTERNAL mutation writer 22곳 감축

**문제.** 인벤토리 릴리스 타깃은 `EXTERNAL == 0`
(모든 주문 mutation 이 version bump + If-Match/idempotency 를 동반).
현재 22곳이 직접 `flag_modified(order, 'structured_data')` 로 쓴다.

**22곳 owner 분포 (실측):**

| owner 패킷 | 곳 | 파일 |
|---|---|---|
| STATE-DRAWING-01 | 4 | `foms/api/drawing/erp_orders_draftsman.py`:106,244,390 · `foms/services/notifications/drawing_order_change.py`:1019 |
| STATE-CONST-CS-01 | 4 | `foms/api/cs/complete.py`:147 · `confirm.py`:65 · `dashboard.py`:348,434 |
| DRAWING-REVISION-BACKFILL-00 | 3 | `foms/api/drawing/erp_orders_revision.py`:118,332,477 |
| STATE-QUEST-01 | 3 | `foms/api/quest.py`:417 · `foms/services/orders/quest_transition_service.py`:142,294 |
| STATE-LEGACY-01 | 2 | `foms/api/orders/field_update.py`:576 · `foms/api/orders/status.py`:216 |
| EVENT-REVERT-01 | 1 | `foms/api/events.py`:418 |
| WDC-LINK-01 | 1 | `foms/api/wdcalculator/blueprint.py`:1174 |
| DATA-01 | 1 | `foms/services/order_geocode.py`:87 |
| QUEST-BACKFILL-00 | 1 | `foms/services/orders/backfill_order_quests.py`:145 |
| BLUEPRINT-01 | 1 | `foms/services/orders/blueprint_projection.py`:137 |
| ORDER-CREATE-01 | 1 | `foms/web/orders/edit.py`:257 |

**일괄 전환은 불가하다.** 22곳의 성격이 3종으로 갈린다:

- **(A) 진짜 미보호 mutation** — HTTP 요청이 직접 주문을 바꾸는데 version/If-Match 가 없다.
  `execute_order_mutation` 전환 대상. 전환하면 응답에 409/428 계약이 생기므로
  **프론트 동반 수정이 필요할 수 있다.**
- **(B) canonical 안에서 불리는 helper** — 예: `order_geocode.py:87`
  `set_order_address()` 는 docstring 에 "db.commit() 호출하지 않음, 호출자 소유"라고 명시된
  순수 helper다. 호출자가 이미 canonical 이면 이 사이트는 **분류 오류**이지 결함이 아니다.
  → 인벤토리 생성기의 분류 규칙 문제로 처리한다.
- **(C) 오프라인 배치/보정** — `backfill_order_quests.py`·`erp_orders_revision.py` 의 backfill
  계열. `AUDITED_RECOVERY` 재분류가 맞는지 판정.

**단계 설계.**

### C3-a. 트리아지 (코드 변경 0)
22곳 각각 호출자를 추적해 A/B/C 판정표를 만든다. 각 행에 판정 근거(호출자 경로:라인)를 적는다.
- 완료 기준: `docs/plans/2026-08-08-external-writer-triage.md` 에 22행 전부 판정 + 근거 기재.
  판정 없는 행 0. **코드·인벤토리 파일 무변경**(diff 는 문서 1개만).

### C3-b. B·C 재분류 (게이트 작업)
생성기에 "canonical 호출자 안의 helper" 인지 규칙을 넣거나, 사이트별 pin 을 owner 패킷에 등재.
인벤토리 재생성 후 `baselines.external` 을 실제 A군 수로 낮춘다.
- **주의**: 인벤토리 파일은 타 세션 점유 이력이 있고 지금도 로컬에 미커밋 2줄 변경이 있다
  (`git diff -- docs/harness/foms_order_mutation_writer_inventory.json`).
  재생성 전 클린 상태 확인 필수. 커밋은 `git commit -F msg -- <경로>` 로 경로 한정.
- 완료 기준: `pytest tests/harness -k inventory` green, 드리프트 게이트 5종 green,
  smoke exit 0, `baselines.external` 이 판정표 A군 수와 정확히 일치.

### C3-c. A군 전환 (패킷 단위, 각각 별건 승인)
owner 패킷 1개 = 커밋 1개. 큰 패킷부터가 아니라 **위험 낮은 패킷부터**:
`EVENT-REVERT-01`(1곳, 이미 보상 트랜잭션 문맥) → `BLUEPRINT-01` → `WDC-LINK-01` →
`STATE-LEGACY-01` → `STATE-QUEST-01` → `STATE-CONST-CS-01` → `STATE-DRAWING-01`.
- 각 패킷 완료 기준: 해당 API 의 409(version 불일치)·428(If-Match 누락) 계약 테스트 신규,
  기존 도메인 테스트 무회귀, 프론트 호출부가 `If-Match`/`Idempotency-Key` 를 보내는지 실브라우저 확인,
  `pytest tests/postgres -q` green, smoke exit 0.
- **C3-c 는 이 계획의 승인 범위에 넣지 않는다.** C3-a 판정표를 보고 패킷별로 다시 결정한다.

---

## 승인 요청 범위

이번 승인으로 착수할 것: **C2 → C1 → C3-a → C3-b**.
`C3-c`(실제 코드 전환)는 C3-a 판정표를 사용자가 본 뒤 패킷별로 별도 승인.

미결 확인 1건: C2 의 writer 이중 쓰기(`additional_data` + `detail` 병기) 유지 기간을
"승격 후 별건 단일화"로 둘지, C2 안에서 바로 단일화할지 — 전자를 권한다
(승격 롤백 시 옛 코드가 읽을 원문이 남아야 한다).
