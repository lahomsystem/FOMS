# 외부 협력사 주문 접수 — 협력사 전용 화면 SPEC (승인 2026-10-08 · 1·2·3단계 구현)

작성 2026-10-08. 등급: 코어 변경(DB · Auth) — Spec → 승인 → 구현.

## 0. 사용자 결정 (2026-10-08)

- 외부 협력사가 영업 → 실측 → 초안 도면까지 하고 우리에게 넘긴다. 그 뒤(도면 확정 · 생산 · 시공)는 우리 흐름과 같다. 시공도 우리가 간다.
- 시작 방식: **협력사 전용 화면** (협력사 직원에게 계정을 주고, 자기 회사 주문만 보이는 화면).
- 고객 연락: **협력사가 고객에게 따로 연락한다.** 협력사 주문의 고객에게 우리 시스템은 알림톡 · 문자를 보내지 않는다.
- 고객 확인 단계: **우리 시스템에 고객 확인은 없다.** 대신 **협력사가 최종 도면을 보고 "이대로 만들어 주세요"를 누르면 생산으로 간다**(협력사 확인 = 기존 CONFIRM 승인 자리). 잘못 만들어졌을 때 책임 소재가 남는다.
- 시공 날짜: **협력사가 고객과 잡는다.** 우리가 가능한 날짜를 협력사 화면에 올리고, 협력사가 그중 하나를 고른다.
- 보는 범위: **협력사 직원은 자기 회사 주문 전부**를 본다(직원별 구분 없음).
- AS: **협력사를 통해서만** 받는다. 협력사 화면에서 AS 를 접수한다.
- 정산: **돈 계산 규칙은 아직 정하지 않는다.** 이번에는 정산 화면에서 협력사 주문을 따로 갈라 보이기만 한다.

## 1. 지금 코드의 사실 (협력사에게 일반 ERP 계정을 주면 안 되는 이유)

1. 조회 범위가 전역이다. `user_can_read_order` 는 활성 계정이면 주문과 무관하게 True 다
   ([order_mutation_policy.py:387](../../foms/services/orders/order_mutation_policy.py)). VIEWER 도 같다.
   앱 URL 규칙 385개 중 134개가 `order_id` 를 받는다(2026-10-08 `app.url_map` 계수). 대부분은 `@login_required` 만 본다.
2. 회사(조직) 개념이 없다. `User` 에 회사 칸이 없고([models.py:1149](../../models.py)), 발주사는
   `structured_data.parties.orderer.name` 자유 글자다.
3. "내 담당만" 필터(`build_mine_sql_filter`, [erp_permissions.py:224](../../foms/services/erp_permissions.py))는 보기 편의이지 막는 장치가 아니다.
   `_erp_construction_team_restrict`([http.py:243](../../foms/platform/http.py))도 스스로 "인가 경계가 아니다"라고 적혀 있고 `/api/` 를 통과시킨다.
4. 쓰기 정책 `evaluate_policy`([order_mutation_policy.py:312](../../foms/services/orders/order_mutation_policy.py))는
   ADMIN · MANAGER · STAFF · VIEWER 외의 role 을 4단계에서 거부한다 → **알 수 없는 role 은 쓰기에서 기본 거부**다. 읽기에는 이런 장치가 없다.
5. 브랜드 판정이 "라홈 아니면 하우드"다. `resolve_brand`([kakao_alimtalk.py:390](../../foms/services/kakao_alimtalk.py))와
   도면 로고 `_resolve_logo`(`drawing_wizard_defaults.py:127`)가 같다. 실측일이 있는 주문을 저장하면
   `maybe_send_measure_alimtalk`(kakao_alimtalk.py:1065)가 하우드 프로필로 고객에게 자동 발송한다(`FOMS_ALIMTALK_AUTO_ENABLED` 켜진 환경).
6. 정산 브랜드 축 `brand_channel_of`(`settlement_aggregation.py:472`)는 라홈/네이버 외 전부 "일반"이다. 협력사에게 청구하는 축이 없다.
7. 알림 수신자: `target_type == 'ALL'` 이면 활성 사용자 전원이 받는다([recipients.py:84](../../foms/services/notifications/recipients.py)).
   Socket.IO `connect` 는 세션의 `user_id` 만 보고 연결한다([socketio_handlers.py:13](../../foms/api/channel/socketio_handlers.py)) — Flask `before_request` 를 거치지 않는다.
