# 태블릿 생산 UI 설계 세션 — 원장 (2026-11-09)

지시서: `docs/plans/2026-11-09-tablet-production-ui-meta-prompt.md`. 이 원장은 그 §7 의 원장이다.

## 0. 시작 상태

- 시작 HEAD: origin/deploy `ea4376ea1` (메인 체크아웃 `C:/DEV/FOMS` 와 같음, ahead/behind 0/0, 2026-11-09 측정).
- 워크트리: `c:/tmp/foms-s-tablet-prod-ui`, 브랜치 `session/tablet-prod-ui`(base origin/deploy). 세션 워크트리 14개 활성(권장 3) — 정리는 이 세션 범위 밖.
- 로컬 환경: PostgreSQL 5432 떠 있음(`furniture_orders`), 포트 5000~5010 비어 있음, `.env` 에 `ERP_MOBILE_V2_ENABLED`·`FOMS_V3_SHELL_COHORT`·`DATABASE_URL` 없음, Playwright 설치됨.
- 총괄 모델: Fable 5.1(이 세션). effort 는 하네스 설정값(`/effort status` 는 세션 안에서 못 부름 — 사용자가 확인).

## 1. 사용자 결정 (질문 창 답, 2026-11-09)

- **D0** 진행 방식: 새 세션이 아니라 **이 세션에서 바로 시작**(메타프롬프트 §0.1 복붙 대신).
- **D1 (Q1) 기종**: **갤럭시 탭**. 가로 약 1280×800 CSS px 기준. 세로로 돌리면 폰 화면(992 미만).
- **D2 (Q2) 사람·계정**: **사람마다 계정, 사람마다 태블릿**. "사람마다 [확인]"(생산 변경 알림) 구조 그대로 쓸 수 있다.
- **D3 (Q3) 볼 범위**: "생산, 출고, 시공 일정도 봐야 되고, 고객이름, 주소, 전화번호 등 다 볼 수 있어야 돼" → 레일을 생산만으로 좁히지 않는다. 생산·출고·시공(일정 읽기)은 필수, 고객 이름·주소·전화는 **가리지 않는다**. 금액은 지시 없음 → 지금 그대로(설계서에서 "그대로 둠"으로 명시). 실측·AS·완료·이력·계산기 탭을 뺄지는 설계서 제안으로 남기고 사용자 승인 때 묻는다.
- **D4 (Q4) 지금 방식**: 구두·전화 + 카톡 발주방 글(PUSH) + 종이 출력(작업지시서·도면). **태블릿에서 인쇄도 필요할 수 있다** → 목업 후보에 F8 "작업지시서·도면 인쇄" 추가(브라우저 인쇄 CSS 재사용 여부는 코드로 확인).
- **D5 (Q5) 공장 환경**: 장갑 끼고 쓴다 · 와이파이 안정 · **가끔 연결이 얼어요** → 터치 타깃을 48px 아래로 내리지 않고 확인 창을 줄인다. 연결이 얼었을 때 "마지막 화면 유지 + 다시 연결되면 보냄"은 설계서에 범위 판단(오프라인 저장은 큰 일 — 최소안: 실패 시 재시도 안내·입력 보존).
- **D6 (Q6) 다른 사용자**: "생산만 · 시공팀·CS·영업 · 출고팀 · 도면팀" 전부 선택 → 모든 팀이 태블릿을 쓸 수 있다고 읽는다. 목업 1순위는 생산, 다른 팀 태블릿 표면은 **전수 점검(결함 목록)에 넣되** 목업은 2차(플랜 뒷 단계). "생산만"이 함께 선택된 점은 승인 때 한 줄로 되묻는다.

## 2. 재측정 (사실 카드 §2 와 다른 값만)

