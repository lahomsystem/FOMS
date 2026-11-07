# 프리랜서 영업 수수료 설계 — 교차 검수 원장 (2026-11-06)

대상: `docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md`
검수: ① 반증 ② 단순화 ③ 사실 검증 (리뷰 에이전트 3개, origin/deploy `65dec3151` 기준)
규칙: finding 은 받는 즉시 이 원장에 옮긴다. 처리 칸 = 반영 / 기각(이유) / 보류(이유). 메인 세션이 코드로 다시 확인한 뒤에만 반영한다.

## ① 반증 (받음 — 20건: 높음 8 · 중간 11 · 낮음 1)

| # | 심각도 | 내용 (리뷰어 근거) | 처리 |
|---|---|---|---|
| A1 | 높음 | 프리랜서가 `/profile` 에서 이름을 직원 이름으로 바꾸면 이름 일치 연결로 남의 주문·수수료를 가져감(`foms/web/auth/routes.py:1245-1256`, 검증·중복 없음). 동명이인도 같음 | 반영 — J8(맞출 이름은 설정값·다른 활성 사용자와 중복 거부), 3단계 프로필 이름 저장 거부 |
| A2 | 높음 | 모바일 홈 `?focus_order=` 가 mine 없이 남의 주문 줄을 끼워 넣음(`foms/web/orders/dashboard.py:222-230`, `dashboard_filters.py:99-100`) — 겹 2 가 query string 을 안 봄 | 반영 — §6.3 겹 2 query string 주문 번호 판정 |
| A3 | 높음 | 실측 판이 사용자 무관하게 그날 네이버 주문 전체 고객명을 HTML 에 실음(`foms/web/measurement/dashboard.py:592` → `:110-136`, `naver_dispatch_strip.html:80-82,123-124,187`) | 반영 — §6.3 겹 3 조각 전수 점검(네이버 띠 None) |
| A4 | 높음 | 실시간 알림이 다른 수신자 함수(`foms/api/notifications/__init__.py:74-131`)를 씀 → 팀 대상(도면 전달 담당 불일치 시 `target_team='SALES'`, 공지 팀 펼침 `:943-1010`)이 프리랜서 소켓으로 감 | 반영 — §6.3 겹 5 수신자 함수 통합, 소켓 전송까지 시험 |
| A5 | 높음 | 직원→프리랜서 전환 시 소켓 연결 허용(`socketio_handlers.py:19-39`), 채팅 새 메시지가 `user_` 방으로(`:143-147`), 기존 알림 state 남음(`notifications/__init__.py:358`) | 반영 — §6.3 겹 5 소켓 채팅 이벤트 거부·지정 때 회원 해제·옛 알림 숨김 |
| A6 | 높음 | AS 는 본공정과 무관하게 접수됨(`as_cycle_service.py:513`, 운영 477건 기록 `status_constants.py:80-93`) → AS 상태를 시공 완료로 보면 시공 전 주문에 수수료 | 반영 — J1 메인 단계(erp_stage_code CS/COMPLETED)만, AS 축 안 봄 |
| A7 | 높음 | 연결 투영을 `sync_erp_flat_columns` 에 넣으면 `_DeriveShim`(`erp_flat_audit.py:78-91,133-137`)·SimpleNamespace 시험(`tests/domains/test_erp_sync_columns.py`)이 `UnmappedInstanceError` — before_flush 선례 `order_date_sync.py` | 반영 — §5 before_flush 훅(order_date_sync 선례), sync_erp_flat_columns 안 씀 |
| A8 | 높음 | 서버가 초안에 채운 담당을 첫 자동 저장이 통째 교체로 지움(`erp_orders_structured.py:2338,2357-2365`), 마법사도 클라이언트 값 그대로(`erp_order_draft.py:217-220`) | 반영 — §5 CREATOR 연결 |
| A9 | 중간 | 실측 요약 API·focus 가 `is_order_related_to_user`(퀘스트 담당·시공자 이름·sales_assignee)로 거름(`measurement/routes.py:300-307`, `measurement_read_model.py:500-513`, `erp_permissions.py:162-202,348`) → 뱃지에서 빠져도 보임 | 반영 — §6.1·겹 3 프리랜서는 연결 표 하나만 |
| A10 | 중간 | `_history_more_link` 가 mine 없이 전체 건수 노출(`orders/dashboard.py:108-121,212-217`) | 반영 — 겹 3 history_more 끔 |
| A11 | 중간 | 품목 취소가 출고가에 반영 안 됨(`erp_orders_item_cancel.py:70-80`, `erp_display.py:304-347`, `structured_form_projection.py:251-305`) → §8.2·§11.1 "품목 취소 → ADJUST" 문구가 실제와 다름 | 보류 — 사용자 질문 §14 Q1(D2 와 충돌 가능) |
| A12 | 중간 | 차감 넣기 endpoint 가 FOR UPDATE·버전 증가 없이 JSONB 통째 저장(`cs/dashboard.py:292,345-366`) → 동시 저장 유실 | 반영 — §10.3 execute_order_mutation |
| A13 | 중간 | 프리랜서가 수수료를 올리는 다른 길: 발주사 라홈→하우드, 실측일 10-31→11-01, 시공일을 요율 오른 달로(`erp_permissions.py:378`) | 반영 — 겹 4 발주사 변경 거부 + 1단계 "본인 수정" 표시 + J9 |
| A14 | 중간 | 마감 뒤 주인·대상 변경 재계산 규칙 공백(대표 담당 F→G, 시작 달 변경, 단계 되돌림, 삭제, 발주사 F·대표 G 의 G 차감) → 첫 마감 때 주인·거래구분을 줄에 굳힘 | 반영 — J9 첫 마감 때 주인·거래구분·요율 굳힘 |
| A15 | 중간 | 시공일 10-30·완료 버튼 11-12 → "M 달만" 구현 시 영영 빠짐. "아직 마감 안 된 완료 전부"면 엑셀로 지급한 달까지 쓸어 담음 → ERP 정산 시작 하한 | 반영 — §8.1 대상 = 미마감 완료 주문 중 달 ≤ M, 시작 달이 하한 |
| A16 | 중간 | 마감 동시성(같은 F 의 두 달 동시 마감 → 조정 두 번), 순서(12월 먼저), "지급한 합" 정의(VOID·CLOSED) | 반영 — §8.1 오름차순만·설정 행 FOR UPDATE·VOID 없음 |
| A17 | 중간 | 차감 읽는 곳 6곳(`completion_dashboard.py:186-188,443-468,530-532`, `settlement_rows.py:360-362`, `settlement_aggregation.py:394-421,570-575`), `TARGET_STATUSES` 공용 상수(바꾸면 정산 전체 변함), 취소 권한(FINANCE_MUTATION 은 CS·영업 전원) | 반영 — §10.1 유효 판정 함수 6곳 공유, §10.4 상수 안 건드림, 취소는 회계·관리자 |
| A18 | 중간 | 래칫: `context_processors.py` 499줄 · `cs/dashboard.py` 476 · `erp_permissions.py` 464(기준선 밖 500 상한). `test_delete_retention.py:159` FK 커버리지(orders 참조 FK 는 CASCADE 필요). SQLite 부분 unique `sqlite_where` | 반영 — §4.2 CASCADE, §4.4 sqlite_where, §13 새 모듈 |
| A19 | 중간 | 서버 시작 때 `app_init.py:51-81` 이 최근 주문 sync → 배정 알림 폭주. 초안 단계 알림. 오프라인 병합(`offline_recovery.py:243-256`)은 sync 안 부름 | 반영 — §5 알림 조건(초안·되채우기·서버 시작 제외), before_flush 로 병합 경로 해결 |
| A20 | 낮음 | 파이썬 `round()` 은 짝수 반올림 → `(금액×bp + 5000)//10000`. 여러 날 시공은 첫 날짜 달(`settlement_aggregation.py:126-140`) | 반영 — J3 정수식, J1 여러 날은 첫 날 |