8. `/register` 는 PENDING · VIEWER 계정을 만들고 관리자가 승인한다. 승인된 VIEWER 는 전체 주문을 본다.
9. 첨부 파일 관문 `_deny_file_access`([files/routes.py:86](../../foms/api/files/routes.py))는 `orders/<id>/...` 키에 대해
   이미 `user_can_read_order` 를 부른다 → 1번을 고치면 파일도 함께 막힌다.
10. 새 주문의 시작 단계: 실측일이 있거나 발주사가 '라홈'이 아니면 MEASURE (`initial_workflow_stage.py`).
    MEASURE → DRAWING 은 실측 대시보드의 "도면 전달"(quest approve)이다.

## 2. 설계 원칙

- **같은 앱 · 같은 DB.** 도면 이후 과정은 우리가 하므로 주문은 우리 DB 에 있어야 한다. 협력사별 DB/서버는 동기화 비용만 만든다.
- **기본 거부.** 협력사 계정은 허용 목록에 있는 주소만 쓸 수 있다. 기존 385개 주소를 하나씩 고치지 않는다.
- **판정 축은 ID 칸.** 이름 · JSONB 문자열로 회사를 판정하지 않는다(`users.partner_org_id`, `orders.partner_org_id`).
- **기존 내부 흐름은 그대로.** 우리 직원 화면 · 권한은 바뀌지 않는다(협력사 표식만 늘어난다).

## 3. DB (Alembic 1개, downgrade 포함)

### 3.1 새 표 `partner_orgs`
| 칸 | 형 | 설명 |
|---|---|---|
| id | int PK | |
| name | varchar(100) unique | 협력사 이름 — 주문의 발주사 이름으로 자동 기입 |
| biz_reg_no | varchar(20) null | 사업자번호 |
| is_active | bool default true | false 면 소속 계정 로그인 차단 · 새 주문 등록 차단 |
| customer_messaging | varchar(20) default 'NONE' | 고객 알림 정책. 이번 범위는 `NONE` 만(0장 결정). 칸은 나중 확장용 |
| logo_storage_key | varchar null | 도면 로고(없으면 로고 없음) — 6.2 |
| contact_name / contact_phone | varchar null | 우리 쪽 연락 창구 |
| created_at / updated_at | timestamptz | |

### 3.2 `users`
- `partner_org_id int null FK partner_orgs.id` + 색인. null = 우리 직원.
- 협력사 계정은 `role = 'PARTNER'`, `team = NULL`.
  - 이유: 1장 4번 — 알 수 없는 role 은 쓰기 정책에서 이미 기본 거부되고, `role_required([...])` 허용 목록에도 걸리지 않는다.
    VIEWER 나 STAFF 를 주면 기존 허용 규칙에 걸려 통과하는 곳이 생긴다.
  - `ROLES` 상수([auth/routes.py:61](../../foms/web/auth/routes.py))에는 넣지 않는다 — 사용자 관리 화면에서 내부 직원에게 실수로 줄 수 없게. 협력사 계정은 협력사 관리 화면(5.3)에서만 만든다.
- DB 제약: `CHECK ((role = 'PARTNER') = (partner_org_id IS NOT NULL))` — 회사 없는 협력사 계정, 회사 붙은 내부 직원 둘 다 막는다.

### 3.3 `orders`
- `partner_org_id int null FK partner_orgs.id` + 부분 색인 `WHERE partner_org_id IS NOT NULL`.
  - JSONB 가 아니라 평평한 칸인 이유: 권한 필터를 SQL 에서 건다. JSONB 를 건드리면 TOAST 비용이 크다(성능 메모 참조).
- `structured_data.source = 'PARTNER'`, `structured_data.parties.orderer.name = partner_orgs.name` 을 함께 기록한다(화면 표식 · 기존 표시 경로 호환).
- `partner_org_id` 는 등록 때 한 번 정해지고 이후 바뀌지 않는다(바꾸려면 ADMIN 전용 명령 + 감사 기록. 이번 범위 밖).

### 3.4 첨부
- 협력사가 올린 파일은 `OrderAttachment.category = 'partner_draft'`(초안 도면) · `'measurement'`(실측 사진) 로,
  키는 `orders/<id>/partner_draft/...` · `orders/<id>/measurement/...`. `upload_authz.py` 허용 폴더에 `partner_draft` 추가.
