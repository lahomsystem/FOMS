# 주문 변경 기록 사각 메우기 — 진행 원장 (AUDIT-GAP-01)

- **작성**: 2026-08-26 / **CEO 설계 리뷰 반영**: 2026-08-26
- **베이스**: `origin/deploy` `222222a8`, 브랜치 `session/audit-gap-fill`, 트리 `C:\tmp\foms-audit-gap`
- **선행**: ORDER-FLAG-01(`8b7692b2` deploy / `0c8095fd` production) — `flags.factory2`·`is_regional`·`construction_type` 3종 처리 완료

## 문제

`order_field_changes` 원장은 `structured_diff.SCALAR_PATHS` **화이트리스트**만 본다. 운영 실측(2026-08-26):

- 원장 5,658행 / 주문 321건 = 전체 4,022건의 **8%**
- 관측창 내 구조화 저장 1,810건 중 원장 changeset 813건 → **저장 2건 중 1건 이상 무기록**(무변경 저장 포함 상한)
- `record_field_changes` 호출부는 **3곳(2파일)** 뿐

구멍은 두 계통이다: ① 화이트리스트에 없는 값 ② 화이트리스트에 있어도 그 화면이 원장을 안 부름.

## 작업 분할 — 파일 소유권 (동시 편집 충돌 방지)

각 task 는 **자기 파일만** 편집한다. 표에 없는 파일을 고쳐야 하면 BLOCKED 로 적고 멈춘다.

| task | 소유 파일 | 다루는 구멍 |
|---|---|---|
| T1 | `foms/api/erp_orders_structured.py` | 자가실측·주문비고(컬럼)·접수일·접수시간 |
| T2 | `foms/services/orders/structured_diff.py`, `foms/services/audit_message_display.py` | 잔금비고·AS내용·현장특이(요약) + **전 task 라벨/표기 등재** |
| T3 | `foms/web/orders/edit.py` | 주문수정폼 구조화 감사 + 평면 컬럼 emit |
| T4 | `foms/api/orders/field_update.py`, `foms/api/shipment/settings.py`, `foms/web/admin/storage.py` | 타 화면 원장 연결 + 배송비/수납장 before 복원 |
| T4b | `foms/api/orders/regional.py` | 지방 체크리스트 6종 **실사용 정본 경로** |

### 공용 파일 규칙
- `docs/harness/*inventory*.json` — **task 가 손대지 않는다.** T5 가 일괄 재생성.
- 테스트는 **task 별 새 파일**에 쓴다(기존 테스트 파일 동시 편집 금지).
- 자산 `?v` 핀 범프가 필요하면 원장에 적고 T5 가 처리.

### 라인 핀 인벤토리 규약 (필독 — 오해하면 사고)
`tests/domains/test_rev_99.py::test_no_new_external_writers` 와 `test_state_guard.py::test_no_new_external_writers` 는 EXTERNAL 사이트를 **`(path, lineno, kind)` 로 대조**한다(`test_rev_99.py:199-206` 확인). 아래 task 는 **편집만으로** 이 게이트를 red 로 만든다:

| task | 파일 | 핀 lineno |
|---|---|---|
| T1 | `erp_orders_structured.py` | state 313, 877, 2172, 2245 |
| T3 | `edit.py` | writer 268 |
| T4 | `field_update.py` | writer 597 / state 436, 437 |

**이 red 는 정상이다. BLOCKED 아니다. 인벤토리를 손대지 마라.** T5 가 `state_writer_scan.py`·`order_mutation_writer_scan.py` 로 한 번에 재생성한다.

### 금지 사항
- `record_field_changes` 는 **이미 fail-open** 이다(`order_field_change_writer.py:143`). 호출부에서 try/except 로 다시 감싸지 마라 — failopen 인벤토리에 신규 broad catch 가 잡혀 별개로 red.
- **새 감사 action 코드를 만들지 마라.** 기존 재사용: `ORDER_STRUCTURED_SAVED`·`ORDER_FIELD_UPDATED`·`ORDER_CHECKLIST_UPDATED`·`STORAGE_SETTING_UPDATED`.

