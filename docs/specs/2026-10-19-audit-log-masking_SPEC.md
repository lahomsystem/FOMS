# 감사 기록 고객 개인정보 가림 — 기록을 쓰는 한 지점에서 — SPEC (2026-10-19)

## 목적
`security_logs`(감사·보안 기록, 보존 3년)에 고객 전화번호·주소·이름이 원문 그대로 쌓이는 것을 막는다.
2026-08-07 운영 실측(`docs/plans/2026-08-07-audit-retention-analysis.md` §6)에서 메시지의 12.6% 에
휴대전화번호, 11.8% 에 주소 형태 문자열이 있었다. 2026-09-06 시스템 검토가 "기록할 때 가리는 장치를
강제하는 곳이 없다" 고 지적했고 아직 미해결이다.

호출부(170여 곳)를 하나씩 고치지 않는다. 기록이 실제로 저장되는 길목에서 한 번 가린다.
누가 무엇을 바꿨는지 알아볼 수 있는 정도(바뀐 칸 이름, 주문 번호, 행위자)는 남긴다.

## 지금 구조
- 모델: `SecurityLog`(`models.py:1375`) — `message`(사람용 문장) + `action`·`target_type`·`target_id`·`detail`(JSONB).
  모델 docstring 은 "detail 에 PII 원문 금지" 라고 적었지만 강제하는 코드가 없다.
- 저장 길목(물리)은 네 가지다.
  1. ORM `SecurityLog(...)` 생성 → 세션 flush. `log_access`(`foms/web/auth/routes.py:80`) 본체가 여기에 속하고,
     그 밖에 `db.add(SecurityLog(...))` 직접 쓰기가 27곳 있다.
  2. Core insert — `write_security_log_detached`(`foms/services/audit_writer.py:191`). 접근거부 기록
     `record_access_denied` 가 이 길을 쓴다(본 요청 트랜잭션과 무관하게 즉시 커밋).
  3. raw SQL `INSERT INTO security_logs` — 독립 실행 운영 도구 2곳
     (`tools/ops/bulk_complete_past_construction_core.py:377`, `tools/ops/data_doctor.py:500`). 앱을 import 하지 않는다.
  4. (현재 0곳) `bulk_insert_mappings`·`session.execute(insert(SecurityLog))` 같은 ORM 우회 대량 쓰기.
- 고객명이 문장에 들어가는 이유: AUDIT-LOG P4 B1(`foms/services/orders/audit_order_context.py`)이 "로그만 보고
  누구 건인지" 알게 하려고 `order_audit_context` 로 고객명을 스냅샷해 `주문 #4109 (홍길동) — …` 형태로 남긴다.
  같은 값이 `detail.customer_name` 에도 들어간다. 연락처·주소는 넣지 않기로 했지만(같은 파일 docstring) 아래 경로로 섞인다.
- 전화·주소가 섞이는 경로:
  - 주문 수정 폼 `foms/web/orders/edit.py:600-606` — `전화번호: 이전 ⇒ 이후; 주소: 이전 ⇒ 이후; 고객명: …` 를 문장에 넣는다.
  - 주문 저장 `foms/api/erp_orders_structured.py:607`(`_diff_detail`) → 1189·1717 — `detail.changes` 에
    `parties.customer.phone`·`site.address_full` 등의 변경 전후값을 그대로 싣고, 문장 꼬리말(요약)에도 앞의 몇 건을 적는다.
  - 자유 입력 문장(AS 메모·지방 메모·강제 진행 사유·비용 청구 사유·파일명 등)에 사람이 적은 번호·주소.
- 관리자 감사 화면(`foms/web/admin/audit.py`)은 이미 주문 번호로 현재 고객명을 한 번에 조회해 붙인다
  (`_order_display_names`, N+1 없음). 자유 검색은 `message ILIKE` 다.

## 전수 결과 (기준 `origin/deploy` 4188600fb, AST 로 호출 노드만 셈 — 주석·docstring 제외)
- 감사·보안 기록 작성 호출 지점 **171곳** (부록 A 에 경로:행 전부).
  - `log_access` 137 · 직접 `SecurityLog(...)` 28(그중 1곳은 `log_access` 본체) · `record_access_denied` 3 ·
    `write_security_log_detached` 1(`record_access_denied` 본체) · raw SQL 2.
  - 참고: `access_logs`(파일 열람 기록) 작성은 별도 6곳(`record_file_access` 5 + 본체 1). 담는 값은 파일 키·주문 번호뿐이라 이번 범위 밖.