- `partner_draft` 는 **원본 보존**: 협력사 · 우리 직원 모두 삭제 불가(ADMIN 만). 실측 오류 책임을 가릴 증거다.
- 협력사가 입력한 실측 수치는 `structured_data.partner_intake`(등록 시점 사본, 읽기 전용)에도 남긴다. 우리 도면팀은 `items` 를 평소처럼 고친다.

## 4. 권한

### 4.1 협력사 문지기 (`before_request`, 핵심)
- `foms/platform/http.py` 의 `_set_current_user` 바로 뒤에 `_partner_gate` 를 등록한다.
- `g.current_user.role == 'PARTNER'` 이면:
  - 허용(1단계 구현): `static` · `auth.logout` · `auth.switch_back` · 파일 관문 `files.view`·`files.presigned_urls`·`files.download`(안에서 4.2 로 다시 판정). 2단계에서 협력사 화면 endpoint 를 더한다.
  - 로그인 화면은 허용하지 않는다 — 공용 레이아웃이 내부 메뉴·단계 배지 수를 그린다. 로그인된 협력사가 `/login` 을 열면 막힘 화면이 나온다.
  - 그 외 전부: 화면은 403 막힘 화면(공용 레이아웃 없는 단독 HTML, 로그아웃 버튼), `/api/` 가 든 경로는 403 JSON(기존 불변식: API 는 302 금지).
  - 소속 `partner_orgs.is_active == false` 면 세션을 끊고 로그인 화면으로(API 는 401).
- 구현: `foms/services/auth/partner_scope.py` 의 `partner_gate`, 등록은 `foms/platform/http.py`(`_set_current_user` 바로 뒤).
- 허용 목록은 **접두어가 아니라 endpoint 이름 집합**으로 둔다(`request.endpoint`). 접두어는 새 라우트가 우연히 같은 접두어로 생길 때 뚫린다.

### 4.2 주문 단위 조회 판정
- `user_can_read_order(user, order)`:
  - `role == 'PARTNER'` 이면 `order is not None and order.partner_org_id == user.partner_org_id` 일 때만 True.
  - 내부 직원은 지금과 같다(전역 조회).
- 파일 관문은 이미 이 함수를 쓰므로 자동 적용(1장 9번). `order-drafts/<user_id>/` 분기도 본인만이라 그대로 안전.

### 4.3 문지기가 닿지 않는 길
- Socket.IO `connect`: role 이 PARTNER 면 `return False`(연결 거부). 협력사 화면은 실시간 연결을 쓰지 않는다.
- 알림 수신자 `recipients.py`: ALL · role · team · manager_name 경로 모두 `User.partner_org_id IS NULL` 조건 추가. 협력사에게 가는 알림은 `target_user_id` 직접 지정만.
- 웹푸시 일괄 대상(`push_sender.py:693` — team 있는 사용자)은 team NULL 이라 이미 제외. 계약 테스트로 고정.
- `/switch-user`: ADMIN 이 협력사 계정으로 들어가 보는 것은 허용(지원용). 반대는 문지기가 막는다.
- `/register` 승인 화면에서 PARTNER 를 고를 수 없다(3.2 — ROLES 에 없음).
- 쓰기 정책 엔진(`evaluate_policy`, 운영에서만 켜짐): 협력사 계정은 `PARTNER_ALLOWED_POLICIES`(ACCOUNT_SELF · ACCOUNT_ANON)만 통과. 이 분기가 없으면 모르는 role 이라 **로그아웃까지 403** 이었다(테스트는 엔진이 꺼져 있어 안 보인다 — 엔진을 켠 테스트로 고정).
- 긴급 호출 받는 사람 후보 · 알림 배지 무효화 대상(`foms/api/notifications`)도 4.3 수신자 조건과 같은 `INTERNAL_USERS_ONLY` 를 쓴다.

### 4.4 래칫 테스트 (pre_push 범위 밖이니 CI 에서 강제)
- `tests/security/test_partner_gate.py`: `app.url_map` 전 규칙 × 메서드를 협력사 세션으로 호출해, 허용 목록 밖은 문지기 응답(403)인지 확인한다.
  새 라우트가 생기면 자동으로 검사 대상이 된다. 문지기 등록을 빼면 빨강이 되는 것을 확인했다.
- 다른 협력사 주문 id · 내부 주문 id 로 상세 · 파일 · presigned 를 호출해 403 확인(음성 대조군 포함 — 자기 회사 주문은 200).

## 5. 화면

