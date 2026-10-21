# 협력사 화면을 우리 주문 화면 그대로 — 협력사 모드 SPEC (2026-10-19 승인 · 1·2단계 운영 · 3단계 구현 중)

등급: 코어 변경(Auth · API · 화면) — Spec → 승인 → 구현.
선행 설계서: `docs/specs/2026-10-08-partner-portal_SPEC.md`(1~3단계 · §16 담당 = 협력사 직원). 이 문서는 그 화면 부분을 대체한다.
목업: https://claude.ai/artifact/FtF9mhLWGub3ZjmP6iGj7p (7판, 사용자 비공개 링크). 스테이징 `/edit/4382` 를 PC 1440px · 모바일 390px 로 찍어 칸 순서를 옮겼다.

## 0. 사용자 결정 (2026-10-18 ~ 19)

- 협력사도 PC 와 휴대폰 모두에서 일한다. 화면은 **우리 FOMS 주문 화면(erporder) 그대로** 쓰고, 협력사에게 필요 없는 기능만 뺀다.
- 완공 사진을 볼 수 있어야 하고, **그 탭에서 바로 AS 접수**가 된다.
- 협력사도 **제품이 여러 개**이고 **복잡한 치수 입력**(제품마다 규격 여러 줄, 복합 폭 `5700(2402+1864+1434)` · `2352+2100+2860`)이 우리와 같게 필요하다.
- **실측 사진**을 첨부할 수 있어야 한다(제품별 + 공통).
- 제품 속성은 우리와 같은 다섯 칸: 내부 · 색상 · 옵션 · 손잡이 · 기타·설치(한 칸).
- PC 일정 칸은 한 줄(실측일 · 시공일 · 시공시간).
- 목업 7판으로 간다("이대로 가자").

## 1. 지금 코드의 사실

1. 협력사 화면은 단독 문서다(`templates/partner/*`, `static/css/contexts/partner/partner-portal.css`). 우리 화면 틀을 쓰지 않고, PC 에서도 가운데 860px 한 줄이다(2026-10-18 스테이징 실화면).
2. 우리 주문 화면은 열 때 **주문 데이터 전체**를 페이지에 싣는다: `_build_erp_order_bootstrap` 이 `structured_data` 통째(입금 · 잔금 · 견적 · 내부 비고 포함)를 `erp-order-bootstrap` JSON 으로 넣는다(`foms/web/orders/edit.py:678-692`, `templates/orders/partials/edit_order_body.html:27`). → 칸을 가리는 방식으로는 협력사에게 줄 수 없다.
3. 우리 저장은 주문 전체를 덮어쓰는 `/api/orders/<id>/structured`, 업로드는 주문 범위를 따지지 않는 `/api/upload/session` 이다. 협력사에게 열면 안 된다(지금 문지기가 막고 있다 — 그대로 둔다).
4. 협력사 품목 입력(`foms/services/partners/orders.py:68-92` `_clean_items`): 품목 30개까지는 되지만 **품목마다 규격 1줄**, 치수 칸 **20자**에서 자름, 제품 속성 칸 없음, 품목 메모는 `misc` 로 들어간다.
5. 협력사 사진은 주문 공통 폴더(`orders/<id>/partner_measurement/`)에만 올라가고 품목에 묶이지 않는다. 품목 사진 연결의 기준 칸은 `OrderAttachment.item_id`(`order_item_identities` UUID)이고(`models.py:363-368`), 품목 식별자는 주문을 만들 때 `order_create._mint_item_identities` 가 발급한다.
6. 제품 속성 키: `internal` · `color` · `option_detail` · `handle` · `misc`(`static/js/orders/erp-order-shared.js:1563-1575`). 모바일 이름표 "기타 / 설치위치"도 같은 `misc` 한 칸이다(`:1695`).
7. 완공 사진 = 첨부 분류 `construction`(`foms/web/cs/completion_dashboard.py:410` `_completion_construction_photos`). 협력사 상세는 협력사가 올린 원본만 골라 보여 준다(`foms/web/partner/__init__.py` · `is_partner_original_key`). 파일 열람 관문은 자기 회사 주문이면 이미 열려 있다.
8. AS 진행 읽기: `project_current_as_cycle(order)` → `{cycle_id, status, visit_date, visit_time, classification, opened_at}`(`foms/services/orders/as_cycle_service.py:160`).
9. 협력사 계정은 알림을 받지 않는다(`INTERNAL_USERS_ONLY`, 선행 설계서 §16.3). 도면 확인 차례가 와도 모른다.
10. 관리자가 협력사 계정으로 전환하면 협력사 화면에 돌아가기 버튼이 없다(`templates/partner/layout.html` 은 로그아웃만). `auth.switch_back` 은 문지기 허용 목록에 이미 있다.
11. 새 협력사 라우트는 허용 목록(`foms/services/auth/partner_scope.py` `PARTNER_ALLOWED_ENDPOINTS`)과 매니페스트 2개(`docs/harness/foms_order_mutation_policy_manifest.json`, `docs/harness/foms_write_guard_manifest.json`)에 같이 넣는다.
12. 우리 주문 화면 템플릿은 크다: `erp_order_tab.html` 749줄, `erp_order_tab_mobile.html` 698줄, `edit_order_body.html` 652줄.
13. (3단계 착수 때 확인) 우리 주문 화면은 값 · 품목 · 금액 · 첨부를 서버가 그리지 않는다. `erp-order-shared.js`(6,278줄) `erpLoadStructured` 가 주문 데이터 전체로 브라우저에서 채운다. 같은 파일이 저장(`PUT /structured`) · 탭을 다시 열 때 다시 읽기(`GET /structured`) · 실측 일정판 30초 조회를 함께 한다.
14. `erpLoadStructured` 는 칸 14개(`erp-customer-name` · `erp-items` 등)를 있는지 확인하지 않고 쓴다 — 구역을 서버에서 빼면 거기서 멈춘다.
15. 우리 바깥 틀(`orders/layout.html` → `layout_nav` · `layout_head` · `layout_scripts`)은 알림 벨 · 실시간 연결 · 채팅 · 긴급 호출을 싣고, 한 번에 끄는 장치가 없다.

## 2. 설계 원칙

- ~~**화면 틀은 하나.** 우리 템플릿 · CSS · JS 부품을 그대로 쓰고 "협력사 모드"에서 구역을 끈다.~~ → **2026-10-19 바꿈(§5-8)**: 우리 디자인 부품(CSS 파일 · 마크업 클래스)을 그대로 싣고, 화면 파일(템플릿 · JS)은 협력사 것을 따로 둔다.
- **뺌은 서버에서.** (a) 데이터는 협력사 투영 함수가 고른 키만 페이지에 싣는다, (b) 뺄 구역은 Jinja 가 아예 그리지 않는다, (c) 협력사 쓰기는 협력사 전용 API 로만 간다. CSS 로 가리는 것은 뺌이 아니다.
- **구역 단위로 끈다.** 칸 하나하나에 분기를 넣지 않고 구역(접수 표시 · 발주 · 금액 · 발송 · 실측 일정판 · 계산기 · 견적서)으로 묶는다 — 직원 화면이 깨질 자리를 줄이려는 것.
- **주소는 협력사 쪽에 둔다.** 협력사는 지금처럼 `/partner/...` 주소만 쓴다. 우리 `/edit/<id>` 를 협력사에게 열지 않는다. 같은 템플릿을 협력사 라우트가 협력사 모드로 그린다.
- **원본 보존은 그대로.** `structured_data.partner_intake` 사본 규칙(선행 설계서 §5.2 · §15)을 지킨다.
- **우리 직원 화면은 바뀌지 않는다.** 대조군 시험으로 고정한다.