## 경로·기록 규약 (전 task 공통)

1. 평면 컬럼은 **점 없는 컬럼명**을 원장 `path` 로 쓴다(ORDER-FLAG-01 확정 규약). sd 경로는 점 경로 그대로.
   - 안전 확인 완료: `path_template_of` 는 품목 아니면 원본 반환, `path_label` 은 미등재 시 경로 원문, `field_restore` 는 `RESTORABLE_PATHS` 화이트리스트 체크가 `write_path` **앞**이라 평면 path 는 400 거부 → 없는 sd 키를 만들 위험 0.
2. `change_set_id` 는 각 task 가 **`str(uuid.uuid4())` 인라인**. `erp_orders_structured._new_change_set_id` 는 private, 이동 금지.
3. 원장 행을 쓰는 곳은 그 감사 헤더 `log_access(detail=...)` 에 **반드시 `'change_set': <같은 id>`** 를 넣는다 — 관리자 감사 화면이 `detail->>'change_set'` 으로 조인한다(`foms/web/admin/audit.py:137`).
4. 원장 쓰기는 **반드시 `db.commit()` 이전**(같은 트랜잭션).
5. **라벨은 T2 가 전부 등재한다.** 다른 task 는 `audit_message_display.py` 를 건드리지 않는다.
6. **테스트 단언 경계**: T1·T3·T4·T4b 테스트는 "원장 행이 `path=X` 로 `before/after` 와 함께 생겼다"까지만 단언한다. **`path_label` 단언은 T2 테스트 전용** — 다른 task 에 넣으면 T2 미착지 시 인위적 red 가 되어 병렬성이 죽는다.

### 라벨·표기 표 (T2 가 등재)

| 원장 path | `PATH_LABELS` | `_PATH_VALUE_FIELD` | emit 담당 |
|---|---|---|---|
| `is_self_measurement` | 자가실측 | `is_self_measurement`(체크리스트 표기) | T1 |
| `order_notes` | **주문 비고** | — | T1 |
| `received_date` | 접수일 | — | T1 |
| `received_time` | 접수시간 | — | T1 |
| `payment.balance_note` | **잔금 비고** | — | T2 |
| `shipment.as_content` | AS 내용 | — | T2 |
| `shipment.site_extra` | 현장 특이사항 | (요약 처리, 아래 참조) | T2 |
| `is_cabinet` | 수납장 | `is_cabinet` | T3 |
| `cabinet_status` | 수납장 상태 | — | T3·T4 |
| `shipping_fee` | 배송비 | — | T4 |
| `payment_amount` | 결제금액 | — | T3 |
| `completion_date` | 설치완료일 | — | T3 |
| `as_received_date` | AS 접수일 | — | T3 |
| `as_completed_date` | AS 완료일 | — | T3 |
| `shipping_scheduled_date` | 상차 예정일 | — | T3 |
| `options` | 옵션 상세 | — | T3 |
| `status` | 상태 | `status` | T3 |
| `regional_sales_order_upload` | 영업발주 업로드 | 체크리스트 표기 | T3·T4b |
| `regional_blueprint_sent` | 도면 발송 | 체크리스트 표기 | T3·T4b |
| `regional_order_upload` | 발주 업로드 | 체크리스트 표기 | T3·T4b |
| `regional_cargo_sent` | 화물 발송 | 체크리스트 표기 | T3·T4b |
| `regional_construction_info_sent` | 시공정보 발송 | 체크리스트 표기 | T3·T4b |
| `measurement_completed` | 실측완료 | 체크리스트 표기 | T3·T4b |

**`order_notes` 이름 근거**: `PATH_LABELS["notes"]="비고"` 가 이미 있고(`audit_message_display.py:310`) 그건 `sd.notes` **객체**(phone/address/measurement/construction 4칸)다. `Order.notes` 컬럼은 별도 textarea("주문 비고", `erp_order_tab.html:227`)이고 `sync_erp_flat_columns` 가 동기화하지 않는 독립 값이다. 같은 path 를 쓰면 서로 다른 두 필드가 한 이력으로 합쳐진다.