### 5.1 협력사 화면 (`foms/web/partner/`, `foms/api/partner/`, 자체 base 템플릿 — 내부 nav · 알림 벨 · 채팅 없음)
- **주문 목록**: 자기 회사 주문만. 칸은 고객명 · 현장 주소(동까지) · 등록일 · 쉬운 단계.
- **쉬운 단계**(내부 단계를 묶어서 보여 준다): 접수 확인 중(MEASURE) → 도면 작업 중(DRAWING) → 도면 확인 요청(CONFIRM — 협력사 차례) → 생산 중(PRODUCTION · 출고) → 시공 날짜 고르기 / 시공 예정(날짜 표시) → 완료. AS 는 "AS 진행 중" 한 칸.
- **새 주문 등록**: 고객명 · 연락처 · 현장 주소 · 품목별 실측 치수 · 실측 사진 · 초안 도면 파일 · 메모. 업로드는 기존 R2 Presigned PUT 경로.
- **주문 상세**: 등록 내용(읽기 전용) · 최종 도면(우리가 확정한 것) · 시공 일정 · 메모 주고받기.
- **협력사 도면 확인**(0장 결정): 우리 도면팀이 넘긴 최종 도면이 CONFIRM 단계에 오면 협력사가 둘 중 하나를 누른다.
  - "이대로 만들어 주세요" → 기존 CONFIRM 승인 경로(`check_quest_approvals_complete` → 생산 자동 이동, 2026-09-20 작업)를 그대로 탄다. 누른 사람 · 시각 · 그때의 도면 회차를 감사 기록에 남긴다.
  - "수정 요청"(사진 · 메모) → 기존 도면 수정요청 경로(`erp_orders_revision.py`)로 우리 도면팀에 간다.
  - 고객 확인 단계는 시스템에 두지 않는다. 고객과의 확인은 협력사가 시스템 밖에서 한다.
- **시공 날짜 고르기**(0장 결정): 우리 시공 담당이 가능한 날짜 후보(1~여러 개)를 올리면 협력사 화면에 뜨고, 협력사가 고객과 맞춰 하나를 고른다. 고른 날짜는 기존 `schedule.construction` 에 들어간다. 바꾸려면 협력사가 "날짜 변경 요청"을 보내고 우리가 새 후보를 올린다.
- **AS 접수**(0장 결정): 협력사 화면의 완료 주문에서 "AS 접수"(내용 · 사진). 기존 AS 사이클(`OrderASCycle`) 생성 경로를 협력사 몫으로 연결한다. 고객이 우리에게 직접 연락하면 협력사로 안내한다.
- 보여 주지 않는 것: 금액 · 원가 · 내부 메모 · 우리 직원 연락처 · 변경 이력 · 다른 회사 주문.

### 5.2 우리 직원 화면
- 주문 목록 · 상세에 "협력사: <이름>" 표식(네이버 마크와 같은 자리, `source == 'PARTNER'`).
- 협력사 주문은 MEASURE 단계 · 담당 팀 CS 로 들어오고 `measurement_completed = True`. CS 가 내용을 보고 기존 "도면 전달"을 누르면 DRAWING 으로 간다.
  새 단계 코드는 만들지 않는다(파이프라인 · 대시보드 전수 변경을 피한다).
- 실측 대시보드에서 협력사 주문은 "협력사 접수" 묶음으로 따로 보인다(우리 실측 담당 목록에 섞이지 않게).

### 5.3 협력사 관리 (ADMIN 전용, `/admin/partners`)
- 협력사 등록 · 끄기, 소속 계정 만들기 · 끄기 · 비밀번호 초기화. 계정은 우리 관리자만 만든다.

## 6. 고객 연락 · 도면 · 정산

### 6.1 고객 메시지 차단 (0장 결정)
- 주문 단위 판정 함수 하나: `is_partner_order(sd_or_order)`.
- 막는 곳:
  - 알림톡 자격 판정 `_sd_ineligible_reason`(kakao_alimtalk.py:524) — 자동 · 수동(`/api/kakao`) · 마법사 발송 모두 이 판정을 지난다(구현 때 전수 재확인).
  - 공유 링크 문자 · 알림톡 `api_share_send_sms`(share.py:1150) · `api_share_send_alimtalk`(share.py:1461) — 409 + "협력사 주문은 협력사가 고객에게 전달합니다".
  - 공유 링크 **만들기**는 허용한다(내부 직원이 협력사에게 전달하는 용도). 협력사는 자기 화면에서 최종 도면을 바로 보므로 링크가 꼭 필요하지는 않다.