- 지시서 §2.3 "태블릿 CSS 체인 `foms-tablet-bundle.css` ← `foms-mobile-surfaces.css`" 는 옛 구조 — 지금은 `layout_head.html:271` 이 `foms-tablet-bundle.css?v=20261109a` 를 따로 싣고 surfaces 에는 태블릿 레이어가 없다(워커 B, 시험 `test_tablet_t2_contract.py:109-110` 고정).
- 지시서 §2.3 "시트 [보류] 꺼져 있음" → 틀림(H3 뒤집힘). 시트 머리 주석이 낡았을 뿐.
- 지시서 H9 전제 "90vh" → 태블릿 CSS 에 없음. 미보정은 변경 모달 목록 `60vh` 하나(실화면 130% 에서 확인).
- 워커 C 로컬 "생산 단계 0건" vs 총괄 측정 `erp_stage_code='PRODUCTION'` 5건(2건 DELETED·3건 items 0) — 열이 다름. 로컬 DB 는 어차피 QA 에 못 쓴다(도면 0·품목 0). 실화면은 스테이징으로 했다.
- 스테이징 코호트: 이날 만든 생산팀 계정이 바로 태블릿 표면(레일·칸반·마커 ready)을 받음 → 스테이징 `FOMS_V3_SHELL_COHORT` 는 전체. 운영 값은 미확인.
- **측정 함정 2개(다음 세션용)**: ① Playwright `full_page=True` 캡처는 문서 높이가 폭을 넘는 순간 `orientation: portrait` 가 되어 태블릿 규칙이 풀린다(출고 화면이 PC 크롬으로 찍혔다) — 뷰포트 캡처만 판정에 쓴다. ② 가로 생산 보드 DOM 에는 숨은 레거시 `#erp-grid` 행이 칸반보다 앞에 있어, `#erp-grid tr, .foms-kanban-card` 같은 합친 셀렉터로 "첫 카드"를 고르면 숨은 행을 눌러 기본 fragment 403 이 난다(1024 대조군의 403 은 이 탓, 결함 아님).
- 지시서 줄 번호 정정(리뷰 ③): 계정 팀 목록 "생산팀" `auth/routes.py:85`(TEAMS :81-91) · `foms_scr` 기준 `feature_flags.py:177`, `foms_vw` 판정 `:229-271` · `build_split_side_items` 는 `foms_split_view.py:129` · 도면 TRANSFERRED 막힘 `orders.py:807-828`(제작 시작)·`:1055-1060`(수정 제작) · 시트 뷰 `dashboard.py:408-468`, 썸네일 `:383-405`.
- 워커 D 는 띄우지 않았다 — 하네스(`scratchpad/tablet_shot.py`)를 총괄이 만들고 5모드 사전 스윕 + 보강 2회를 직접 돌렸다(비용·자격증명 노출 둘 다 줄임). 판정은 총괄이 PNG 를 직접 봤다.

## 3. 워커 보고 (원문 그대로 붙임)

### 3.A 권한·라우트
보고 원문: `2026-11-09-tablet-production-ui-worker-A.md`(Fable 5.1 high, 65 도구 호출, 10.5분). 핵심: 생산팀은 `can_edit_erp` 밖 → 컨트롤타워 시트(자체 라우트)·AS 표 행(기본 fragment) 403, `/edit/<id>` 는 302 `/`+flash, 이력 시트는 200. 출고 배정 API 는 CS/SALES 데코레이터라 생산팀·출고팀 STAFF 모두 403(부수 발견). 모바일 하단 탭에 '생산' 없음. 로그인 착지는 `Sec-CH-UA-Mobile` 판정 → 태블릿은 `/` 레거시 목록일 가능성(추정).

### 3.B 태블릿 표면·게이트·기능표
보고 원문: `2026-11-09-tablet-production-ui-worker-B.md`(Fable 5.1 high, 63 도구 호출, 13.1분). 핵심: 태블릿 가로에서 생산팀이 못 하는 일 = 공정 5단계 체크·불량 보고(모바일 바텀시트 전용) · 도면 여러 장 보기(시트는 첫 1장) · 고객 연락처·주소(카드·시트 모두 없음 — 사용자 D3 와 충돌) · 서버 필터·정렬·내 것 토글 · 제작 취소·완료 취소는 시트에서만 · 출고 배정 없음. 역방향 격차: 보류 토글·변경 확인·묘비·KPI 탭·전체화면은 태블릿에만. 태블릿 CSS 체인은 `foms-tablet-bundle.css`(surfaces 아님). JS 래칫은 .js 300줄 + 기준선 목록, `tablet-production-kanban.js` 남은 줄 109. 공정 체크 시트는 include + 버튼 1개로 가로에서도 동작(JS 전역 로드).

### 3.C 단계 흐름·알림
보고 원문: `2026-11-09-tablet-production-ui-worker-C.md`(Fable 5.1 high, 68 도구 호출, 11.7분). 핵심: 생산 접점은 고객컨펌·생산·시공 3단계 + AUTO_PRODUCTION_D2 할 일. 출고 겹축·출고 2주 판은 생산 화면에 안 보임. AS → 재제작 경로 없음(시공 불가 `product_defect` 와 [수정 제작]만). 품목 일부 취소는 알림이 안 감. 도면 바로 반영은 합치기 없이 매번 폰 push. 발주 PUSH 는 채널톡 방이라 FOMS 알림 밖. 상차일 = 시공일 같은 키.

### 3.D 실화면 수집(총괄 직접)
- 하네스 `scratchpad/tablet_shot.py`(모드 tablet 1280×800 · tablet_s 1024×768 · portrait 800×1280 · pc · pc80, `--zoom` 으로 배율 흉내), 로그인 상태 `state_prod.json`(생산팀 STAFF `claude_test_prod`, 스테이징에서 이날 생성)·`state_master.json`(claude_master).
- 스윕: 모집단 31 경로 × tablet·portrait, 대조군 7 경로 × tablet_s·pc·master, 보강 14+5+3 장(뷰포트 캡처). 결과 표·PNG 는 `scratchpad/shots/*/results.jsonl`·`*.png`.
- 판정 전수표: `2026-11-09-tablet-production-ui-inventory.md`(화면 24 × 잣대 6 = 144 칸, 대조군 4). 결함 F-01~F-20.