- 고객 정보가 닿는 곳 **67곳**:
  - 고객명이 문장·detail 에 들어감 **56곳**. 그중 **3곳**은 전화·주소·고객명의 변경 전후값까지 들어감
    (`edit.py:605`, `erp_orders_structured.py:1189`, `:1717`).
  - 고객명은 없지만 자유 입력 문장이 그대로 들어가 전화·주소가 섞일 수 있음 **11곳**(채팅방 이름·파일명·사유 등).
    고객명이 있는 56곳 중 44곳도 메모·사유 같은 자유 입력을 함께 싣는다.
- 고객이 아닌 사람 정보 **8곳**: 직원 계정(로그인 실패 아이디, 직원 발신번호 `sender_phone` 변경 — `routes.py:928`),
  협력사 계정·연락처 변경(`partners.py:36`, `partner/__init__.py:205` — 번호 자체는 싣지 않음). 가리지 않는다.
- 고객 정보 없음 95곳(네이버 수집 조작 기록·로그인/권한·설정 저장 등). 래퍼 본체 1곳(`routes.py:108`).

## 변경

### 4-1. 가리는 한 지점
새 모듈 `foms/services/audit_masking.py` 의 `mask_security_log_values(message, detail, *, target_type, action)` 하나가 규칙 전부를 가진다.
이 함수를 부르는 곳은 두 군데뿐이다.
- ORM 길: `models.py` 에 `SecurityLog` 의 `before_insert`·`before_update` 훅을 단다. `log_access` 와
  직접 `db.add(SecurityLog(...))` 28곳이 모두 이 훅을 지난다 — 호출부 수정 0.
- Core 길: `write_security_log_detached` 가 insert 직전에 같은 함수를 부른다.

raw SQL 운영 도구 2곳은 앱을 import 하지 않는 독립 스크립트라 이 함수를 부를 수 없다. 대신 문장에서
고객명 자리(`({customer_name})`)를 뺀다(주문 번호·전후 단계·사유는 그대로). 래칫(§5)이 이 두 곳을 이름으로 허용하고, 다른 우회 쓰기가 생기면 실패한다.

가림 함수는 예외를 밖으로 던지지 않는다. 예상 못 한 오류가 나면 원문 대신 표식 문장
`(감사 문장 가림 실패 — 원문은 저장하지 않았다)` 과 `{"mask_failed": true}` 를 저장하고 경고 로그를 남긴다
(직접 `db.add` 경로에서 가림 오류가 업무 트랜잭션을 죽이지 않게, 그리고 원문이 새지 않게).

### 4-2. 가림 규칙
| 대상 | 규칙 | 예 |
|---|---|---|
| 전화번호 | 가운데 자리. 알림톡 로그·공유 감사 `to` 와 **같은 함수**(`kakao_alimtalk._mask_phone`) 재사용 | `010-1234-5678` → `010****5678` |
| 주소 | 시·도 + 시·군·구까지만, 나머지 `***` | `서울특별시 강남구 테헤란로 1` → `서울특별시 강남구 ***` |
| 상세주소 | 전부 `***` | `101동 1001호` → `***` |
| 고객명 | 성(첫 글자)만, 나머지 `*` (§4-3) | `홍길동` → `홍**` |

어디를 가리나:
- `detail` — 경로·칸 이름으로 고객 칸을 안다: `changes[].path` 가 `parties.customer.name/phone/phone2`,
  `parties.buyer.name/phone`, `site.address_full/address_detail` 이거나 `field` 가 `customer_name/phone/address`
  이면 그 `before`·`after` 를 종류대로 가린다. 키 `customer_name`·`phone`·`address`·`address_detail` 등도 종류대로 가린다
  (`to` 는 정산 내보내기의 날짜 `from`/`to` 와 겹쳐 키로는 쓰지 않는다 — 공유 발송 `to` 는 호출부가 이미 가리고, 남은 번호는 일괄 가림이 잡는다).
  그 밖의 문자열 값은 전화번호 모양만 일괄로 가린다(식별자 키 `storage_key`·`change_set`·`*_id` 는 건드리지 않는다).