**`payment.balance_note` 는 변경 사유 모달을 띄우지 않는다(확정)** — `is_reason_required` 는 `AMOUNT_PATH_TEMPLATES`·`CONSTRUCTION_SCHEDULE_TEMPLATES`·`STAGE_TEMPLATES` 3집합만 보고 `balance_note` 는 어디에도 없다.

**`shipment.site_extra` 는 단순 화이트리스트 추가 금지** — `{text,color}` dict 최대 20개·text 500자 리스트라 `_clip` 120자 절단 후 **before==after 로 보이는 행**이 된다. `spec_rows` 선례(`_spec_rows_summary`)처럼 **T2 가 요약("특이사항 N건")으로** 다룬다.

## 범위 밖 (이번에 하지 않는다 — 명시적 제외)

- **`schedule.as_visit.availability`** — 폼 JS 가 `schedule` 을 `{measurement, construction}` 만 보내는데 `schedule` 은 deep-merge 보존 목록(`erp_orders_structured.py:501` = `('workflow','assignments','shipment','meta','parties')`)에 **없다**. 그래서 AS 주문을 ERP 폼으로 저장할 때마다 `as_visit` 이 통째 소실된다. 이 상태로 등재하면 **저장 1회에 허위 '지움' 행**이 쌓인다. 보존 수정이 선행돼야 하고 그건 데이터 동작 변경이라 **사용자 결정 사항**. 별건.
- **`edit.py` 의 `customer_name`·`phone`·`manager_name`·`product`** — sd 쌍둥이(`parties.customer.name` 등)가 이미 원장에 있어 평면으로 또 넣으면 **경로 2벌**이 되어 감사 화면 `path_template` 필터가 반쪽만 잡는다. 별건.
- **자가실측 권한 게이트** — 기록만 넣는다. 누가 켜고 끌지는 사용자 결정.
- `manager_name` 컬럼 ↔ `parties.manager.name` **1,037건 불일치** — 데이터 정합, 별건.
- 되돌리기(`field_restore`) 화이트리스트 확대 — bool·메모류는 복원 대상 아님.

## Task 원장

완료 기준 = **검증 명령 통과**. 오케스트레이터가 diff 직접 확인 + 테스트 직접 실행 후에만 DONE.

| task | 상태 | 완료 기준(검증 명령) |
|---|---|---|
| T0 CEO 설계 리뷰 | **DONE** (수정 후 진행 — 본 원장에 반영 완료) | 판정 리포트 |
| T1 PUT 평면 컬럼 | **DONE** (오케스트레이터 직접 검증: 31 passed, diff 범위 소유파일 1개 확인, 스냅샷이 setattr 앞 확인, 옛 시그니처 호출부 잔재 0) | `pytest tests/domains/test_audit_gap_flat_columns.py` + `python -c "import app"` |
| T2 화이트리스트·라벨 | **DONE** (직접 검증: 137 passed. 본체 + 후속 4건(cabinet_status 한글화·FIELD_LABELS 3종·regional_memo 라벨) 반영. site_extra 는 요약 축 분리로 SCALAR_PATHS 미등재 = 이중기록 없음 확인) | `pytest tests/domains/test_audit_gap_paths.py tests/domains/test_structured_diff.py tests/domains/test_audit_message_display.py tests/domains/test_field_restore.py` |
| T3 주문수정폼 감사 | **DONE** (직접 검증: 28 passed. sd 변경은 canonical sd 경로, 평면은 쌍둥이 없는 컬럼만. 후속으로 플래그 3종 합류 + 무권한 게이트 시 0행 계약 고정) | `pytest tests/domains/test_audit_gap_edit_form.py` |
| T4 타 화면 원장 연결 | **DONE** (직접 검증: 14 passed. `_LEDGER_SD_TWIN` 으로 경로 2벌 방지, storage before 를 row lock 안에서 포획) | `pytest tests/domains/test_audit_gap_other_surfaces.py` |
| T4b 지방 체크리스트 정본 | **DONE** (직접 검증: 22 passed, diff 범위 `regional.py` 1개, 원장 쓰기가 `_mutate` 안 = replay 유령행 방지 확인. `regional_memo` 추가 처리 — T2 라벨 필요) | `pytest tests/domains/test_audit_gap_regional.py` |
| T5 통합 검증 | **DONE** (라벨 3건 보충, 인벤토리 4종 재생성=줄번호만, 게이트 55 passed, pre_push_smoke exit 0, 전체 domains+contracts **5276 passed / 5 skipped**) | 인벤토리 재생성 + `pre_push_smoke` exit 0 + CI green |
| T6 CEO 최종 판정 | **DONE** — 스펙 준수 **합격** / 코드 품질 **조건부 합격**. 차단 1건 수정 완료(아래) | 스펙 준수·코드 품질 2판정 |
| T7 차단 결함 수정 | **DONE** (직접 재현→수정→회귀테스트가 실제로 red↔green 하는지 확인) | `pytest tests/domains/test_audit_gap_regional.py` |