## 4. 가설 판정 (H1~H12)

| # | 판정 | 근거 |
|---|---|---|
| H1 | **확인됨(실화면)** — 기전은 조건부 | 컨트롤타워 시트는 자체 라우트지만 `can_edit_erp` 검사로 403(`foms/web/orders/dashboard.py:653-654`), AS 표 행만 기본 fragment 403(`fragment.py:72`), 이력 시트 200. 403 때 시트 문구 "내용을 불러오지 못했습니다"(권한 안내 없음) |
| H2 | **확인됨(코드+실화면)** — 가로 시트 단추 = 보류·완료 취소·수정 제작/제작 시작뿐, 세로 바텀시트에만 공정 5체크 | `tablet_sheet.html`·`tablet-domain-sheets.js`·`tablet_kanban_body.html` 에 `production/steps`·`defect`·`data-foms-prod-steps-open` 없음. 시트 마크업은 `mobile_queue.html:113` 에만. JS `foms-production-steps.js` 는 `dashboard_body.html:161` 전역 로드 → include + 버튼이면 동작 |
| H3 | 뒤집힘(코드, 워커 A) | `tablet_sheet.html:176-182` [보류] 에 disabled 없음, `tablet-domain-sheets.js:204-245` 가 hold API 호출. 머리 주석 ":6 보류 disabled" 가 낡음 |
| H4 | 확인됨(코드) · 실화면 일부 | 시트 `drawing_thumb` 는 첫 1장(`dashboard.py:383-407`), 칸반엔 도면 열기 없음, 바뀐 도면 구분 없음. 스테이징 도면 파일이 깨져(4103 썸네일 로드 실패, 4082 는 전달본 0·첨부 2) 뷰어 실동작은 못 봄 → 운영 재확인 |
| H5 | 확인됨(실화면) | 800×1280 에서 레일 숨김·칸반 숨김·모바일 큐 카드. 하단 탭에 '생산' 없음(F-07) |
| H6 | 해소(사용자 D2) | 사람마다 계정·태블릿 → "사람마다 확인" 구조 그대로. 운영 생산팀 계정은 사용자가 만든다 |
| H7 | 확인됨(실화면) | 출고 태블릿 판·시트 읽기 200, 배정 쓰기 403. 생산 카드엔 출고 배정 상태 없음(워커 C) |
| H8 | 사용자 D3 로 좁히지 않음 | 생산·출고·시공 필수. 실측·AS·완료·이력·계산기 빼기는 승인 때 질문(F-18) |
| H9 | **확인됨(실화면 130%)** — 전제 90vh 는 틀림 | 90vh 전제는 틀림(시트는 top/bottom 고정). 칸반 열·전체화면·변경 모달은 `/zoom` 보정됨(시험 고정). 미보정: 변경 모달 목록 `max-height: 60vh`(`foms-tablet-production-kanban.css:926`) → 130% 잘림 가능(추정). 배율 손잡이가 가로 레일 모드에서 둘 다 숨어 **가로에서는 배율을 못 바꿈**(추정) |
| H10 | 조건부(코드, 워커 B) | PC 에만 있는 것: 서버 필터(단계·팀·긴급·경보·검색 UI)·정렬·고객 연락처·주소 열·첨부 모달 여러 장. "일괄 선택·관리자 되돌림"은 PC 에도 없음(함수만). 역방향 격차(태블릿에만): 보류 토글·변경 확인·묘비·KPI 탭·전체화면 |
| H11 | 확인됨(코드, 워커 A·C 일치) | 시트 규격 표·총 자수·카드 자수·KPI 이번 주 자수 모두 `active_items`(`dashboard.py:199,317,427,447`) → `drop_cancelled`. 원본 세는 곳은 "취소 품목 N개" 배지만(의도) |
| H12 | 확인됨(코드, 워커 C) | 카드 빨간 표시는 요청자 본인의 `PRODUCTION_CHANGE_ACK` 만 봄(`production_change_alerts.py:121-130`), 벨은 [확인]과 무관(본인 read 만). 사람마다 계정(D2)이면 설계 그대로 맞음 |

## 5. 리뷰 finding (전량, 받는 즉시)