## ② 단순화 (받음 — 12건)

| # | 종류 | 제안 | 근거(리뷰어 인용) | 처리 |
|---|---|---|---|---|
| S1 | 미룸 | 연결 표·투영 훅 일체를 3단계로. 1·2단계는 계산 때 이름 정리(공백·NFC) 후 활성 프리랜서 이름표와 일치 판정. OrderAssignment(주문당 SALES 1명=만든 사람, `models.py:2424,2462`)·`sales_assignee_user_ids`(넣으면 편집·첨부 권한이 바뀜, `erp_policy_permissions.py:28`, `order_attachment_permissions.py:73`)로 대신하면 안 됨 | §4.4, §5 | 반영 — J10(연결 표는 3단계) |
| S2 | 합침 | 프로필+요율 표 → SystemSetting JSON 한 줄(`foms/services/partners/statement_profile.py:22,104-142` 선례, version·409) | §4.1, §4.2 | 반영 — J7 SystemSetting |
| S3 | 미룸 | 조정 줄은 1-10 전까지. 마감 M = 아직 마감 안 된 대상 주문 중 시공 완료 달 ≤ M 전부. 합계 0 이하면 마감 거부(넘김 칸 지움). `deduction_ids` 불필요 | §8.2, §8.3 | 반영 — §8.1·§8.2 (조정은 1-10 전) |
| S4 | 합침 | 설정 화면 → `/admin/users/edit/<id>` 안 칸 묶음(ADMIN, manifest `ACCOUNT_ADMIN` 기존, 발신번호 칸 선례 `routes.py:963-978`). 처리 본문은 서비스로(routes.py 1,289줄) | §2.3, §9 | 기각 — 사용자가 "컨트롤 패널"을 명시. 대신 작은 화면(선례 26줄·76줄)으로 |
| S5 | 합침 | 겹 4 정책 분기는 겹 1 과 중복 — 발주사 바꿔치기 검사만 남김. 탭 마크업 빼기 불필요(화면 전체가 이미 회계 전용). 읽기는 기존 `SETTLEMENT_DASHBOARD_READ`, 새 정책은 `SALES_COMMISSION_WRITE` 1개. §6.4 는 별도 task. "시공 뒤 금액 바뀜" 미룸 | §6.3, §9 | 반영 — 겹 4 정책 목록 지움, 탭 빼기 불필요, 읽기 기존 정책, 새 정책 1개, §6.4 별도 |
| S6 | 합침 | 마감 줄 표 → closings.lines JSON. 지급 전 마감 취소 = 행 삭제 + 감사(VOID 지움) | §4.5, §4.6, §8.4 | 반영 — §4.3 lines JSON, 마감 취소 = 삭제 |
| S7 | 지움 | `/api/sales-commission/me` + JS → 서버 렌더 `/erp/my-commission`(`<details>`, 링크 달 이동, JS 0줄) | §2.2, §9 | 반영 — §2.2 서버 렌더 |
| S8 | 지움 | 홈 빠른 카드 → 모바일 "더보기" 서랍 링크 한 줄(`templates/partials/shared/erp_mobile_menu_drawer.html:28-33`) | §2.2-1 | 반영 — §2.2 서랍 링크 |
| S9 | 미룸/지움 | 배정 알림·등록자=담당자는 3단계. 담당자 datalist 는 출고설정 실측담당자 목록(`context_processors.py:287-305`)에 이름만 넣으면 됨 — 코드 수정 불필요. D17 차감 알림은 1단계 | §5, §7 | 반영 — 배정 알림·CREATOR 는 3단계, datalist 는 운영 준비 |
| S10 | 미룸 | 차감 보강은 1(취소)·6(CS 단계 허용)만 첫 단계. 3번은 서버에서 "SALES 면 사람 필수" 한 줄. 2·7·8·9 미룸 | §10 | 반영 — §10.1~5(+프리랜서 FINANCE 거부), 나머지 미룸 |
| S11 | 미룸 | 실측일 기준 전환(D7)은 12-10 뒤, 매개변수 하나로 | §3.3, §9 | 반영 — D7 은 2단계 |
| S12 | 미룸 | CSV 내려받기는 첫 지급 뒤(회계팀이 파일을 원하는지 승인 때 확인) | §9 | 기각 — CSV 는 2단계에 유지(회계팀 지급·세금 기록용, 라우트 1개) |