## 3. 화면 (목업 7판 기준)

### 3.1 맨 위
- PC 머리줄 · 메뉴 줄, 모바일 위 줄 · 아래 탭은 우리 것 그대로.
- 뺌: 긴급 호출(⚡), 담당 배정 아이콘, 내부 메뉴(접수 · 실측 · 네이버 수집 · 자가실측 · 지방 주문 · 휴지통 · 관리자 · ERP 대시보드 · 계산기 · 채팅).
- 협력사 메뉴: 회사 주문 · 도면 확인(내 차례 수) · 완공 사진·AS · 새 주문. 모바일 아래 탭: 주문 · 도면 확인 · 새 주문 · 완공·AS · 더보기(내 정보 · 연락처 · 로그아웃).
- 관리자가 전환해 들어온 경우 "관리자로 돌아가기" 버튼(POST `auth.switch_back`).

### 3.2 주문 목록
- PC = 우리 ERP 대시보드 틀: 프로세스 맵(협력사 쉬운 단계 7칸, "도면 확인"만 노란 강조) · 필터 줄(검색 · 단계 · 담당 · 내 차례만 · 내 담당) · 작업 큐 표(단계 · 현재 작업 · 고객 · 연락처 · 주소 · 제품 · 시공일).
- 모바일 = 우리 큐 카드: 검색 + 필터, 칩, "지금 내 차례" 묶음, 카드마다 진행 막대.
- 뺌: 대시보드 아래 내부 메뉴, 경보 칸 · D-day 경보, 실측일 칸.

### 3.3 주문 화면 (우리 `/edit` · 모바일 "주문 수정" 틀)

탭: ERP Order · 계산기 · 견적서 · 변경 이력 → **주문 · 도면 · 완공 사진 · 이력**.

| 우리 화면 칸 (위에서부터) | 협력사 | 비고 |
|---|---|---|
| 접수인 · 접수일 · 접수시간 | 보기 | 접수인 = 보낸 협력사 직원 |
| 긴급 · 자가실측 · 지방주문 · 긴급 사유 · 지방주문 구분 | 뺌 | 내부 표시 |
| 고객명 · 연락처 · 연락처 특이사항 | 보기 | 원문 잠금. 수동입력은 뺌 |
| 발주사 · 시공 담당자 · 비고 | 뺌 | |
| 담당자 | 바뀜 | 같은 회사 직원 중에서만(지금 코드 그대로) |
| 본공정 단계 · 강제 · AS 접수 수정 | 바뀜 | 쉬운 단계 + 진행 막대(보기만). 강제 뺌, AS 는 완공 사진 탭 |
| 주소 · 주소 특이사항 | 보기 | 찾기 버튼 뺌 |
| 실측 일정 현황판 · 실측시간 · 시공 특이사항 | 뺌 | |
| 실측일 · 실측 특이사항 | 보기 | |
| 시공일 · 시공시간 | 바뀜 | 우리가 정하고 보기만. PC 는 실측일과 한 줄 |
| 제품 항목(목록 · 제품명 · 규격 여러 줄 · 제품 속성 다섯 칸 · 추가 입력 · 품목 실측 사진 · 전체 항목 요약) | 바뀜 | "접수 확인 중"(RECEIVED · MEASURE)에는 새 주문처럼 고침, 그 뒤 보기만(바꿀 것은 수정 요청) |
| 항목 금액 · 출고가 합계 · 항목 실측일 · 항목 시공일 | 뺌 | |
| 저장 · 출고가 · 예약금 · 잔금 · 현금영수증 | 뺌 | 저장 자리 → 단계 버튼 |
| 기존주문 변환 · 발주/영발/실측/AS PUSH · 알림톡 · 변환 · 복사 · 발송 기록 줄 | 뺌 | 협력사 주문은 고객 발송 금지 |
| 공통 첨부 올리기 | 바뀜 | 접수 확인 중에만, 실측 사진 · 초안 도면 두 분류, 협력사 API |
| 첨부 갤러리 실측 · 도면 · 시공 · AS | 바뀜 | 실측 = 협력사가 보낸 것, 도면 = 최종 도면만(삭제 없음), 시공 = 완공 사진 탭, AS = 접수 사진 |
| 모바일 아래 버튼 저장 · PUSH · 알림톡 | 바뀜 | 단계 버튼: 수정 요청 · 이대로 만들어 주세요 / AS 접수 |

### 3.4 새 주문 등록
- 우리 제품 항목 입력 그대로: 왼쪽 항목 목록 · 검색, 오른쪽 상세, Ctrl+↑↓ 이동, 이전 · 다음, 전체 항목 요약.
- 제품명은 목록에서 고르거나 직접 입력. 규격은 품목마다 여러 줄, W*D*H 붙여넣기 자동 분해, 복합 폭은 콤마.
- 제품 속성 다섯 칸(모르면 "상담"). 추가 입력.
- 품목마다 실측 사진(PC: 즉시 추가 · Ctrl+V · 끌어놓기, 휴대폰: 찍기 · 앨범). 아래 공통 첨부에서 현장 전체 사진 · 초안 도면, 올린 공통 사진은 품목에 연결 · 해제.
- 꼭 넣을 칸은 지금과 같다: 고객명 · 연락처 · 주소 · 품목 1개. 주소 찾기는 새로 넣는다.

### 3.5 도면 탭
- 최종 도면을 그림으로 바로 보여 준다(지금은 파일 이름 링크 · 새 탭). 회차 · 올린 때 표시.
- "이대로 만들어 주세요" · "수정 요청 보내기"(고칠 곳 + 참고 사진 10장) — 서버 동작은 지금 그대로(`approve_partner_drawing`, `request_partner_revision`).

### 3.6 완공 사진 탭 + AS
- 우리 시공팀 사진(분류 `construction`)을 그대로 보여 준다. 시공이 끝나기 전에는 탭을 끈다.
- 사진을 눌러 고르면 옆(PC) · 아래 시트(휴대폰)의 AS 접수 칸에 붙는다. 고객이 보낸 사진도 더할 수 있다.
- "고객에게 보낼 사진 내려받기"(휴대폰: 사진첩 저장). 고객 전달은 협력사 몫.
- 진행 중인 AS 가 있으면 접수 칸 대신 진행 상황: 접수 → 우리 확인 → 방문 예정(날짜 · 시간) → 처리 완료(처리 사진). 읽기는 `project_current_as_cycle`.

### 3.7 이력 탭
- 협력사가 볼 일만 고른 줄: 주문 보냄, CS 확인 → 도면 작업, 최종 도면 N회차, 수정 요청(누가 · 내용), 승인(누가 · 언제 · 회차), 시공일 정해짐, AS 접수 · 방문 · 완료. 우리 내부 변경 이력과 다르다(우리 직원 이름 · 내부 메모는 넣지 않는다).

## 4. 서버에서 바뀌는 것