- 리뷰어 ② 단순화: 원문 `2026-11-09-tablet-production-ui-review-2.md`(Fable 5.1 high, 15 도구 호출, 7.2분). 요지: 바뀐 칸 18개 중 남김 6(F1 ③·F2 ①·F2 ③·F6 ①·F7 ①·D5 문구), 줄임 5(F2 ④·F2 ⑤·F7 ②·F-13·시험/CSS 재사용), 지움·미룸 7(F1 ①·F1 ②·F2 ②·F3 새 JS·F6 ②·F7 ③·F8·T5-3). 새로 만드는 것 10개 중 남는 것 = 60vh 보정 1개(+인쇄는 미룸). 플랜 17 → 8 task, P1~P3. 질문 5개 모두 설계자가 정해도 됨.
- 리뷰어 ① 반증: 원문 `2026-11-09-tablet-production-ui-review-1.md`(Fable 5.1 high, 79 도구 호출, 10.2분). 깨짐 7(F2 ③ 공정 JS 는 document 전역 6곳이라 "1곳 일반화" 불성립 · 가로 DOM 에 세로 오프캔버스가 먼저 있어 id·data 중복 · 카드 "공정 n/5" 단추는 세로 시트를 연다 · 착지는 `listing.py:158`·`post_auth_navigation.py:100-101` 두 곳이 직접 dashboard · 읽기 전용 시트에 승인 단추 잔존 · F-13 호출 지점 `:46` 은 해시 헬퍼, 60초 합치기가 품목 2개를 덮어씀 · §9 쿼리 수 시험은 대시보드만), 조건부 9, 버팀 18. 전수표 #19 ② 는 △(모바일 상세는 취소 품목을 라벨 붙여 보여 줌).
- 리뷰어 ③ 사실 검증: 원문 `2026-11-09-tablet-production-ui-review-3.md`(Fable 5.1 high, 44 도구 호출, 10.7분). 틀림 14(착지 3곳·공정 시트 줄 `:15-35`·JS 경로 `static/js/production/`·F-13 호출 지점·시험 3개 역할 오귀속·카드 스트립 위치 `:184-197`·시트 단추 목록에 [제작 취소]·지시서 줄 번호 3), 모호 13(줄 번호 어긋남·confirm 수·터치 계약 44/48·시공팀 키 `shipment.construction_workers`). 설계서 §3·§5~§9 나머지 경로·숫자(JS 줄 수·래칫·상한 300·공정 5·불량 4)는 맞음.

### 6.3 리뷰어 ③ 반영
- 틀림 14 중 반영판(6.1·6.2)에서 이미 고친 4(착지 3곳·JS 경로·F-13 지점·읽기 전용 시트→문구) 빼고 나머지 전부 설계서·플랜에 파이썬 치환으로 반영(설계서 18/18·플랜 8/8 치환 성공). 지시서 줄 번호 3건은 §2 재측정에 추가: `auth/routes.py:85`(TEAMS :81-91), `feature_flags.py:177`(`WIDE_SURFACE_MIN_PX`)·`:229-271`(`wants_mobile_width_surfaces`), `foms_split_view.py:129`(`build_split_side_items`), `orders.py:807-828`·`:1055-1060`(TRANSFERRED 막힘).

## 6. 총괄 재확인·반영