- 구현 시작 때 고객 대상 발송 경로를 전수 목록으로 만든다(채널톡 고객 메시지 포함). 음성 대조군: 내부 주문은 지금처럼 발송.

### 6.2 도면 로고
- 협력사 주문은 하우드 · 라홈 로고를 쓰지 않는다. `partner_orgs.logo_storage_key` 가 있으면 그 로고, 없으면 로고 없음.
- `_resolve_logo` 앞에 협력사 분기를 둔다.

### 6.3 정산
- `brand_channel_of` 에 "협력사" 축 추가(협력사 주문은 일반에서 빠진다). 협력사별 합계를 따로 볼 수 있게 한다.
- 협력사에게 청구하는 금액 규칙(단가 · 수수료)은 이번 범위 밖(0장 결정 — 아직 안 정함). 이번에는 "어느 협력사 주문인지"만 정산 화면에 갈라 보인다.

## 7. 정해진 것 · 남은 것

정해짐(2026-10-08): 고객 확인 없음 + 협력사 도면 확인으로 생산 · 시공 날짜는 협력사가 고름 · 회사 단위 조회 · AS 는 협력사 경유 · 정산 규칙은 보류.

남은 것(구현을 막지 않음):
1. **시공 당일 고객 연락**: 시공팀이 고객에게 직접 전화해도 되나(도착 시간 안내 등)? 기본안: 주문에 고객 연락처가 있으니 시공팀 전화는 허용, 문자 · 알림톡 자동 발송은 없음.
2. **협력사 정산 규칙**: 정해지면 별도 SPEC.

## 8. 바꾸지 않는 것

- 내부 직원의 role · team · 조회 범위 · 쓰기 정책.
- 기존 주문 흐름(단계 코드 · quest 템플릿 · 파이프라인 순서).
- 네이버 · 라홈 · 하우드 판정(협력사 분기만 앞에 추가).
- Postgres RLS(DB 수준 행 보안)는 넣지 않는다 — 앱이 DB 계정 하나로 접속해 효과가 작다. 협력사가 늘면 다시 본다.

## 9. 단계 (각 단계 끝마다 deploy · 스테이징 확인)

1. DB 칸 + 문지기 + `user_can_read_order` + Socket.IO · 알림 수신자 차단 + 래칫 테스트. (화면 없음 — 협력사 계정이 아무것도 못 하는 상태를 먼저 증명)
2. 협력사 관리 화면 + 협력사 화면(목록 · 등록 · 상세) + 고객 메시지 차단 + 직원 화면 표식.
3. 도면 로고 · 협력사 도면 확인(→ 생산) · 시공 날짜 고르기 · AS 접수.
4. 정산 협력사 축(갈라 보이기만).

## 10. 검증 (완료 기준)

- `python -c "import app; print('APP_OK')"`.
- `python -m pytest tests/security/test_partner_gate.py -q` green.
  - 협력사 세션: 허용 목록 밖 모든 규칙 403/302. 다른 회사 · 내부 주문의 상세 · 파일 · presigned 403. 자기 회사 주문 200.
  - 내부 직원 세션: 기존 동작 그대로(협력사 주문도 조회 가능).
  - Socket.IO 연결 거부, `target_type='ALL'` 알림 수신자에 협력사 없음.
  - 협력사 주문: 알림톡 자동 · 수동 · 공유 문자 모두 발송 안 함. 내부 주문은 발송(음성 대조군).
  - 협력사 "이대로 만들어 주세요" → 자기 회사 CONFIRM 주문만 PRODUCTION 으로 이동, 다른 회사 주문 · CONFIRM 아닌 주문은 거부. 감사 기록에 도면 회차가 남는다.
- 기존 권한 테스트 전량 green(`tests/security`, `tests/domains` 의 정책 · 파일 관문 테스트).
- `alembic upgrade head` → `downgrade -1` → `upgrade head` 로컬 PG 왕복.
- `scripts/ops/pre_push_smoke.ps1` exit 0, push 뒤 CI green.
- 스테이징: 협력사 테스트 계정으로 로그인 → 내부 주소 직접 입력 시 막힘, 자기 주문 등록 → 우리 CS 화면에 "협력사" 표식으로 MEASURE 단계에 보임 → 도면 전달 → 협력사 화면 단계가 "도면 작업 중".