1. **협력사 투영** `build_partner_order_view(order)` (새 함수, `foms/services/partners/`): 3.3 의 "보기 · 바뀜" 칸 값만 담는 허용 키 목록 방식. 협력사 모드 템플릿과 JS 는 이 묶음만 받는다. `_build_erp_order_bootstrap` 은 협력사 라우트에서 부르지 않는다.
2. **협력사 모드 렌더링**: 우리 주문 화면 템플릿에 `partner_mode` 하나를 넘기고, 3.3 의 뺄 구역을 구역 단위로 감싼다. 협력사 모드에서는 계산기 · 견적 · 발송 · 저장 JS 모듈을 싣지 않는다(빈 데이터로 터지는 것을 막는다).
3. **품목 입력 확장** (`create_partner_order` · `_clean_items`): 품목 모양을 우리와 같게 — `product_name`, `spec_rows`(여러 줄, 줄 수 상한), `quantity`, `internal` · `color` · `option_detail` · `handle` · `misc`, 추가 입력. 치수 칸 상한을 20자에서 우리 입력이 받는 길이로 올린다. 원문 사본(`partner_intake`)도 같은 모양으로 남긴다.
4. **접수 확인 중 품목 고치기**: 새 협력사 API(예: `PUT /api/partner/orders/<id>/items`). RECEIVED · MEASURE 에서만, 다른 회사 주문 404, 그 밖 단계 409. 고친 기록을 감사에 남긴다.
5. **품목 실측 사진**: `upload_file` 에 선택 칸 `item_id` 를 더한다(그 주문의 품목 식별자가 아니면 400). 공통 사진을 품목에 연결 · 해제하는 협력사 API. 접수 확인 중에만.
6. **완공 사진 읽기** + **AS 접수에 고른 완공 사진 붙이기**: 같은 파일을 첨부 두 줄로 복제하지 않는다(AS 첨부를 지울 때 시공 사진 원본이 같이 지워질 위험). AS 접수 기록에 고른 완공 사진 id 목록으로 남긴다.
7. **AS 진행 읽기**: `project_current_as_cycle` 결과에서 상태 · 방문일 · 방문시간 · 처리 사진만 협력사 투영에 넣는다(비용 판정 등 내부 값은 넣지 않는다).
8. **새 라우트는 전부** 허용 목록 + 매니페스트 2개 + "다른 회사 주문으로 부르면 거부" 시험을 1:1 로 둔다(선행 설계서 §11).

## 5. 결정 (2026-10-19 사용자 승인)

1. 시공 특이사항(시공팀 메모)은 협력사에게 **보여 주지 않는다**.
2. 우리 화면 "지방주문 구분"의 "협력사" 값과는 섞지 않는다 — 판정은 `partner_org_id` 만(기본값 그대로).
3. 도면 작업이 시작된 뒤에는 협력사 실측 사진 추가를 **막는다** — 수정 요청의 참고 사진(10장)으로 보낸다.
4. 접수 확인 중 협력사가 품목을 고치면 원문 사본(`partner_intake`)도 **같이 바꾸고**, 누가 · 언제 · 무엇을 고쳤는지 기록을 남긴다.
5. 협력사가 보는 품목 값은 도면팀이 고친 현재값(기본값 그대로). 원문과 다를 때 표시는 이번 범위 밖.
6. 협력사 알림 방식은 6단계에서 따로 정한다.
7. 1단계부터 시작한다.
8. (2026-10-19, 3단계 착수 때) **우리 디자인 부품 + 협력사 화면 파일.** §1-13 ~ 15 때문에 "우리 화면 파일에 협력사 모드"는 직원 화면을 깨뜨릴 위험이 크다. 협력사 화면은 우리 CSS(Bootstrap · `style-pro-max.css` · `foms-tokens.css` · `erp-pro.css` · `erp-items-master-detail.css`)와 같은 마크업 클래스로 그리고, 템플릿 · JS 는 `templates/partner/` · `static/js/partner/` 에 둔다. 우리 직원 화면 파일은 바꾸지 않는다. 대가: 우리 화면 모양이 바뀌면 협력사 화면을 따로 맞춘다.
9. 3단계는 셋으로 나눈다: 3-1 주문 화면(+ 접수 확인 중 품목 고치기) → 3-2 주문 목록(대시보드 모양) → 3-3 도면 미리보기 · 이력.

## 6. 단계 (각 단계 끝마다 deploy · 스테이징 실화면 확인)

실운영이 2026-10-19 부터라, 실주문에 바로 필요한 입력부터 한다. 1 · 2단계는 지금 협력사 화면에 먼저 붙이고 서버 부품은 3 · 4단계에서 그대로 쓴다.

1. **품목 입력 확장 + 품목 실측 사진** (4.3 · 4.5) — 지금 협력사 새 주문 화면에 규격 여러 줄 · 긴 치수 · 제품 속성 · 품목 사진.
2. **완공 사진 + 그 자리 AS 접수 + AS 진행 + 관리자 돌아가기 버튼** (4.6 · 4.7 · 3.1).
3. **협력사 투영 + PC 화면을 우리 틀로** (4.1 · 4.2 · 3.2 · 3.3 · 3.5 · 3.7 · 4.4) — 협력사 PC 를 ERP 대시보드 · `/edit` 틀로 바꾸고 지금 단독 화면을 걷는다.
4. **모바일 화면을 우리 틀로** (3.2 · 3.3 모바일).
5. **새 주문 등록을 우리 틀로** (3.4 — 1단계 입력을 우리 제품 항목 부품으로 옮김).
6. **협력사 알림** (5-6 결정 뒤 별도 설계).

## 7. 바꾸지 않는 것

- 우리 직원의 화면 · 권한 · 저장 API.
- 협력사 고객 발송 차단(`partner_order` 409), 협력사 로고 · 담당 연락처 도면 표기, 승인 · 수정 요청 서버 동작.
- 문지기 기본 거부 구조(허용 목록 밖은 모두 막음).

## 8. 검증 (완료 기준)

- `python -c "import app; print('APP_OK')"`.
- 투영 시험: 협력사 페이지 원문(HTML + 실린 JSON)에 금액 · 견적 · 입금 · 잔금 · 비고 · 내부 일정 키가 **0개**. 같은 주문을 우리 직원으로 열면 그대로 있음(대조군).
- 직원 화면 대조군: 협력사 모드 분기를 넣은 뒤 우리 `/edit` · ERP 대시보드 HTML 이 바뀌지 않음.
- 쓰기 시험: 다른 회사 주문 404, 접수 확인 중이 아닌 품목 수정 409, 다른 주문의 `item_id` 로 사진 올리기 400, AS 접수에 남의 완공 사진 id 거부.
- 품목 시험: 규격 3줄 · 복합 폭(`5700(2402+1864+1434)`, `2352+2100+2860`) · 제품 속성 다섯 칸이 저장되고 도면 마법사 · 우리 주문 화면에 그대로 보임.
- `python -m pytest tests/security/test_partner_gate.py tests/security/test_partner_manager.py -q` 와 새 시험 green, PG 레인(담당 교체 · 품목 식별자).
- 스테이징: CLAUDE-TEST 협력사로 PC 1440px · 휴대폰 390px 실화면(등록 → CS 도면 전달 → 승인 → 완공 사진 → AS 접수). 시험 계정은 끝나면 다시 끈다.
- `scripts/ops/pre_push_smoke.ps1` exit 0, push 뒤 CI green.