- `message` — ① `주문 #N (이름)` 의 괄호 안 이름, ② 표시 SSOT 라벨(`고객명`·`전화번호`·`보조 연락처`·`주문자명`·
  `주문자 연락처`·`주소`·`상세주소`) 뒤의 값(이전·이후 각각), ③ detail 에서 알게 된 고객명 원문, ④ 행위
  `ESTIMATE_SAVED` 의 꼬리말(견적 고객명), ⑤ 나머지 자유 글의 전화번호 모양과 `시·도 시·군·구 도로명/동 번지` 모양 주소.
  라벨은 `audit_message_display.FIELD_LABELS`·`PATH_LABELS` 에서 읽는다(라벨을 바꾸면 규칙도 따라간다).
- 남기는 것: 주문 번호, 바뀐 칸 라벨, 행위자(`user_id`), 행위 종류, 금액·날짜·단계, 직원·협력사·발주사 정보.
  - 직원 대상 행(`target_type` 이 `user`·`password_reset_request`·`partner_org`)은 통째로 손대지 않는다 — 직원 발신번호 변경 기록이 그대로 남는다.
  - 주문 행 안의 `발주사 연락처`(`parties.orderer.phone`, 라홈·하우드 같은 회사 번호)는 고객이 아니라 일괄 가림에서 뺀다.
  - 대표번호(`1566-…`)는 0 으로 시작하지 않아 전화번호 모양에 걸리지 않는다.
- 같은 값을 두 번 가려도 결과가 같다(멱등) — `before_update` 에서 다시 지나도 안전하다.

### 4-3. 고객명 판단 — 성만 남긴다
- 업무상 필요한 것은 "어느 고객 건인지 알아보는 것" 이지 실명 원문 사본이 아니다.
  - 주문이 살아 있으면(휴지통 포함 — 행이 남는다) 감사 화면이 주문 번호로 **현재 이름**을 조회해 붙인다(`_order_display_names`).
    원장에 실명 사본이 없어도 화면은 지금처럼 읽힌다.
  - 원장 사본이 유일한 단서가 되는 것은 주문 행이 영구 삭제된 뒤뿐이다. 그 경우까지 3년 동안 실명을 남기는 것은
    목적보다 과하다. 성 + 글자 수(`홍**`)와 주문 번호·시각이면 같은 날 여러 건 중 어느 건인지 사람이 가려볼 수 있다.
- 그래서 저장은 성만 남기고, 화면·검색은 살아 있는 주문 표에서 이름을 다시 가져온다.
  - `foms/web/admin/audit.py` `_security_log_row`: detail 의 이름보다 조회한 현재 이름을 먼저 쓴다.
  - 같은 파일 `_unmask_order_names`: 문장의 `(홍**)` 이 그 주문 현재 이름의 가림 결과와 같을 때만
    현재 이름으로 바꿔 보여 준다(다른 이름이면 가린 채로 둔다). "원문 보기" 는 저장값 그대로다.
  - 자유 검색: `message ILIKE` 에 더해 "고객명이 검색어와 맞는 주문(상한 200건)을 대상으로 한 행" 도 찾는다
    (`target_type='order' AND target_id IN (…)`). 이름으로 찾던 기능이 새 기록에서 사라지지 않게 한다.

### 4-4. 바꾸는 파일
- 새 파일: `foms/services/audit_masking.py`, `tests/domains/test_audit_log_masking.py`, 이 설계서.
- `models.py` — `SecurityLog` 바로 아래 훅 1개(지연 import, 순환 없음).
- `foms/services/audit_writer.py` — Core insert 직전 1줄 + 모듈 상단 import 1줄(파일 크기 래칫 500줄 미만 유지 —
  docstring 두 줄을 한 줄로 합쳤다).
- `foms/web/admin/audit.py` — 표시 이름 우선순위 1줄, 가린 이름 되돌려 보이기, 검색 조건 1개.
- import 는 전부 모듈 상단이다(함수 안 지연 import 래칫 `test_layer_dependency_ratchet` 순증 0).
  `audit_masking` → `audit_message_display`(순수 모듈)·`kakao_alimtalk`(`_mask_phone`), `audit_writer`·`audit.py` → `audit_masking`.
  모델 훅만 `models.py`(스캔 밖) 안에서 지연 import 한다 — 모델 정의 시점 순환을 피하려는 기존 관례와 같다.