## 검증 무신뢰 규율

서브에이전트 "완료" 보고는 주장일 뿐이다. 오케스트레이터가 `git diff` 로 실제 변경을 보고, 검증 명령을 **직접** 돌린 뒤에만 원장을 DONE 으로 바꾼다.


## T6 CEO 최종 판정 결과 (2026-08-26)

**판정 1 스펙 준수 = 합격.** 경로·기록 규약 6개조가 5개 파일 전부에서 지켜짐. 금지사항 위반 0(try/except 감쌈 0건, 신규 action 0건). 범위 밖 준수 확인. emit 경로 **70개 전부 라벨 등재**.

**판정 2 코드 품질 = 조건부 합격** → 차단 1건 수정 후 합격.

### 차단 결함 (수정 완료)
- **`regional.py` 지방 메모 판정이 120자 절단값으로 이뤄져 121자 이후 변경이 무기록.** 메모 상한 2000자라 흔한 모양이고, 잔금 조건·열쇠 보관처처럼 분쟁 소재가 뒤쪽에 적힌다. 감사 헤더는 남는데 원장 0행 → "기록 없음"이 "안 바뀜"으로 오독된다. **이 PR 이 새로 만든 무기록**이었다.
  - 수정: 판정은 절단 전 원문으로, 저장 표현만 `ledger_text`. 절단으로 표시값이 같아지면 `(내용 수정)` 표식(= `structured_diff` 의 site_extra 선례).
  - 회귀 테스트 2건 추가. **수정을 되돌리면 red, 복원하면 green** 을 실제로 확인.

### 후속 별건 (비차단 — 이번 범위에 넣지 않음)
1. **`status` 축 2벌** — `edit.py`(자기 path 유지) vs `field_update.py`(`workflow.stage` 로 twin 억제)가 상반된 결정. 감사 필터가 반쪽만 잡는다. 축 통일 + 테스트에 path 명시 고정 필요.
2. **`options`·`shipment.as_content` 절단 충돌** — 표시값이 `A → A` 로 보이는 행. site_extra 처럼 요약 축 또는 `(내용 수정)` 표식 적용.
3. **`as_orders.py:637`(AS 본문 쓰기)에 원장 미배선** — 계획 자체의 구멍. `shipment.as_content` 를 등재했지만 실제 쓰는 경로가 어느 task 소유도 아니었다.
4. **평면 diff 로직 4~5벌 중복** — `flat_ledger.py` 로 공통화 권고. 절단 유무·`_is_unset` 유무가 파일마다 갈렸고 결함이 정확히 그 자리에서 났다.
5. `settings.py`·`storage.py` 원장 쓰기를 `_mutate` 안으로 이동(IntegrityError backstop 경로의 유령 행 창).
6. `test_audit_gap_flat_columns.py` 무변경 테스트 5개에 `status_code` 단언 추가.
7. `change_set` 을 헤더에 넣는 조건이 4:2 로 갈림(무조건 vs `if recorded_rows`). 통일.