## 9. 남는 위험

- 우리 주문 화면 템플릿이 커서(1.12) 협력사 분기를 넣다가 직원 화면이 깨질 수 있다 → 구역 단위 분기 + 직원 화면 대조군 시험 + 단계별 실화면.
- 우리 JS 가 투영에 없는 키를 읽다 멈출 수 있다 → 협력사 모드에서는 해당 모듈을 싣지 않고, 실화면에서 콘솔 오류 0건을 확인한다.
- 협력사 모드가 직원 라우트 성능 예산(pre_push perf guard)에 끼지 않게 한다.
- 협력사 알림이 6단계까지 없다 → 그동안 CS 가 도면 확인 차례 · 시공일을 전화로 알린다(운영 규칙).

## 10. 1단계 구현 기록 (2026-10-19)

- 품목 모양(`foms/services/partners/orders.py` `_clean_item` · `_clean_spec_rows`): `spec_rows` 여러 줄(`MAX_SPEC_ROWS` 20, 빈 줄은 버리고 최소 한 줄), 치수 칸 `DIM_LIMIT` 100자(예전 20자), 제품 속성 `ATTRIBUTE_KEYS`(internal · color · option_detail · handle · misc) 빈 칸은 키를 만들지 않음, `extra_input` 2000자. 옛 모양(`width/depth/height/memo`)도 받는다 — 옛 `memo` 는 지금처럼 `misc`. 원문 사본(`partner_intake.items`)은 같은 모양, 작업본에만 주문 생성 때 품목 `uid` 가 붙는다.
- 등록 응답에 `item_count`. 업로드(`POST /api/partner/orders/<id>/files`)에 선택 칸 `item_index` — 실측 사진만, 그 주문의 품목 범위 안만(밖이면 400), `item_id` 는 `resolve_active_item_id` 로 같이 채운다(우리 직원 업로드와 같은 묶음). 새 라우트 없음(허용 목록 · 매니페스트 변경 없음).
- 화면: `templates/partner/new_order.html` 제품 항목 카드(규격 줄 추가 · 빼기, W*D*H 붙여넣기 분해, 속성 다섯 칸, 추가 입력, 제품 실측 사진), 입력 로직은 새 파일 `static/js/partner/partner-items.js`(JS 300줄 규칙 때문에 분리). 수량 칸은 우리 화면처럼 뺐다(서버는 기본 "1" 유지, 상세는 1이 아닐 때만 표시). 상세는 규격 모든 줄 · 속성 · 추가 입력, 제품 사진에 품목 이름.
- 시험: `tests/security/test_partner_items.py` 8건(여러 줄 · 복합 폭 · 속성 · 원문 사본, 옛 모양 대조군, 길이 · 줄 상한, 빈 줄, 품목 사진 item_index · item_id 와 공통 사진 대조군, 잘못된 번호 · 초안 거부, 다른 회사 404, 상세 표시).

## 11. 2단계 구현 기록 (2026-10-19)