- `tools/ops/bulk_complete_past_construction_core.py`, `tools/ops/data_doctor.py` — 문장에서 고객명 자리 제거.
- 기존 테스트 기대값: 고객명·전화가 원문으로 저장된다고 단언하던 곳을 가린 값으로 고친다(계약 변경 — P4 C1 의
  "고객명 병기" 는 유지, 병기되는 값이 `홍**` 로 바뀐다). `test_audit_action_coverage.py`·
  `test_order_audit_structured_writes.py`·`test_order_save_audit_diff.py`·`test_admin_audit_screen_readability_2.py`·`_3.py`.
- `docs/harness/foms_failopen_inventory.json` — 가림 실패 처리(로그 남김) 1건 등재(스캐너 재생성).

## 기존 데이터 (이번에 고치지 않는다 — 별도 승인)
이미 쌓인 행은 그대로 둔다. 정리는 운영 쓰기라 별도 승인 후 일회성 도구로 한다.
1. 측정(읽기만): 운영 `security_logs` 에서 전화번호 모양(`0(1[016789]|2|[3-6][1-5]|70)…`)·주소 모양·
   `detail ? 'customer_name'` 행 수를 **개수만** 센다(본문 출력 금지). 2026-08-07 측정과 비교한다.
2. 도구: `tools/ops/mask_security_logs_backfill.py`(가칭) — `id` keyset 배치(1,000행)로 읽어
   `mask_security_log_values` 를 그대로 적용하고, 바뀐 행만 `UPDATE security_logs SET message=…, detail=… WHERE id=…`.
   - `--dry-run` 기본: 바뀔 행 수·종류별 개수만 출력(값 출력 금지).
   - `--apply` 는 운영 승인 절차(`foms/services/security/ops_approval.py`) 1건 + 작업 전 백업 스냅샷 확인 후.
   - 같은 함수를 쓰므로 새 기록과 옛 기록의 가림 결과가 같다. 멱등이라 중단 후 다시 돌려도 된다.
   - 직원 대상 행은 함수가 알아서 건너뛴다.
3. 범위 밖이지만 같은 성격: `order_field_changes.before_value/after_value`(변경 원장 — 되돌리기·검색에 원문을 쓴다),
   `order_events.payload`(`ADDRESS_CHANGED`·메모 `to`), `channel_delivery_logs`(분석 문서 §6 — `masked_` 인데 30% 에 번호).
   각각 쓰임새가 달라(원장은 되돌리기 근거) 별도 설계가 필요하다.

## 테스트
새 파일 `tests/domains/test_audit_log_masking.py`(테스트 데이터는 `CLAUDE-TEST-` 표지와 `010-0000-0000` 류 가짜 번호만):
- 저장 경로별 가림: `log_access`·직접 `db.add(SecurityLog)`·`write_security_log_detached`·`record_access_denied`
  네 길 모두 문장의 전화·주소가 가려져 저장된다.
- 남는 것: 주문 번호·바뀐 칸 라벨·직원 대상 행의 직원 연락처·발주사 연락처·대표번호·식별자 키는 그대로.
- 변경 전후값(JSON): `detail.changes[]` 의 고객 칸 `before`/`after`, 평면 `field/before/after` 가 가려진다.
- 실제 라우트 1건: 주문 수정 폼(`edit.py`) 으로 전화·주소를 바꾸면 저장된 문장에 원래 번호·도로명이 없다.
- 멱등·실패: 두 번 가려도 같다, 가림 함수가 예외를 내면 표식 문장이 저장되고 원문은 없다.
- 화면: 가려 저장된 행이 감사 화면에서 현재 이름으로 보이고, 고객명 검색으로 찾힌다.
- 래칫: `security_logs` 에 ORM 훅을 거치지 않고 쓰는 곳(`SecurityLog.__table__.insert/update`·`insert(SecurityLog…)`·
  `bulk_insert_mappings`·`bulk_save_objects`·`query(SecurityLog)….update`·raw SQL `INSERT INTO`/`UPDATE security_logs`)을
  `foms`·`scripts`·`tools`·`migrations`·루트 .py 에서 찾아 허용 목록(`audit_writer.py` Core 1곳 + 운영 도구 2곳)과 **정확히** 같아야 한다.
  음성 대조: 우회 쓰기 4종을 담은 임시 파일을 스캐너가 실제로 잡는다. 운영 도구 2곳은 raw INSERT 에 고객 필드가 없어야 한다.
  ORM 훅이 실제로 등록돼 있는지도 확인한다.