### 6.1 리뷰어 ② 재확인(코드로 직접)
- `templates/partials/shared/foms_ui_zoom_control.html` 있음(변형 bar/drawer, `data-foms-ui-zoom-ctl`), `ui-zoom.js:43` 은 로드 때 `querySelectorAll('[data-foms-ui-zoom-ctl]')` — 레일은 레이아웃 소유(로드 때 있음)라 include 가 먹음 → **F1 ① 은 "지움" 대신 "include 1줄 + 레일 변형 CSS 몇 줄"로 줄임**(사용자 D5 장갑·세로로 돌려 정하라는 건 공장에서 번거로움, 가로 손잡이는 남긴다 — 총괄 판단).
- `static/js/foms/erp-attachment-preview-open.js:147,163-167` `galleryFilesFromNodes` → `GlobalImageViewer.open(files, idx)` 확인, 로드 지점 `foms_mobile_queue_attachment_preview_bundle.html:4`(모바일 큐 번들) → 생산 페이지에 이미 실리는지 T3-1 에서 확인. 뷰어 counter "n / N" `layout-scripts-core.js:262-264` 확인 → **F3 새 JS 지움, F2 ④ 글 두 개 지움 수용**.
- `fragment-loader.js:92-100` renderError 는 status 를 모름(`:124` throw) → "문구만"도 status 전달 1줄 필요. **F7 ② 는 읽기 전용 렌더 대신 403 문구로 줄임**(Q-D 삭제).
- `tablet_sheet.html:6,9,169` "생산 완료" 확인 → 세로·설계서와 같은 "제작 완료"로 글 통일(계약 시험은 confirm 문구만 고정).
- `production_change.py:138` 기본 라벨 "주문 변경" 확인 → **F-13 은 호출 1줄로 줄임**(라벨 "주문 변경"이 생산 사람에게 충분한지는 실화면에서 한 번 더 본다).
### 6.2 리뷰어 ① 재확인(코드로 직접)
- `static/js/production/foms-production-steps.js:56,159,162,191-194` 전부 `document.querySelector`, `:18,275` 전역 `currentOrderId`, `:309` capture `stopImmediatePropagation` 확인 → **F2 ③ 은 "스코프 객체로 재작성"**(루트 `[data-foms-prod-steps-sheet]` 기준, id 제거, 시트 삽입 때 `loadSteps(id, root)`). 파일 경로도 설계서의 `static/js/foms/` 가 아니라 `static/js/production/` — 고침.
- `listing.py:158-159`·`post_auth_navigation.py:100-101` 직접 `url_for('erp_dashboard.erp_dashboard')` 확인 → **착지 분기는 세 곳**(+ `auth/routes.py:585` switch_user). PC 마우스도 생산 보드로(기기 무관, 총괄 결정).
- `production_change.py:148-156` merge 가 title/message 덧쓰기 확인 → **F-13 은 `merge=False` + 라벨 추가**, 삽입은 `_mutate` 안 `:78` 뒤(REV-99 인벤토리 lineno 주의).
- F7 ② 는 6.1 대로 "문구만"이라 승인 단추 잔존(R1 #8)은 해당 없음. 단 `Sec-Fetch-Dest: document` 302(R1 #10)는 생산팀이면 모바일 상세로.
- F1 ① 배율 단추 위치 = 레일 **브랜드 바로 아래**(130% 에서도 보임, R1 #17).
- **수용 안 함**: F2 ② "상차 → 시공" 이름 바꾸기 — 값은 같은 키지만 공장 말로는 상차가 맞을 수 있다(KPI 도 "오늘 상차"). 이름은 두고 "시공팀" 추가만 지운다. F8 인쇄 — 사용자 D4 "필요할 수 있어"라 **지우지 않고 승인 질문으로**(지금 할지·뒤로 미룰지). Q-A 금액 — 돈 노출은 사장님 몫이라 질문 유지. Q-B·Q-C·Q-E 는 리뷰어 판정대로 설계자가 정함(지금처럼·그대로·별건).

### 6.4 목업·발행
- 워커 E(Fable 5.1 xhigh, 71+21 도구 호출, 약 32분): `docs/design/mockups/tablet-production-ui.html`(1,294줄, 자급자족, 가짜 데이터, 한자 0, 실명 0, 1280/400 가로 스크롤 0). 리뷰 반영 수정 1회(레일 배율 단추 위로 · 카드 "공정 n/5" 삭제 · 시트 "시공팀"·"1/3"·"바뀐 도면" 삭제 · 링크 "상세" 하나 · F3 오버레이 삭제 · F6 QR 그대로 · F7 문구 · 질문 2개). 총괄이 프레임 6장을 1400 폭에서 직접 렌더해 확인.
- Artifact(비공개, 사용자만): https://claude.ai/artifact/1otSBdYuZ2PhD4ai4zRyor — 껍데기 벗긴 판 `scratchpad/tablet-production-ui.artifact.html`(저장소 판과 본문 동일).
- 스테이징 시험 계정 `claude_test_prod`(id 101) 비활성화 완료(11-09 12:26 생성 → 같은 날 비활성).

## 8. 사용자 승인·추가 결정 (2026-11-09 질문 창)
- **D7 (Q-A) 금액**: "생산팀에겐 가려요" → 완료 보드(PC·태블릿 그리드·모바일 카드·KPI 미수 합계)와 모바일 주문 상세의 품목 금액을 생산팀 계정에서 숨긴다(서버 분기, 값도 안 보냄). 플랜 T1-4 로 추가.
- **D8 (Q-F) 인쇄**: "이번에 같이" → F8 작업지시서 인쇄 포함, 시트 링크 "상세 · 인쇄". 플랜 P4 는 조건부 아님.
- **D9 진행**: "설계 승인, 구현 시작" → 이 워크트리에서 P1 부터 task 단위 구현·시험·커밋. 운영 반영은 따로 묻는다.


## 9. 작업자 시안 넷 (2026-11-09, 사용자 요청 "지금 구현된 태블릿 UI 말고 작업자 persona 로 목업 몇 가지 더")

- 파일 `docs/design/mockups/tablet-production-ui-alternatives.html`(612줄, 자급자족, 가짜 데이터). Artifact https://claude.ai/artifact/MD4PMbNiiKwF7mfuZLfuwk (비공개, Version 1). 색·글꼴·틀 축소 방식은 앞 시안과 같은 토큰.
- 안 1 **오늘 할 일**: 시공일 순 큰 카드 한 줄(118px×5), 공정 5칸을 카드 안에, 바뀐 주문은 붉은 띠 + 한 줄. 레일·KPI·칸반 없음. 데이터는 칸반 목록 + steps GET + 변경 알림.
- 안 2 **도면 먼저 작업 화면**: 전체 화면, 도면 6할(넘기기 72px·썸네일·PDF) + 고객(전화·주소·실측·출고)·만들 것·공정 5줄(누가 몇 시)·불량/보류·제작 완료(검수 전 회색)·위 막대 [인쇄]. 설계서 F2·F3 내용과 같고 배치만 다름. 시트 라우트 뷰 모델 2키 + 템플릿 1장.
- 안 3 **내 공정 줄**: 공정 5탭(사람마다 저장), 그 공정에 와 있는 줄 + 아직 앞 공정인 것 흐리게, 오른쪽 [엣지 끝] 96px·불량·보류·다음 사람. 단위는 공정마다 다름(재단·엣지 판 장수, 도장 면·색, 조립 장, 검수 품목). 판 장수는 ERP 에 없음.
- 안 4 **일정과 바뀐 것**: 요일 6칸에 출고·시공, 오른쪽 받은함(변경 4종 + 품목 취소) 사람마다 [확인했어요]. 브리핑 모달 대신 상시 받은함. 쓰기는 ACK 하나.
- 승인된 설계서와 관계: 설계서 = 기존 레일+시트를 생산팀이 쓸 수 있게, 넷 = 생산팀 전용 첫 화면. 함께 갈 수 있음(레일 생산 탭이 연다). 안 2 가 셋의 공통 바닥.
- 묻는 것: Q-G 공장 사람 유형(주문 단위 / 공정 단위 / 섞임) → 안 1 과 안 3 중 첫 화면 · Q-H 판 장수 데이터(도면팀 입력 / 품목 수로 시작) · Q-I 첫 화면 구성(한 장 / 할 일+이번 주 탭 둘 / 설계서대로만).
- 사용자 답(11-09, 질문 창): Q-G·Q-I → **"첫 화면은 전체 주문을 볼 수 있게"** = D10. Q-H → **"일의 양은 안 보여도 돼요"** = D11.
- 반영: 안 1 을 "전체 주문 — 시공일 순 한 줄"로 고침(날짜 머리줄, 왼쪽 큰 글자 = 지금 단계 "엣지 중/도면 기다림/시공 중", 위 세 칸 전체/생산 중/바뀐 것 + 찾기, 카드 100px). 안 3 줄에서 판 장수 칸 삭제. 안 2 돌아가기 글 "전체 주문". 고르기 절에 D10·D11 기록. Artifact Version 2(같은 URL).
- 아직 안 정한 것: 안 3·안 4 를 첫 화면 탭으로 둘지 레일에서만 열지 · 승인된 설계서(레일+시트 P1~P4)와 이 첫 화면의 구현 순서.

### 8.1 추가 결정(11-09, 작업자 시안 뒤)
- **D10** 생산팀 첫 화면 = 전체 주문 한 줄(시공일 순, 단계 표시). 오늘만/내 공정만이 아님.
- **D11** 일의 양(판 장수 등 ERP 에 없는 값)은 보이지 않음. 새 입력 칸 없음.
- **D12** (11-09 질문 창) "첫 화면으로 바꿔 바로 구현": 설계서에 생산팀 전용 첫 화면(안 1 전체 주문 한 줄) + 전체 화면 작업 시트(안 2)를 넣고, P1 착지를 이 화면으로 바꿔 구현 시작. 기존 레일·옆 시트 고치기(금액 가림·403 문구·인쇄 등)는 그 뒤 이어서.
- **D13** (11-09 질문 창) 안 3(내 공정 줄)·안 4(일정과 바뀐 것)는 첫 화면 위 탭 "전체 주문 | 이번 주 | 내 공정"으로. 레일은 생산팀에겐 뒤로.

## 10. 구현 진행 (P0 — 설계서 §12)

- **T0-1 DONE (2026-11-09)** 생산 홈 `GET /erp/production/home` + 착지(기기 무관). 새 파일: `foms/services/production_home_read_model.py`, `foms/web/production/home.py`(dashboard.py 가 501줄로 500줄 래칫에 걸려 같은 Blueprint 에 라우트만 분리), `templates/production/home.html`, `static/css/contexts/production/home.css`, `static/js/production/foms-production-home.js`(77줄), `tests/domains/test_production_home.py`(6). 고친 파일: `production_read_model.py`(`stage_codes` kwarg), `production_dashboard_display.py`(`build_production_home_enriched_rows`), `post_auth_navigation.py`(`is_production_home_user`·`production_home_url`, legacy `/` 분기), `orders/listing.py`, `auth/routes.py`(switch_user), `test_post_auth_navigation.py`(+4), `docs/harness/foms_failopen_inventory.json`(routes.py 줄 번호만).
- 검증: `APP_OK` · 새 시험 10 초록 · 바뀐 모듈에 닿는 시험 784 + 래칫·write-guard·프리랜서 문지기·REV-99·namespace 초록(visual 스위트는 file-backed sqlite 필요 — 환경 사유로 제외). 실화면(로컬 렌더 → Playwright): 1280×800 터치(레일 + 카드 100px 4칸), 800×1280 터치(모바일 셸 + 카드 두 줄), 1440×900 PC(상단 메뉴 + 같은 목록) 모두 설계대로. 세로 하단 탭에 생산이 없는 것은 T1-3 그대로.
- 알게 된 것: 시공팀 계정은 전역 문지기가 먼저 302(출고 화면)라 403 단언이 아니라 "200 아님"으로 둠 · `Order` 시드엔 `received_date`·`product`·`manager_name` 이 있어야 안전 · `g.current_user` 가 같은 사람이면 착지 판정이 추가 쿼리 0.
- 다음: T0-2 전체 화면 작업 시트(`/erp/production/sheet/<id>`), 카드 링크 교체.
- 첫 시안(`tablet-production-ui.html`)의 D7·D8 전 글("아직 정하지 않았어요"·"묻고 싶은 것" 2문항·F2 링크 "상세")을 결정으로 고치고 Artifact Version 2 로 재발행(같은 URL). T0-1 코드 커밋 `676c9d8cc`.
- **T0-1b DONE (11-09)** 사용자 지시 "날짜별로 접었다 펼 수 있게 like 모바일 실측 탭" → 실측 탭(`measurement/partials/mobile_list.html`·`mobile-glance-tabs.js`)의 말 그대로: 머리줄 단추 `aria-expanded`·`is-closed`·꺾쇠 회전·[모두 펼치기/접기]·펼침 수. 처음엔 오늘·내일만 펼침(실측 탭은 전부 접지만 생산은 오늘 일이 바로 보여야 해서 둘만 펼침 — 설계자 판단). 거르면 맞는 묶음 자동 펼침. 로컬 Playwright 로 접기·모두 펼치기·탭 전환 확인(5→0→1 접힘, 생산 중 탭에서 묶음 4 숨김·줄 4). 시험 25 초록.
- **T0-2 DONE (11-09)** 전체 화면 작업 시트 `GET /erp/production/sheet/<id>`(`foms/web/production/home.py`). 뷰 모델은 새 서비스 `foms/services/production_sheet_view.py` 로 옮긴 옆 시트 헬퍼(`_prod_sheet_*` 이름 그대로, dashboard.py 346줄로 줄어듦) + `full=True` 키(전화·주소·실측/시공·시공팀·도면 전체(이미지/파일)·공정 5줄 누가·몇 시·최근 불량). 템플릿 `templates/production/sheet.html`, CSS `static/css/contexts/production/sheet.css`, JS `static/js/production/foms-production-sheet-page.js`(도면 넘기기·전역 뷰어·공정 체크 POST·불량 칩 POST, 실패 글 §8 한 가지). 단추는 옆 시트와 같은 `data-tablet-sheet-action` 계약 — `tablet-domain-sheets.js` 의 document 클릭 게이트에 `[data-foms-prod-sheet-page]` 안이면 코호트 무관 1줄, 핀 20260921a→20261109a(칸반·출고 CHAIN·계약 시험 상수 함께). 홈 카드 링크를 이 라우트로. 글 "생산 완료"→"제작 완료"(이 페이지만). 가로 태블릿은 본문 높이를 화면에 맞추고 오른쪽만 스크롤(도면 늘 보임).
- 검증: 새 시험 6(`test_production_sheet_page.py`: 도면 2+PDF 1·tel·지도·시공팀·공정 5·불량 4·단추·금액 0·쿼리 ≤14·옆 시트 불변·인라인 0) + 관련 1,013 초록. 로컬 Playwright: 다음 도면 → "도면 2 / 2", 불량 칩 4 펼침, 서버 없이 공정 체크 → "연결이 끊겼어요…" 글. 1280×800·800×1280·1440×900 실화면 설계대로.
- 미룸: [인쇄] 링크는 T4-1 라우트 뒤 · "제작 완료"는 공정 5/5 전에도 눌림(옆 시트와 같음 — 막는 건 새 규칙이라 넣지 않음, 시안 글과 다름) · 세로 하단 탭 "생산" 없음은 T1-3.
- 다음: T0-3 탭 "이번 주"(안 4), T0-4 탭 "내 공정"(안 3).

## 11. 스테이징 반영 (2026-11-09, 사용자 선택 "스테이징에 올려 탭으로 먼저 보기")

- origin/deploy 가 그 사이 6커밋 앞서 있어 `session_worktree.py sync` 로 리베이스(AI_STATUS 충돌 2회 — 상류 판 + 이 세션 줄, 40줄 예산이 3,985/4,000 이라 가장 오래된 진행 중 줄(2026-09-29 할 일 묶음)을 '2026-09-08 상단 정리' 보관으로 내림). 두 번째 sync 는 ledger 밖 커밋이라 refuse → `--allow-foreign`(이 세션 커밋 확인 뒤).
- smoke 1차 FAIL: `test_state_guard` — `listing.py` 착지 3줄로 상태 쓰기 목록 줄 번호(371·372→374·375)만 밀림, `refresh_inventories` 는 안 잡아 `state_writer_scan.py` 직접 실행 → chore 커밋. smoke 2차 PASS(17,113 passed · 776 skipped · 3분 24초).
- 푸시: `deploy` 1880ce572 → **a680a3d07**(이 세션 커밋 5: 366b76cb0 T0-1 · 75bd1beef 문서 · 7e3030bdf 날짜 접기 · d9e04a67f T0-2 · a680a3d07 chore). 운영 반영 없음. CI·Railway 배포 확인은 아래 줄에.
- 배포 확인: `check_deploy_drift` staging a680a3d0 SUCCESS. 스테이징 실화면(관리자 쿠키, 1280×800 터치, Playwright `staging_home_check.py`): 홈 200 · 태블릿 마커 ready · 레일 · 날짜 33묶음 · 주문 110 · 가로 스크롤 없음 · 4xx 0 · JS 오류 0. 첫 카드 → 시트 200(공정 5·칩 4·tel·보류 단추, 도면 기다림 주문이라 제작 단추 없음 — 맞음). 세로 800×1280 하단 탭 있음. 긴급 알림 창(`#foms-urgent-alert`)이 화면을 덮어 DOM 에서만 치우고 찍음(읽음 처리 안 함).
- **스테이징 실데이터에서 본 것 ①** 시공일이 139일 지난 "도면 기다림" 주문이 첫 묶음, 33묶음 대부분이 지난 날짜(닫히지 않은 옛 주문). → **D14(설계자, 11-09)**: 시공일이 7일 넘게 지난 주문은 맨 아래 "지난 시공일 (7일 넘음)" 한 묶음(접힘)으로, 일주일 안에 지난 것은 급한 일이라 제자리. `production_home_groups(rows, today)` + 시험 1. ② 스테이징 도면 그림은 깨짐(알려진 스테이징 파일 문제, 코드 아님). ③ 한 주문의 "바뀐 것"이 "시공일 변경 미정 → 미정" 같은 줄을 여러 개 보임 — 알림 데이터 그대로(별건).
- CI: `ci_watch` a680a3d0 deploy **ALL GREEN**(출력 파일의 `CI_WATCH_EXIT=0` 로 확인). D14 묶음 고침은 뒤이어 smoke → deploy 푸시.
- **T0-3·T0-4 DONE (11-09)** 첫 화면 위 탭 셋 "전체 주문 | 이번 주 | 내 공정"(`?tab=all|week|steps`, D13). **이번 주**(안 4): 월~토 요일 칸(일요일은 일이 있을 때만 7칸)에 시공일 기준 주문 — 출고·시공은 같은 날짜 키(상차 = 시공일, 출고 보드도 `extract_all_construction_dates` 로 같은 날짜를 씀)라 한 칸에 단계 색(생산 전/생산 중/제작 완료/바뀐 것)으로 가름, ◀ ▶ 주 넘기기(`?week=월요일`), 오른쪽 받은함 = 미확인 변경(주문마다 한 장) + 취소 주문(묘비, `collect_production_tombstones`), [확인했어요] = 기존 change-ack(`tablet-domain-sheets.js` 게이트 예외를 `[data-foms-prod-home]` 까지, 핀 20261109b 네 곳). **내 공정**(안 3): 공정 5탭(마지막 탭 localStorage `foms-prod-step-tab`), 그 공정이 첫 미완인 제작 중 주문만 줄로(이름·품목·시공일, 일의 양 없음 D11), [<공정> 끝] 72px = POST steps 뒤 새로고침, 보류는 단추 없이 '보류', 제작 대기·검수 끝은 줄 밖 숫자. 파일: `production_home_read_model.py`(`production_home_week`·`production_home_inbox`·`production_home_step_queues`), `home.py`(tab·week), `home.html` + 파셜 3(`home_all/home_week/home_steps.html`), `home.css`, `foms-production-home.js`(190줄).
- 검증: 새 시험 6(`test_production_home_tabs.py`: 요일 칸 배치·묘비 받은함·공정 탭 숫자·보류 단추 없음·tab 값 방어·주 묶음 규칙·게이트·핀 lockstep·인라인 0) + 관련 74 초록. 로컬 Playwright: 엣지 탭 클릭 → 선택·보임·저장, 서버 없이 [끝] → 실패 글. 1280×800·800×1280 설계대로.
- 푸시 2: deploy a680a3d07 → 91e8bd020(D14) → **d271756c9**(T0-3·T0-4). smoke 17,120 PASS. `check_deploy_drift` staging d271756c SUCCESS. 스테이징 실화면: `?tab=week` 200(요일 6칸, 이번 주 일 0 — 옛 데이터, 받은함 30 + [확인했어요] 30), `?tab=steps` 200(재단 3·엣지 0…, 보이는 줄 cut, [끝] 1), 4xx 0·JS 오류 0. CI 는 `ci3.log` 로 감시 중.