## ③ 사실 검증 (받음 — 62개 확인, 틀림 4, 줄 어긋남 0)

| # | 종류 | 내용 | 처리 |
|---|---|---|---|
| F1 | 틀림 | §5 "24곳 관문" → 시험 밖 호출 34곳(`foms/` 30곳). `flag_modified(structured_data)` 하면서 안 부르는 파일 28개(예 `foms/api/cs/dashboard.py`, `drawing/erp_orders_revision.py`, `partners/info_edit.py`, `naver_commerce/promotion.py`) — 그중 `parties.manager` 를 고치는 경로는 못 찾음. ERP 주문이 아니면 `erp_sync_columns.py:113-114` 에서 바로 돌아감 | 반영 — §5 에서 sync_erp_flat_columns 를 쓰지 않음 |
| F2 | 틀림 | §5 "세션 없으면 건너뜀" — `erp_flat_audit.py:135-136` 이 매핑 안 된 `_DeriveShim` 을 넘김 → `object_session()` 은 `UnmappedInstanceError`. 선례 `erp_orders_structured.py:857`, `partners/logo.py:78` | 반영 — §5 before_flush |
| F3 | 틀림 | §3.3·J1 상태 목록 — AS 진행 `"AS"`(`state_axes.py:77`) 빠짐. `order.status` 는 DELETED > ON_HOLD > AS_* > 물류 > 메인 우선순위 글자(`state_axes.py:311-325`) → 메인 단계(`erp_stage_code`)와 AS 축(`as_axis_status`)으로 판정해야 함 | 반영 — J1 |
| F4 | 틀림 | §5 `create_order` 위치 → `foms/services/orders/order_create.py:140`(초안은 `erp_orders_structured.py:1970`) | 반영 — §5 경로 정정(CREATOR 로 대체) |
| F5 | 못 함 | §6.2 230·18·13 어림수(GET 규칙 264, mine 호출 22곳/14파일, read_model 파일 9개) | 반영 — §6.2 "약" 표기 유지 |
| F6 | 참고 | "실제 매출" 모집단에 CS 단계는 안 들어감(COMPLETED·AS 만) — J1 은 "같은 달 키"만 주장이라 맞음. `received_date` 는 String NOT NULL(빈 글자 가능). origin/deploy 는 `5f714be` 로 1커밋 전진, 마이그레이션 변화 없음 | 반영 — §3.2 received_date 빈 글자면 created_at |