회귀: `test_audit_action_coverage.py`·`test_order_audit_structured_writes.py`·`test_purge_audit_logs.py` + `SecurityLog` 를 쓰는 테스트 전부(pre_push_smoke 전체 실행).

## 영향·위험
- 성능: 감사 행 1건당 정규식 몇 번. 로컬 측정 — 보통 문장 약 0.1ms, 4,000자(상한) 문장 약 2.4ms. 요청 경로에 DB 왕복 추가 없음.
  검색 조건 추가는 관리자 감사 화면 검색(차가운 경로)에만 해당하고 주문 쪽 조회는 상한 200건.
- 동작: 감사 화면 문장의 고객명·전화·주소가 가려져 저장된다. 살아 있는 주문은 화면에서 현재 이름이 보인다.
  "원문 보기" 에는 가린 원문이 보인다. 전화·주소 원문이 필요하면 주문 화면(또는 `order_field_changes` 원장)을 본다.
- 과잉 가림: 주문 행 문장 속 직원·기사 번호가 자유 글로 적히면 같이 가려진다(고객 번호와 모양이 같아 구분 불가).
  감사 목적상 손실은 작고 개인정보 쪽으로 안전한 방향이다.
- 못 잡는 것: 자유 글 속 이름은 같은 행 detail 에 그 고객명이 있을 때만 잡는다(채팅방 이름·파일명에만 쓴 이름은 못 잡음).
  자유 글 주소는 `시·도 + 시·군·구 + 도로명/동` 으로 시작하는 것만 잡는다 — `강남구 테헤란로 1` 처럼 시·도를 빼고 쓴 주소,
  주소와 떨어져 적힌 `101동 1001호` 는 남는다(라벨 `주소`·`상세주소` 뒤 값은 모양과 무관하게 가린다).
- 되돌리기: 훅·호출 2곳을 지우면 원래 동작. 데이터 변환이 없어 롤백 부담이 없다.

## 등급
`**B` — 한 세션 완주 크기. 감사 코어(DB 기록 경로) 변경이라 설계서 → 구현 → 커밋, push 는 하지 않는다.
배포는 deploy → 스테이징에서 감사 화면 확인 → 운영 승격(사용자 요청 시). 기존 데이터 정리는 별도 승인.

## 부록 A — 기록 작성 호출 지점 전수 (171곳)
표기: `행*` = `log_access` 가 아닌 길(직접 SecurityLog·record_access_denied·write_security_log_detached·raw SQL),
`행+` = 고객명과 함께 자유 입력(메모·사유·파일명)도 싣는 곳.

### 전화·주소·고객명 변경 전후값까지 (3)
- `foms/api/erp_orders_structured.py`: 1189, 1717
- `foms/web/orders/edit.py`: 605

### 고객명 (53 — 위 3곳과 합쳐 56)
- `foms/api/channel/channel_integration.py`: 460+
- `foms/api/construction/orders.py`: 344+
- `foms/api/cs/as_orders.py`: 212+
- `foms/api/drawing/erp_orders_draftsman.py`: 64+
- `foms/api/drawing/erp_orders_drawing.py`: 417+, 697+, 826+
- `foms/api/drawing/erp_orders_revision.py`: 687+
- `foms/api/drawing/wizard.py`: 872+
- `foms/api/erp_estimates.py`: 168+
- `foms/api/erp_map.py`: 830+
- `foms/api/erp_order_draft.py`: 742+
- `foms/api/erp_orders_blueprint.py`: 155+, 226+
- `foms/api/erp_orders_structured.py`: 1919+
- `foms/api/events.py`: 378+
- `foms/api/files/order_routes.py`: 157+
- `foms/api/files/upload_intent.py`: 129+
- `foms/api/files/upload_ticket_routes.py`: 130+
- `foms/api/kakao/__init__.py`: 136+, 180+
- `foms/api/measurement/routes.py`: 500+
- `foms/api/notifications/__init__.py`: 1082
- `foms/api/orders/call_log.py`: 210+
- `foms/api/orders/field_update.py`: 454, 577+, 921+
- `foms/api/orders/measurement_visit.py`: 98*, 106*
- `foms/api/orders/mobile_delete.py`: 88*
- `foms/api/orders/regional.py`: 222+, 342+
- `foms/api/orders/stage_override.py`: 299+
- `foms/api/orders/status.py`: 119+, 144+
- `foms/api/production/orders.py`: 580+
- `foms/api/quest.py`: 79+, 762+
- `foms/api/share.py`: 860+, 1281+, 1614+, 1652+
- `foms/api/shipment/change_ack.py`: 254+
- `foms/api/shipment/packing.py`: 386+
- `foms/api/shipment/settings.py`: 293+
- `foms/api/tasks.py`: 178+
- `foms/api/wdcalculator/blueprint.py`: 1050
- `foms/web/admin/storage.py`: 273+
- `foms/web/orders/listing.py`: 508, 655+
- `foms/web/orders/trash.py`: 277+
- `tools/ops/bulk_complete_past_construction_core.py`: 377*
- `tools/ops/data_doctor.py`: 500*