### T8 후속 2건 추가 처리 (사용자 지시, 2026-08-26)
- **`status` 축 통일** — `field_update.py` 의 `_LEDGER_SD_TWIN` 에서 `status` 제거. 근거: `order.status` 와 `workflow.stage` 는 일부러 분리된 두 축이다(`stage_override.as_overlay_status` docstring 이 SSOT — AS 접수 주문은 status 가 AS 로 바뀌어도 stage 는 MEASURE 로 남는다). 쌍둥이로 묶으면 한 저장에서 함께 바뀐 두 값 중 하나가 사라진다. 테스트도 `path in (...)` 느슨한 집합에서 `status` 로 못 박음.
- **AS 방문 일정 보존 + 가능시간 등재** — `_preserve_operational_structured_state` deep-merge 목록에 `schedule` 합류. 폼이 measurement/construction 의 date·time 키를 항상 보내므로 값 비우기는 그대로 동작하고 as_visit 만 보존된다. **보존을 먼저 고친 뒤** `schedule.as_visit.availability` 를 등재했다 — 순서를 뒤집으면 저장 1회마다 허위 '지움' 행이 쌓인다(되돌려 실증: 보존 없이 3건 red).
- 두 수정 모두 **회귀 테스트가 실제로 red↔green 하는지 확인**(가짜 통과 배제).
- T2 의 "범위 밖" 가드 테스트는 삭제하지 않고 **계약을 뒤집어 보존** — 등재 순서(보존 먼저)를 계속 지키게 한다.

### 최종 검증 (2026-08-26)
- 신규 테스트 6파일 + 기존 계약: **148 passed**
- 전체 `tests/domains` + `tests/contracts`: **5283 passed / 5 skipped / 0 failed**
- `pre_push_smoke`: exit 0
- 인벤토리 4종 재생성: 카운트 불변, diff 는 줄번호만

### T9 스테이징 실화면 QA (2026-08-26, lahom-dev 주문 4491)
`574ceeef` 배포 후 실화면 확인. **전 항목 통과, 테스트 주문 원상복구 완료.**

| 확인 | 실제 원장 문장 |
|---|---|
| 자가실측(화면 클릭→저장) | `자가실측 해제 → 완료` |
| 접수일 | `접수일 2026-08-26 → 2026-08-20` |
| 접수시간 | `접수시간 11:44 → 09:30` |
| 주문 비고 | `주문 비고 (없음) → CLAUDE-TEST 감사확인용 비고` |
| 잔금 비고 | `잔금 비고 (없음) → 잔금 계좌이체 확인 요망` |
| AS 방문 가능시간 | `AS 방문 가능시간 (없음) → 평일 · 오전` |

- **"완료/해제"** 로 읽힘(예/아니오 아님) — `_CHECKLIST_FIELDS` 합류가 실화면에서 확인됨.
- **"주문 비고"** 로 읽힘 — sd 의 `notes`("비고")와 경로가 섞이지 않음.
- **"평일 · 오전"** 으로 읽힘 — `_PATH_VALUE_FIELD` 위임이 동작(JSON 원문 노출 없음).
- **AS 방문일정 보존**: as_visit 을 넣어두고 화면 저장 버튼 → `as_visit_survived: true`, 허위 '지움' 행 0.

**부수 확인된 동작 변화**: 보존 수정 이후 `as_visit` 을 payload 에서 **빼면 안 지워진다**(= 의도한 동작). 지우려면 `{date:'', time:'', availability:null}` 처럼 **명시적 빈 값**을 보내야 하고, 실제로 그렇게 하면 지워진다. 실수 유실은 사라졌고 의도적 삭제 경로는 살아 있다.

지방 체크리스트 6종은 실화면 대신 계약 테스트로만 확인(주문을 지방으로 바꿔야 해 실데이터 조작 범위가 커진다) — `test_audit_gap_regional.py` 24 passed.

**CI**: `574ceeef` 4/4 green (FOMS CI · PG Lane · Harness CI · perf-gate).
**잔여**: 운영 승격 미실행 + 후속 별건 5건(위 T6 목록).