## ④ 3단계 반증 재검수 (T18, 2026-11-07, HEAD ca13493af — 재현 시험 3개 통과로 높음 1~3 실재 확인)

| # | 심각도 | 내용 | 처리 |
|---|---|---|---|
| R1 | 높음 | 내 주문 `schedule.as_visit.schedule_link` 에 남의 주문 번호 → 편집 화면·모바일 상세 AS 배너에 남의 고객명·시공일, 없는 번호면 존재 여부까지(`foms/api/erp_orders_structured.py:561-568` 깊은 합치기, `foms/services/as_dashboard_display.py:368-487`) | 반영 `55c14eb21` — 저장 때 못 읽는 주문 링크 거부 · 배너는 보는 사람 판정 |
| R2 | 높음 | structured PUT 으로 `settlement.deductions` 를 지우거나 취소 표시 → 차감 회피(모든 직원에게도 구멍, `SERVER_LOCKED_KEYS` 에 settlement 없음) | 반영 `55c14eb21` — settlement 서버 잠금(모든 직원) |
| R3 | 높음 | 부 담당 프리랜서가 대표 담당 이름을 자기로 → 수수료 가로채기 · 원래 담당 연결 삭제. `SELF_EDIT_PATHS` 에도 없음 | 반영 `f981ea903`(D21 막기) · `55c14eb21`(본인 수정 표시) |
| R4 | 중간 | structured PUT 이 `payment.*_confirmed/_by/_by_user_id` 통째 덮음 → 입금 확인 위조(모든 직원) | 반영 `55c14eb21` — 입금 확인 칸 10개 서버 고정(모든 직원) |
| R5 | 중간 | 실측일·시공일·출고가 바꾸기는 표시만(설계상 허용) — 시공 완료 뒤 변경 거부 또는 마감 때 확인 | 보류 — 표시 유지, 마감 확인은 다음 |
| R6 | 낮음 | ERP 초안 토큰 4길이 초안 주인 확인 안 함(무작위 UUID) | 반영 `55c14eb21` — 토큰 초안은 작성자 = 나 |
| R7 | 낮음 | 마법사 등록 중복 확인이 남의 주문 번호를 돌려줄 수 있음(`erp_order_draft.py:634`) | 반영 `55c14eb21` — 중복 확인은 내가 만든 주문만 |
| R8 | 낮음 | 마법사 첨부 key `..` 정리 판정 한쪽만, 첨부 승격이 앞부분 검사 안 함(파일 관문이 지금은 막음) | 반영 `f981ea903` — 정규형 key 만 · 승격은 내 초안 폴더 |
| R9 | 낮음 | 되채우기 CREATOR 가 손님 값 `OrderDraft.order_id` 를 믿음 | 반영 `55c14eb21` — 생성 이벤트만 근거 |