## 11. 남는 위험

- 문지기 허용 목록에 넣은 공용 주소(파일 관문 등)가 안에서 주문 판정을 빼먹으면 샌다 → 허용 목록의 각 endpoint 마다 "다른 회사 주문으로 호출 → 403" 테스트를 1:1로 둔다.
- 백그라운드 작업(worker · cron)이 만드는 알림 · 메시지는 요청 문지기를 거치지 않는다 → 6.1 의 주문 단위 판정과 4.3 의 수신자 조건이 막아야 한다.
- 발주사 이름을 내부 직원이 손으로 고치면 `orderer.name` 과 `partner_org_id` 가 어긋날 수 있다 → 판정은 항상 `partner_org_id` 로만 하고, 협력사 주문의 발주사 칸은 내부 화면에서 잠근다.
- 개인정보: 협력사 고객의 개인정보를 우리가 받는다. 협력사와 개인정보 처리 관련 계약이 필요하다(법률 확인은 사용자 몫).

## 12. 2단계 구현 기록 (2026-10-08)

- **우리 쪽 담당 직원**: `partner_orgs.owner_user_id`(migration `partner_01`). 주문은 반드시 우리 영업 직원이 담당이어야 한다
  (`create_order` 의 SALES 배정 행이 권한 판정에 쓰인다). 담당이 없는 협력사는 주문 등록을 400 으로 막는다.
  `users.partner_org_id` 와 서로 가리키는 순환이라 FK 는 `use_alter`.
- **협력사 관리**(`/admin/partners`, ADMIN): 협력사 만들기 · 담당 바꾸기 · 켜고 끄기, 계정 만들기 · 끄기 · 비밀번호 바꾸기.
  일반 사용자 수정 화면은 협력사 계정을 열면 여기로 보낸다.
- **협력사 화면**(`/partner`): 목록 · 새 주문 등록 · 상세. 단독 레이아웃(`partner/layout.html`, CSRF 배선 포함).
  문지기는 이제 막힌 화면 대신 `/partner` 로 보낸다(API · 쓰기는 403 JSON 그대로).
- **주문 등록**(`POST /api/partner/orders`): MEASURE · 주관 CS(퀘스트 규칙에 협력사 분기 — `erp_policy_quests`·`erp_quest_display`),
  `measurement_completed`, 원문 사본 `structured_data.partner_intake`. 실측일은 `schedule.measurement` 에 넣지 않는다(우리 실측 일정표에 안 섞이게).
- **파일**(`POST /api/partner/orders/<id>/files`): 기존 업로드 API 는 주문 범위 판정이 없어 열지 않고 전용 API 를 만들었다.
  사진 → `measurement` 분류 · `orders/<id>/partner_measurement/`, 초안 도면 → `drawing` 분류 · `orders/<id>/partner_draft/`.
  새 분류를 만들지 않은 이유: 직원 화면 JS 7곳이 분류 4종을 손으로 나열한다. 도면이 시작되면(DRAWING 부터) 409.
  이 두 폴더의 파일은 ADMIN 만 지운다(`is_partner_original_key`).
- **고객 메시지 차단**: `kakao_alimtalk._sd_ineligible_reason`·`_ineligible_reason`(자동 · 워커 · 수동 · 초안 전부),
  공유 링크 문자 · 알림톡 409, 공유 링크 만들기는 고객 번호 · 문자 본문을 비워 준다. 사유 코드 `partner_order`(재시도 · 이력 대상 아님).
- **직원 화면 표식**: 네이버 마크 8자리 바로 뒤에 "협력사 · 이름"(`partner_mark` 매크로, 추가 쿼리 없음 — 발주사 칸 값).

남은 것(3단계 이후):
- 실측 화면의 "협력사 접수" 묶음(지금은 표식만 붙는다).
- 내부 화면에서 협력사 주문의 발주사 칸 잠그기(판정은 `partner_org_id` 라 권한에는 영향 없음).
- 협력사 도면 확인(→ 생산) · 시공 날짜 고르기 · AS 접수 · 협력사 로고 · 정산 축.

## 13. 3단계 결정 · 3-1 구현 기록 (2026-10-08)

사용자 결정: 생산 날짜·시공 날짜는 우리가 erporder 에서 정한다(협력사는 보기만 — 목록 "시공 예정 · 날짜").
협력사 "도면 OK(→ 생산)"와 "수정 요청"은 만든다. 협력사 로고는 관리 화면에서 올린다.