### 고객명 없이 자유 입력만 (11)
- `foms/api/channel/files.py`: 122, 195
- `foms/api/channel/rooms.py`: 148, 281, 304
- `foms/api/cs/dashboard.py`: 384*
- `foms/api/notifications/__init__.py`: 938
- `foms/api/orders/stage_override.py`: 200, 384
- `foms/services/orders/admin_override.py`: 261*
- `tools/ops/triage_orphan_drawing_uploads.py`: 193

### 직원·협력사 정보 — 가리지 않음 (8)
- `foms/api/partner/__init__.py`: 205*
- `foms/web/admin/partners.py`: 36
- `foms/web/auth/routes.py`: 374, 417, 426, 435, 451, 928

### 래퍼 본체 (1)
- `foms/web/auth/routes.py`: 108*

### 고객 정보 없음 (95)
- `foms/api/channel/files.py`: 216, 223
- `foms/api/channel/messages.py`: 240
- `foms/api/channel/rooms.py`: 346, 375
- `foms/api/cs/dashboard.py`: 455*
- `foms/api/cs/settlement_channel.py`: 385, 492
- `foms/api/drawing/erp_orders_draftsman.py`: 454*
- `foms/api/drawing/erp_orders_revision.py`: 222*, 327*, 460*, 614*
- `foms/api/erp_map.py`: 731
- `foms/api/erp_order_draft_send.py`: 198
- `foms/api/erp_orders_structured.py`: 1426*
- `foms/api/events.py`: 742*, 867*
- `foms/api/notifications/__init__.py`: 660, 709, 771
- `foms/api/orders/copy.py`: 69
- `foms/api/share.py`: 988
- `foms/api/shipment/recommendations.py`: 750*, 804*
- `foms/api/wdcalculator/blueprint.py`: 574, 1165, 1205, 1295, 1360
- `foms/services/audit_writer.py`: 319*
- `foms/services/drawing_wizard_presets.py`: 303*
- `foms/services/integrations/naver_commerce/auto_dispatch.py`: 240*
- `foms/services/orders/admin_override.py`: 294*
- `foms/services/orders/cs_complete_service.py`: 184*
- `foms/services/orders/order_mutation_policy.py`: 591*
- `foms/services/partners/as_intake.py`: 91*
- `foms/services/partners/drawing_confirm.py`: 126*
- `foms/services/partners/manager.py`: 111*
- `foms/services/partners/orders.py`: 196*
- `foms/services/partners/revision.py`: 114*
- `foms/services/request_write_guard.py`: 107*
- `foms/services/shipment_reference.py`: 566*
- `foms/web/admin/backup_status.py`: 66*
- `foms/web/admin/naver_ingest.py`: 5076, 5132, 5209, 5373, 5423, 5519, 5615, 5706, 5773, 5837, 5920, 5990, 6079, 6168, 6256, 6463, 6599, 6658, 6692, 6769, 6830, 6858, 6912, 6929, 7030, 7046, 7150
- `foms/web/admin/ops_approvals.py`: 70, 93
- `foms/web/admin/routes.py`: 46
- `foms/web/auth/routes.py`: 335, 463, 479, 502, 524, 553, 631, 653, 689, 801, 941, 1005, 1069, 1106, 1153, 1214
- `foms/web/orders/dashboard.py`: 798
- `foms/web/orders/listing.py`: 611, 633
- `foms/web/orders/trash.py`: 404, 410