막힘 확인(음성 대조군): 남의 주문 편집 직접 열기 404 · 내 수수료 ?order=/?user_id= · 파일 관문 `..` 400 · draft 표시로 발주사 잠금 우회 불가 · 정규화 우회 불가 · 실측 판 집계 · 마법사 발송 4종 · 변경 이력 본인만 · 이벤트 속 다른 주문 번호는 404.

## ⑤ D26 반증 재검수 (2026-11-07, 독립 검토 1명 — 코드 · 테스트 앱 실행)

| # | 심각 | 발견 | 처리 |
|---|---|---|---|
| V1 | 높음 | `POST /api/orders/<id>/wdc-estimate-sync` 가 본문 `estimate_id` 의 견적을 주문 연결 확인 없이 덮어씀(모든 직원 공통) | 계산기 묶음 작업자가 핸들러에서 `EstimateOrderMatch(estimate_id, order_id)` 확인. 그 전까지 프리랜서 목록에서 뺌 |
| V2 | 중간 | AS 기준 일정 잇기 · 영업 전달 배정이 남의 주문 시공일 · 실측일 · 담당자 · 존재를 돌려줌 | `_resolve_schedule_link_ref` · `_resolve_sales_delivery_ref` 에 `can_read_ref_order`(없는 주문과 같은 404). 시험 + 음성 대조군 |
| V3 | 중간 | 실측일을 옮겨 예전/새 주문을 오가며 잠금을 풀었다 되돌림 | D27 로 날짜 판정 자체가 없어짐(자기 주문 = 회사 직원과 같음, 사용자 수용) |
| V4 | 낮음 | 차감 귀속 사람 번호로 직원 명단 · 팀 알아내기 | 남음 — 프리랜서도 회사 직원과 같게(D27) 하라는 결정이라 보통 직원과 같은 답. 문구 통일은 따로 |
| V5 | 낮음 | 만든 날 비교 UTC 9시간 | D27 로 날짜 판정 없어짐 |
| V6 | 낮음 | 프리랜서 둘이 한 주문에 걸릴 때 | D27 로 날짜 판정 없어짐. 남의 수수료 주문 바꾸기는 회사 직원과 같은 위험(수수료 탭 표시) |