- 새 서비스 `foms/services/partners/completion.py`: `construction_photos_for_partner`(첨부 분류 `construction`, 올린 순서), `as_progress_for_partner`(`project_current_as_cycle` 의 상태 · 방문일 · 방문시간 · 접수일 + 현재 AS 건 로그 줄에 붙은 `as` 사진만 — 비용 판정은 넣지 않음), `pick_construction_photos`(이 주문의 `construction` 사진만, 고른 순서 · 중복 제거 · 20장, 아니면 400). services 는 api 를 부를 수 없어(층 의존 규칙) 사진 주소는 웹 층(`foms/web/partner/__init__.py` `_with_urls`)이 만든다.
- AS 접수(`POST /api/partner/orders/<id>/as`)에 선택 칸 `construction_photo_ids`(여러 개). 다른 회사 주문은 사진 검사 전에 404. 고른 사진은 첨부를 복제하지 않고 접수 원문 줄에 `ref_attachment_ids` 로 남기고, 원문 끝에 `[완공 사진 참고] 파일명, …` 한 줄을 붙여 우리 AS 화면에서 바로 보이게 했다. 고른 사진이 없으면 원문은 지금과 같다. 새 라우트 없음.
- 화면(`templates/partner/order_detail.html`): 시공이 시작된 뒤(`AS_OPEN_STAGES`) "완공 사진 · AS" 칸 — 사진 격자에서 골라 바로 AS 접수, 진행 중인 AS 면 상태 · 접수일 · 방문 예정(날짜 · 시간) · AS 사진, 끝난 AS 는 "지난 AS" 한 줄. 사진이 없으면 "아직 완공 사진이 없습니다" + 접수 칸.
- 관리자 돌아가기: `templates/partner/layout.html` 머리줄에 세션 `impersonating_from` 이 있을 때만 "관리자로 돌아가기"(POST `auth.switch_back`, 문지기 허용 목록에 이미 있음).
- 시험: `tests/security/test_partner_completion.py` 8건(시공 전 숨김 · 실측 사진 대조군, 사진 없을 때 접수 칸, 고른 사진 id · 덧붙임 · 첨부 복제 없음, 사진 없는 접수 대조군, 다른 주문 · 다른 분류 · 숫자 아님 · 없는 id 거부와 AS 미개설, 다른 회사 404, 진행 상황 방문일 · AS 사진 · 접수 칸 없음, 돌아가기 버튼 대조군).
- 스테이징 실화면(2026-10-19, CLAUDE-TEST 협력사 · 시험 주문 #4774 휴지통): 완공 사진 썸네일 표시 → 골라 AS 접수 → 진행 상황(접수됨 · 접수일 · 방문 미정) 표시, 우리 쪽 접수 원문 `[완공 사진 참고] …` + `ref_attachment_ids`, 첨부 복제 없음. 이때 "관리자로 돌아가기"가 직전 주소(`/partner`, 협력사 전용)로 돌아가 관리자에게 막힌 화면이 뜨는 문제를 찾아 `switch_back` 이 협력사 화면에서 왔을 때만 협력사 관리로 보내게 고쳤다(대조군 시험 포함).

## 12. 3-1 주문 화면 설계 (2026-10-19)

- 바깥 틀: `templates/partner/layout.html` 이 우리 CSS 를 싣고 우리 머리줄 · 메뉴 줄 모양(`layout-header` · `layout-global-nav`)을 그린다. 협력사 메뉴: 회사 주문 · 새 주문. 벨 · 실시간 연결 · 채팅 · 긴급 호출은 싣지 않는다.
- 협력사 투영 `foms/services/partners/view.py` `build_partner_order_view(order)`: 허용 키만(주문 번호 · 고객 이름 · 연락처 · 연락처 특이사항 · 접수인 · 접수일 · 접수시간 · 담당 · 쉬운 단계와 진행 칸 · 주소 · 주소 특이사항 · 실측일 · 실측 특이사항 · 시공일 · 시공시간 · 보낸 메모 · 품목(제품명 · 규격 줄 · 수량 · 속성 다섯 칸 · 추가 입력 · uid)). 품목은 도면팀이 고친 현재값(§5-5). 금액 · 견적 · 입금 · 비고 · 시공 특이사항 · 내부 표시는 넣지 않는다.
- 주문 화면(`templates/partner/order_detail.html` + `templates/partner/partials/*`): 우리 `/edit` 카드 · 탭(주문 · 도면 · 완공 사진) · 칸 순서. 제품 항목은 우리 왼쪽 목록 · 오른쪽 상세(같은 클래스) — 넓은 화면만, 좁은 화면은 지금처럼 카드를 차례로. 아래 고정 줄에 단계 버튼(도면 확인 차례: 수정 요청 · 이대로 만들어 주세요 / 접수 확인 중: 품목 저장 / 시공 뒤: AS 접수).
- 품목 고치기 `PUT /api/partner/orders/<id>/items`(§4-4): 접수 확인 중(RECEIVED · MEASURE)만, 다른 회사 404, 그 밖 409. 협력사가 고칠 수 있는 키(제품명 · 규격 줄 · 수량 · 속성 다섯 칸 · 추가 입력)만 바꾸고 나머지 품목 키(금액 · 품목 일정 · 취소 표시 등)는 uid 로 짝지어 그대로 둔다. uid 는 `ensure_item_uids`(이 주문에 있던 값만 인정). 원문 사본(`partner_intake.items`)도 같이 바꾸고 `partner_intake.item_edits` 에 누가 · 언제 · 바꾸기 전 품목을 남긴다(§5-4, 최근 20번). 품목에 묶인 첨부는 uid 로 새 자리를 찾아 `item_index` · `item_id` 를 옮기고, 지운 품목의 사진은 공통 사진이 된다. 감사 1줄 + CS 팀 알림.

## 13. 3-1 구현 기록 (2026-10-19)

- 투영 `foms/services/partners/view.py`(`build_partner_order_view`, 허용 키 23개 — 시험이 키 목록을 고정한다). 품목 고치기 `foms/services/partners/items_edit.py`(`update_partner_items`, 쓰기 정책 id `PARTNER_ITEMS_EDIT`, `execute_single_order_write` 경유라 쓰기 목록 허용 파일에 CANONICAL 로 올림), 라우트 `PUT /api/partner/orders/<id>/items`(`partner_api.update_items` — 문지기 허용 목록 · 쓰기 목록 2개에 추가). 감사 `PARTNER_ORDER_ITEMS_EDITED` + CS 팀 알림(`PARTNER_ORDER_ITEMS_EDITED`).
- 화면: `templates/partner/layout.html`(우리 CSS · 머리줄 · 메뉴 줄), `templates/partner/order_detail.html` + `templates/partner/partials/`(`order_info` · `order_items` · `order_files` · `order_drawing` · `order_completion` · `order_actions` · `item_card`). 제품 항목 카드는 새 주문 화면과 같은 매크로(`item_card.html`)를 쓴다 — 고칠 때와 볼 때 같은 칸. 도면 확인 차례면 도면 탭을 먼저 연다.
- JS: `partner-items-rail.js`(왼쪽 목록 · 오른쪽 상세, 992px 이상만), `partner-order.js`(탭 · 품목 저장 → 품목 사진 올리기), `partner-items.js` 는 서버가 그린 카드를 그대로 고치고 uid 를 돌려보낸다.
- 시험: `tests/security/test_partner_order_screen.py` 8건(화면 원문에 금액 · 견적 · 입금 · 시공 메모 · 긴급 사유 · 비고 0개와 우리 직원 부트스트랩 대조군, 투영 키 목록, 접수 확인 중에만 고치는 칸, uid · 우리 쪽 품목 키 보존 · 원문 사본 · 고친 기록 · 감사 · CS 알림, 남의 uid 거부, 품목 사진 자리 옮기기 · 지운 품목 사진은 공통으로, 도면 단계 409 · 다른 회사 404 · 빈 품목 400, 우리 직원 호출 거부).

## 14. 3-2 주문 목록 구현 기록 (2026-10-19)

- 서비스 `foms/services/partners/order_list.py`: `partner_order_board`(프로세스 맵 7칸 수 · 내 차례 수 · 거른 작업 큐 최근 200건, 내 차례를 맨 위로), `partner_list_filters`(검색 · 단계 · 담당 · 내 차례만 · 내 담당 — 모르는 값은 버림), `partner_turn_count`(머리 메뉴 수). 자기 회사 운영 주문의 평면 칸만 읽는다(JSONB 안 읽음). 담당은 SALES 배정(협력사 직원) 기준. 검색은 고객 · 주소 · 제품 글자, 주문 번호(같은 숫자), 연락처(숫자 4자리 이상).
- "내 차례" = 쉬운 단계 "도면 확인 대기"(CONFIRM, AS 건 열림 제외).
- 화면 `templates/partner/home.html`: 우리 `erp-pro-card` · `erp-pro-pipeline` · 필터 줄 · 작업 큐 표(단계 · 현재 작업 · 고객 · 연락처 · 주소 · 제품 · 시공일 · 담당). 768px 미만은 표 대신 카드(지금 내 차례 묶음 · 진행 막대). 경보 칸 · D-day · 실측일 칸 · 내부 메뉴는 없다. 머리 메뉴에 "도면 확인 N"(내 차례) · "완공 사진 · AS"(완료 단계) 링크.
- JS: 필터 줄은 고르면 바로 거르고, 작업 큐 줄을 누르면 주문 화면으로(`partner-portal.js` `bindBoard`). 인라인 스타일 · 인라인 이벤트는 쓰지 않는다.
- 시험 `tests/security/test_partner_order_list.py` 4건(칸별 수 · 다른 회사 제외 · 내 차례 맨 위, 필터 다섯 가지와 모르는 값 무시, 목록 화면 · 단계 거르기, 모든 화면 머리 메뉴 차례 수와 다른 회사 대조군).

## 15. 3-3 도면 미리보기 · 이력 설계 (2026-10-20)

### 15.1 사실
- 우리 화면은 그림 도면만 그림으로 보여 준다. 고객 공유 화면(`foms/api/share.py` `share_view`)은 그림 도면을 `drawing/partials/drawing_mobile_v2_gallery.html`(카드 + `static/js/foms/lightbox.js` 확대 · 넘기기 · 저장)로, PDF 등은 파일 줄로 보여 준다. 우리 직원 미리보기 창도 PDF 는 "미리보기를 지원하지 않습니다"다. PDF 를 그림으로 바꾸는 부품은 없다(새 패키지 필요).
- 협력사는 `files.view` · `files.download` 를 이미 쓸 수 있다(주문 단위 판정).
- 이력 재료와 시각 기준(모두 naive = UTC, `format_datetime_kst` 로 바꿈 — 협력사 원문 사본만 KST aware):
  - 주문 보냄: `partner_intake.submitted_at` · `submitted_by_name`. 품목 고침: `partner_intake.item_edits`(`at` · `by_name`).
  - 도면: `drawing_transfer_history` — `TRANSFER`(올림, 파일 수), `CANCEL_TRANSFER`(올림 취소), `REQUEST_REVISION`(수정 요청 — 협력사가 보낸 것은 `by_user_name` 이 "(협력사)"로 끝남), `CONFIRM_RECEIPT`(도면 확정 = 협력사 확인 차례). 회차 = 그 올림 앞의 수정 요청 수 + 1(`drawing_round_info` 와 같은 규칙).
  - 승인: `blueprint.confirmed_at` · `confirmed_by`(협력사 승인 때 "이름 (협력사)").
  - 접수 확인 → 도면 작업: 단계 전이 이벤트(`STAGE_CHANGED` 등, 우리 타임라인 `_stage_reach_events` 규칙)의 DRAWING 첫 도달.
  - 시공일: `OrderEvent` `CONSTRUCTION_DATE_CHANGED`(`from` · `to`). 시공 끝: `CONSTRUCTION_COMPLETED`.
  - AS: `as_lifecycle.cycles[].transitions`(`AS_REGISTER` · `AS_SCHEDULE` · `AS_UNSCHEDULE` · `AS_COMPLETE` · `AS_REOPEN`). 대시보드 칸(`field_update` 의 `as_visit_date`)으로 정한 방문일은 이벤트가 없어 이력에 못 넣는다 — 지금 방문일은 "완공 사진 · AS" 탭 진행 상황에 보인다.

### 15.2 설계 (2026-10-20 사용자 승인: PDF 는 파일 줄로 · 우리 쪽 수정 요청 내용은 숨김)
- **도면 탭**: 최종 도면 중 그림 파일은 고객 공유 화면과 같은 갤러리(카드 · 눌러서 크게 · 넘기기 · 카드마다 저장), 그 밖(PDF · DWG 등)은 지금처럼 파일 줄(새 창 열기). 회차("N차 도면 · 올라온 날")를 제목 옆에. 갤러리 조각 · lightbox JS · CSS 는 우리 파일을 그대로 싣는다(바꾸지 않음).
- **이력 탭**(새 탭 "이력"): 새 서비스 `foms/services/partners/history.py` `partner_order_history(db, order)` — 협력사가 볼 줄만 고른 허용 목록 방식, 최근이 위. 줄 = 시각(KST) · 일 · 누가 · 내용.
  - 우리 직원 이름은 넣지 않는다 — "저희 도면팀" · "저희 담당자". 협력사 직원 이름은 넣는다(자기 회사).
  - 도면팀이 올릴 때 적은 메모, 우리 쪽이 낸 수정 요청 내용, 단계 바꾼 사유, 시공 메모, AS 비용 판정은 넣지 않는다. 협력사가 보낸 수정 요청은 내용까지 보인다.
- 새 API · DB 변경 없음(HTML 화면만). 이벤트는 그 주문 것만 한 번에 읽는다(N+1 없음).

### 15.3 검증
- 시험 `tests/security/test_partner_history.py`: 줄 종류별(보냄 · 고침 · 도면 작업 · N차 올림 · 수정 요청 · 확정 · 승인 · 시공일 정해짐/바뀜 · 시공 끝 · AS 접수/방문/끝), 우리 직원 이름 · 도면 메모 · 우리 쪽 수정 요청 내용 0개(대조군: 협력사 수정 요청 내용은 보임), 다른 회사 주문 404, 시각 KST.
- 도면 탭: 그림 도면은 갤러리 카드, PDF 는 파일 줄(대조군), 회차 표시.
- 스테이징: CLAUDE-TEST 협력사로 PC · 휴대폰 실화면(그림 확대 · 넘기기, 이력 탭).

### 15.4 구현 기록 (2026-10-20)
- 서비스 `foms/services/partners/history.py` `partner_order_history`: 줄 = `{at, kind, title, who, detail}`(시험이 키를 고정). 이름은 이 주문 협력사 직원(`User.partner_org_id`)만 내고 나머지는 "저희 담당자" · "저희 도면팀". 수정 요청 내용은 협력사 직원이 보낸 것만. 단계 전이는 우리 타임라인 규칙(`_stage_reach_events`)의 DRAWING 첫 도달만 쓴다. 올림 취소는 이력에서 TRANSFER 를 빼는 방식이라 따로 줄이 없다.
- 화면: 도면 탭(`templates/partner/partials/order_drawing.html`)에 회차 · 그림 갤러리(우리 조각 `drawing_mobile_v2_gallery.html` share_mode, `lightbox.js` 는 그림이 있을 때만) · 파일 줄. 이력 탭(`order_history.html`). 저장 단추 CSS 는 공유 화면 규칙을 `.pp-drawing-gallery` 안으로 옮겼다(우리 파일 무변경). 휴대폰에서는 "(시공 뒤)" 안내를 빼고 탭 여백을 줄여 탭 4개가 한 줄에 보이게 했고(스테이징 390px 에서 "이력" 탭이 화면 밖에 숨던 것), 도면 카드는 한 줄 한 장.
- 스테이징 실화면(2026-10-20, CLAUDE-TEST 협력사 · 시험 주문 #4782): 우리 쪽에서 그림 2장 + PDF 1개를 1차로 전달하고 수령 확정 → 협력사 도면 탭에 그림 카드 2장(눌러서 크게 · 다음 그림) · PDF 파일 줄 · "1차 · 10-20 13:37 올라옴", 협력사 수정 요청 뒤 이력 5줄(보냄 · 1차 · 도면 작업 · 확정 · 수정 요청 내용). 화면 원문에 도면 메모 · 도면 담당자 이름 · 단계 사유 0건.
- 시험 `tests/security/test_partner_history.py` 4건.


## 16. 4단계 휴대폰 화면 설계 (2026-10-20)

### 16.1 사실
- 우리 휴대폰 틀은 CSS 만으로 모양이 난다. 켜지는 조건 셋: 화면 폭 992px 미만(또는 세운 터치 태블릿), 조상에 `.erp-mobile-shell[data-erp-mobile-v2='true']`, `body.erp-mobile-v2-layout`. 아니면 `.erp-mobile-shell-chrome{display:none}`(`erp-pro/10-erp-mobile-v2-shell.css:28 · 49 · 364`).
- CSS: `erp-pro.css`(이미 실음, 머리 · 아래 탭 기본) + `foms-mobile-surfaces.css?v=20261015d`(우리 `layout_head.html:241`, `foms-shell` · `foms-bottom-nav` · `foms-queue-card-v2` · `foms-detail-hero` · `foms-form-field` · `foms-chip-strip` 등을 가져옴). 협력사 화면은 아직 두 번째 것을 싣지 않는다.
- 부품(클래스): 위 줄 `header.erp-mobile-shell-header.foms-shell-header` · 뒤로 `.erp-mobile-shell-header__home` · 제목 `.erp-mobile-shell-header__title` · 알림 `.erp-mobile-shell-header__notify`. 아래 탭 `nav.erp-mobile-bottom-nav > a.erp-mobile-bottom-nav__item(.is-active)` · 배지 `.erp-mobile-bottom-nav__badge`. 큐 카드 `article.queue-card.foms-queue-card-v2`(단계 칩 `foms-stage-badge--<단계>` · 제목 · `dl` 칸 · 아래 단추). 상세 `foms-detail-hero` · `foms-detail-section`. 아래 고정 줄 `foms-sticky-action-bar.erp-mobile-sticky-action-bar`. 아래 시트 `foms-reason-sheet`(CSS 조건 없음, 여닫기는 JS).
- 우리 메뉴 서랍 · 뒤로 단추 JS(`erp-mobile-shell.js`)는 Bootstrap JS · 내부 화면 전제라 싣지 않는다.

### 16.2 설계 — 우리 부품 클래스 + 협력사 파일(§5-8 그대로), 셋으로 나눈다
- **4-1 바깥 틀**: 휴대폰에서 지금 머리줄 · 메뉴 줄 대신 우리 위 줄 + 아래 탭.
  - 위 줄: 목록은 회사 이름, 주문 · 새 주문 화면은 뒤로 단추 + 제목. 오른쪽 알림(지금 "알림 받기" 칸을 연다).
  - 아래 탭 5개(§3.1): 주문 · 도면 확인(내 차례 수 배지) · 새 주문 · 완공·AS · 더보기. 더보기 = 아래 시트(이름 · 회사 · 알림 받기 · 관리자로 돌아가기 · 로그아웃).
  - PC(992px 이상)는 지금 머리줄 · 메뉴 줄 그대로.
- **4-2 목록**: 휴대폰 카드를 우리 큐 카드 마크업으로(단계 칩 · 고객 · 주소 · 제품 · 시공일 · 담당 · "열기"/"도면 확인하기" 단추) + 진행 막대(협력사 추가). "지금 내 차례" 묶음 · 검색 · 단계 칩(우리 칩 줄).
- **4-3 주문 화면**: 휴대폰에서 우리 상세 모양 — 위 카드(단계 칩 · 고객 · 제품), 탭 4개(주문 · 도면 · 완공 · 이력)는 칩 줄, 칸은 구역 카드, 단계 버튼은 아래 탭 바로 위 고정 줄. 완공 사진을 고르면 AS 접수 칸이 아래 시트로 뜬다(§3.6).
- 데이터 · API · 권한은 바꾸지 않는다(화면만). 우리 직원 화면 파일은 바꾸지 않는다.

### 16.3 검증
- 시험: 협력사 화면 원문에 위 줄 · 아래 탭 5개 · 활성 탭 · 배지, 우리 직원 화면 대조군(바뀌지 않음), 기초 CSS 핀이 `layout_head` 와 같음.
- 스테이징 실화면: 휴대폰 390px(목록 · 주문 · 도면 · 이력 · 완공 · 새 주문, 가로 넘침 0) · PC 1440px(지금과 같음).

### 16.4 구현 기록 (2026-10-20)
- 4-1 바깥 틀: `templates/partner/layout.html` 이 `body.erp-mobile-v2-layout` + `.erp-mobile-shell[data-erp-mobile-v2]` 안에 우리 위 줄(`erp-mobile-shell-header`) · 아래 탭(`erp-mobile-bottom-nav`)을 그린다. PC 머리줄 · 메뉴 줄은 `foms-shell-desktop-only`(우리 규칙이 휴대폰에서만 숨김). 알림 판은 공용 조각 `partials/push_panel.html`(PC · 휴대폰 하나씩, `partner-push.js` 가 칸마다 묶음). 더보기는 우리 아래 시트 모양(`foms-reason-sheet`), 여닫기 `static/js/partner/partner-shell.js`. 알림 켜기는 더보기가 아니라 위 줄 종 단추에 두었다(같은 판을 두 번 두지 않으려고).
- 우리 휴대폰 틀은 직원 화면에서도 프로세스 맵(`erp-pro-card--process-map`)을 휴대폰에서 숨긴다(`foms-shell.css:190`) — 그래서 4-1 만으로는 휴대폰 목록의 검색 · 단계 거르기가 빠졌고, 4-2 에서 우리 검색 줄 · 칩 줄로 되살렸다.
- 4-2 목록: `templates/partner/home.html` 에 휴대폰 전용 `.foms-shell-body.pp-mlist` — 검색 줄(`erp-mobile-queue-filters`) · 칩 줄(전체 · 단계 7칸 · 내 담당, 도면 확인 대기는 노란 칩) · 우리 큐 카드(`foms-queue-card-v2`, 단계 칩 색 `foms-stage-badge--<단계>`, 지금 · 주소 · 제품 · 연락처(전화 링크) · 시공일 · 담당, "도면 확인하기"/"열기") + 진행 막대. 3-2 의 옛 카드 목록(`pp-cards`)과 CSS 는 걷었다.
- 4-3 주문 화면: 휴대폰에서 카드 머리 · 탭 대신 우리 상세 위 카드(`foms-detail-hero`: 단계 칩 · 내 차례 · 고객 · 제품 · 시공일)와 칩 줄 탭(`foms-chip`, 위 줄 아래 고정). 단계 칩 색은 공용 조각 `partials/stage_badge.html`(목록과 같이 씀). 완공 사진이 있고 AS 를 접수할 수 있으면, AS 칸은 PC 에서 사진 아래 펼친 칸 · 휴대폰에서 사진을 고르면 올라오는 아래 시트(같은 form 안이라 고른 사진과 함께 보낸다, `is-open` · 고른 장수 표시, `partner-shell.js`). 아래 고정 줄 "AS 접수"도 그 시트를 연다.
- 시험 `tests/security/test_partner_mobile_shell.py` 6건(위 줄 · 아래 탭 5개 · 활성 탭 · 뒤로 · 배지 · CSS 핀, 휴대폰 목록 카드 · 칩 · 내 차례 묶음 · 다른 회사 제외, 주문 화면 위 카드 · 칩 탭 · AS 시트).

## 17. 5단계 새 주문 화면 설계 (2026-10-20 사용자 승인: 셋 다 5-1 부터 · 주소 찾기는 우리 PC 와 같은 창 · ▾ 목록은 제품명만)

### 17.1 사실
- 지금 협력사 새 주문(`templates/partner/new_order.html`)은 단독 form(`pp-fieldset` 넷)이다. 제품 카드는 주문 화면과 같은 매크로(`partials/item_card.html` `pp_item`)지만, 왼쪽 목록 · 오른쪽 상세 틀은 주문 화면(`partials/order_items.html`)에만 있다.
- 보내기 순서: 주문 만들기(`POST /api/partner/orders`) → 사진 올리기(`POST …/files`, `item_index`). 주문이 생겨야 올릴 곳이 생기므로, 새 주문 화면의 사진은 보내기 전까지 브라우저에만 있다(`partner-portal.js` `bindNewOrder`).
- 우리 새 주문(`/add`, `orders/add_order.html:372`)은 주문 화면과 같은 `orders/partials/erp_order_tab.html` 을 쓴다(목록 · 상세 `:389-410`). 우리 휴대폰 새 주문은 마법사(`orders/wizard/wizard_shell.html`)라 모양이 따로다.
- 제품명 목록: 우리 입력 칸 옆 ▾ 단추(`static/js/orders/erp-spec-calc.js:160-184`)가 `ErpSpecPicker.openSingle` 을 연다(`static/js/orders/erp-spec-picker.js` — PC 는 펼침 목록, 휴대폰은 아래 시트. 다른 JS 에 기대지 않는 모듈). 목록 출처 `GET /api/wdcalculator/products` 는 값에 단가가 들어 있고 협력사 허용 목록 밖이다. 우리 화면은 발주사가 라홈인 주문에서만 켠다.
- 품목 사진: 우리 칸은 `[data-erp-attachment-paste-zone="item"]` · "즉시 추가" · Ctrl+V(`erp-order-shared.js:1780-1797 · 5078-5093`). 끌어놓기는 우리 화면에도 없다. 우리 쪽은 주문이 이미 있어 바로 올린다.
- 공통 사진 연결 · 해제: 우리 `PATCH /api/orders/<id>/attachments/<aid>` `{item_index}`(`foms/api/files/order_routes.py:498`) — 공통 카드의 "제품 연결" 고르기, 품목 사진의 "공통으로 이동" 단추. 협력사 쪽 API 는 아직 없다(§4-5).
- 주소 찾기: 우리 PC 는 서버의 카카오 주소 검색 `GET /api/address/search`(`foms/api/address.py:96`, 로그인만 확인 · 주문 데이터 없음) + 검색 창(`erp_order_tab.html:599-628`, Bootstrap 모달). 협력사 허용 목록에 없다. 휴대폰 마법사는 다음 우편번호 창(`wizard_shell.html:92`).
- 전체 항목 요약은 우리도 `window.alert`(`static/js/orders/erp-items-master-detail.js:267`).

### 17.2 설계 — 우리 부품 클래스 + 협력사 파일(§5-8 그대로), 셋으로 나눈다
- **5-1 화면 틀**: 우리 새 주문 모양 — "주문 정보" 카드(고객명 · 연락처 · 주소 + 찾기 · 실측일 · 메모, 우리 `erp_order_tab` 칸 순서) → 제품 항목 왼쪽 목록 · 오른쪽 상세(주문 화면 조각을 새 주문에도 씀) → 공통 첨부 → 아래 고정 줄 "보내기"(휴대폰은 아래 탭 위).
  - 제품명 ▾ 목록: 우리 제품 목록의 **이름만** 화면에 싣는다(단가 등 다른 값은 싣지 않음, 새 라우트 없음). 고르기는 우리 `erp-spec-picker.js` 를 그대로 싣고, 직접 입력은 지금처럼 된다.
  - 주소 찾기: 우리 PC 와 같은 검색 창(검색어 · 상세주소 · 결과 목록 · 입력)을 협력사 파일로 그리고, 우리 서버 카카오 검색(`address.search`)을 협력사 허용 목록에 하나 더한다. 고르면 "도로명 주소 + 상세주소"가 주소 칸에 들어간다. 꼭 넣을 칸은 지금과 같다(고객명 · 연락처 · 주소 · 품목 1개).
- **5-2 사진**: 품목 사진 칸을 우리 모양으로 — "즉시 추가" · Ctrl+V · 끌어놓기(PC), "찍기" · "앨범"(휴대폰). 고른 사진은 미리보기 · 빼기. 공통 첨부(실측 사진 · 초안 도면)도 같은 칸이고, 공통 사진마다 "제품 연결" 고르기, 품목 사진마다 "공통으로" 단추. 보내기 때 지금처럼 주문 → 사진 순서로 올린다(서버 변경 없음).
- **5-3 접수 확인 중 주문 화면 사진**: 주문 화면(접수 확인 중)에도 같은 사진 칸. 이미 올린 사진의 연결 · 해제는 새 API `PATCH /api/partner/orders/<id>/attachments/<aid>` `{item_index}` — 접수 확인 중만(밖이면 409), 다른 회사 404, 협력사가 올린 실측 사진만(아니면 400), 품목 범위 안만, `item_id` 같이 고침, 첨부 변경 기록(`ATTACHMENT_META_UPDATED`)은 우리와 같이 남김. 허용 목록 · 쓰기 목록 · "다른 회사 거부" 시험 1:1(§4-8).
- 우리 직원 화면 파일은 바꾸지 않는다. 직원 쪽 제품 목록 · 주소 검색 라우트도 바꾸지 않는다.

### 17.3 검증
- 시험: 새 주문 화면 원문에 목록 · 상세 틀 · ▾ 단추 · 주소 찾기 창, 실린 제품 목록에 이름만(단가 키 0개), 등록 필수 칸 그대로. 협력사가 주소 검색은 되고 우리 다른 API(제품 단가 목록 등)는 여전히 막힘(대조군). 5-3 API: 다른 회사 404 · 도면 단계 409 · 다른 주문 사진 · 우리 직원 파일 · 실측 사진 아님 · 범위 밖 400, 연결 뒤 `item_index` · `item_id`.
- 스테이징 실화면: PC 1440px 등록(목록 고르기 · 직접 입력 · W*D*H 붙여넣기 · 주소 찾기 · Ctrl+V · 끌어놓기 · 공통 사진 연결) → 주문 화면에 품목 사진 자리가 맞음. 휴대폰 390px(찍기 · 앨범 · 아래 시트 목록 · 가로 넘침 0).

### 17.4 구현 기록 (2026-10-21)
- 5-1 화면 틀: `templates/partner/new_order.html` 을 우리 새 주문 모양(주문 정보 카드 → 제품 항목 왼쪽 목록 · 오른쪽 상세 → 공통 첨부 → 메모 → 아래 고정 줄 "보내기")으로 바꿨다. 목록 · 상세 틀은 공용 조각 `partials/items_rail.html`(주문 화면 `order_items.html` 도 같이 씀). 옛 새 주문 전용 CSS(`pp-fieldset` · `pp-items` · `pp-title`)는 걷었다.
- 제품명 ▾: `foms/web/partner` `_product_names()` 가 `load_products()` 에서 이름만(앞뒤 공백 · 빈 이름 · 겹친 이름 뺌, 500개까지) 골라 `[data-pp-product-names]` 에 싣는다. 고르기는 우리 `erp-spec-picker.js`(PC 펼침 목록 · 휴대폰 아래 시트), 묶기는 새 `static/js/partner/partner-order-entry.js`. 접수 확인 중 주문 화면에도 붙는다(그 밖 단계는 싣지 않음).
- 주소 찾기: `partials/address_modal.html`(우리 PC 검색 창과 같은 칸, `hidden` 으로 여닫기 — `partner-shell.js`). 협력사 허용 목록에 `address.search` 하나를 더했다.
- 스테이징에서 찾아 고친 것: 휴대폰은 왼쪽 목록이 숨어 '+ 항목' 단추도 숨었다 → 카드 아래 '제품 항목 더하기'(넓은 화면에서는 숨김). 접수 확인 중 주문 화면에도 같은 구멍이 있었다.
- 시험 `tests/security/test_partner_new_order.py` 6건(틀 · ▾ · 주소 창 · 더하기 단추 둘, 제품 목록은 이름만 · 단가 0개, 목록이 비면 ▾ 없음, 주문 화면은 접수 확인 중만, 협력사 주소 검색 됨 · 우리 제품 단가 · 프리셋 API 403 대조군, 직원 주소 검색 그대로).
- 스테이징 실화면(2026-10-21, CLAUDE-TEST 협력사): PC 1440px — ▾ 목록 27개에서 "신발장" 고름 → 칸 · 왼쪽 목록 반영, 주소 찾기 "송파대로 345" 10건 → 고르고 상세주소 → 주소 칸에 "… 헬리오시티 101동 1001호", 항목 둘(목록 고른 것 · 직접 입력, 복합 폭 `5700(2402+1864+1434)`)로 보내기 → 시험 주문 #4786 에 그대로. 휴대폰 390px — 아래 시트 목록 · 주소 창(Enter 검색) · 더하기 단추, 가로 넘침 0, 보내기 줄은 아래 탭 바로 위.