3-1 (이번):
- **로고**: `/admin/partners/<id>/logo` 업로드(png·jpg·webp ≤2MB, `partners/<id>/logo/` 키) → `partner_orgs.logo_storage_key`.
  도면 마법사 기본값 `logo` = `'partner'`(로고 있음) / `'none'`(없음) — 라홈·하우드 안 씀(`foms/services/partners/logo.py`).
  도면 PNG 는 html2canvas 라 로고는 같은 출처 `GET /api/partner/orders/<id>/logo`(직원용, 협력사 세션은 문지기 밖)로 내린다.
  마법사는 협력사 주문이면 예전에 저장된 'haud'/'lahom' 을 무시하고 로고 고르기 창을 열지 않는다.
- **도면 OK**: 협력사 상세에 "최종 도면"(`resolve_final_drawing_files` — 도면팀이 넘긴 현재 파일만, 협력사 초안 제외) +
  CONFIRM 단계·도면 확정(CONFIRMED)일 때만 "이대로 만들어 주세요". `POST /api/partner/orders/<id>/approve-drawing` →
  직원 승인과 같은 기록(quest.assignee_approval · COMPLETED · blueprint.customer_confirmed · QUEST_APPROVAL_CHANGED) +
  `advance_stage_on_quest_completion` → PRODUCTION. 감사 `PARTNER_DRAWING_APPROVED`(도면 회차 · 최종 파일 key).
  도면 게이트 우회 없음.
- 작은 수정: 관리 화면 주문 수에서 지운 주문 제외, 담당 선택지에서 시스템 계정(naver_unassigned) 제외.

3-2 (다음): 협력사 "수정 요청"(메모·사진 → 기존 도면 수정 요청과 같은 효과), 협력사 AS 접수(`register_as_cycle`).

## 14. 3-2 구현 기록 (2026-10-08)

- **수정 요청**: 협력사 상세(DRAWING·CONFIRM 단계, 도면 TRANSFERRED·CONFIRMED)에서 메모 + 참고 사진(≤10장).
  `POST /api/partner/orders/<id>/revision` — 사진은 서버가 `orders/<id>/drawing_gateway/revisions/` 에 올리고
  (`is_revision_reference_key` 와 같은 폴더), 직원 수정 요청과 같은 효과: drawing_status RETURNED · 이력 REQUEST_REVISION
  (`by_user_name` 에 "(협력사)") · 고객확인 무효화 · 쓰기 정책 DRAWING_REVISION_REQUEST · 도면팀 알림(확인 창·웹 푸시·배지).
  대상 도면은 고르지 않고 현재 최종 도면 전부. 감사 `PARTNER_DRAWING_REVISION_REQUESTED`(`foms/services/partners/revision.py`).
- **AS 접수**: 시공 시작 뒤(CONSTRUCTION·CS·COMPLETED·AS*) 열린 AS 건이 없을 때만. `POST /api/partner/orders/<id>/as` →
  `register_as_cycle` + 직원 접수와 같은 부수 기록(reception·"AS 접수됨 (협력사)"·비용 판정 '미정' 기본값).
  사진은 접수 원문 줄(as_log_id)에 category 'as' 로 붙는다(접수가 확정된 뒤 — 사진 실패해도 접수는 남는다).
  고객 발송 없음. 열린 건 재접수는 우리 직원 몫(409). 감사 `PARTNER_AS_REGISTERED`(`foms/services/partners/as_intake.py`).

## 15. 마무리 (2026-10-09)

- **운영 반영**: PR #528 → production `8c890e0f` (1~3단계).
- **발주사 잠금**: 직원 주문 폼 저장(`lock_server_owned_keys`)이 협력사 주문의 `parties.orderer`·`source`·`partner_intake` 를
  서버값으로 고정한다(우리 주문은 그대로 바꿀 수 있다 — 대조 테스트).
- **"협력사 접수" 묶음 대신 알림**: 협력사 주문은 실측일이 없어 실측 화면(날짜 기준)에 아예 뜨지 않는다 — 묶음을 만들 자리가
  없다. 대신 등록 순간 **CS 팀 + 담당 영업**에게 벨 알림 `PARTNER_ORDER_CREATED`("협력사 새 주문")를 남긴다(협력사 계정은 수신 제외).
  주문 대시보드(실측 단계·CS 주관)에는 "협력사" 표식과 함께 보인다.

