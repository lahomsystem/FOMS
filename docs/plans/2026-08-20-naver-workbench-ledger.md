# 네이버 수집 워크벤치 — UI 개편 본체 플랜 + 진행 원장

- 등급 `**C` · 브랜치 `session/naver-ingest` · 워크트리 `c:/tmp/foms-s-naver-ingest`
- 스펙: `docs/specs/2026-08-20-naver-ingest-workbench_SPEC.md`
- 목표 화면: `docs/design/mockups/naver-ingest-workbench-v2.html`
- 선행 결함(완료): `docs/plans/2026-08-20-naver-precursor-defects-ledger.md`

## 확정 사항

주소=`/admin/naver-ingest/triage` 본진 · 탭 하나씩 · 게이트 스위치로 롤백 · 서버 `?tab=` 라운드트립 ·
테스트 먼저 고치기 · 미푸시(세션 브랜치 유지).

## 원칙

**게이트 off 경로는 개편 내내 green 이어야 한다.** 기존 79건을 빨갛게 두면 개편 중에
다른 회귀가 들어와도 못 본다. 새 화면 테스트는 게이트를 켠 클라이언트로 따로 쓴다.

## Task

### W1 — 게이트 + 뼈대 + 처리 대기 탭 (DONE)
1. `feature_flags` 에 `is_naver_workbench_enabled(user_id)` 추가 (`FOMS_NAVER_WORKBENCH_ENABLED` + `_COHORT`)
2. `naver_ingest_triage` 라우트가 게이트로 템플릿 분기 (off=기존 `naver_triage.html`)
3. 새 템플릿 `templates/admin/naver_workbench.html` — 상태 스트립 + 헤더 이중표기 + 탭 4개(`?tab=`)
4. 처리 대기 탭: 좌 큐(색띠 3층 + 글자 라벨) / 우 상세(2단 대조표 + 상품주문 n행 표)
5. 주문 만들기 확인 모달(건수 재진술·되돌릴 수 없음·사후 경로)
**완료 기준**: 게이트 off 로 기존 79건 green · 게이트 on 신규 테스트 green(탭 4개 존재·기본 work·
색띠 라벨 4종·상품주문 표가 옵션 원문 전문 노출·모달 문구에 건수 재진술) · `APP_OK`.

### W2 — 발주확인 전 탭 (DONE)
선택 체크박스 + 선택 개수 동기 + 일괄 발주확인 모달. **선택 0집이면 버튼 비활성**.
**완료 기준**: 선택 0=버튼 disabled · n집 선택 시 라벨·모달 문장 숫자 동기 · 기존 fulfillment 라우트 재사용 확인(회귀 없음).

### W3 — 취소·반품 탭 (DONE)
액션 잠금 + `확인 완료`(선행 결함 #4 결과 재사용) + 클레임 사유 표시.
**완료 기준**: 주문 만들기·발주확인 disabled · 확인 완료만 활성 · 큐에서 실제로 빠짐(라우트까지).

### W4 — 전체 이력 탭 (DONE)
집 단위 표 + 취소·반품 회색 잔존(빼지 않는다) + 상태 필터 + 페이지네이션(필터 유지).
**완료 기준**: 취소 행이 회색+비활성으로 **남아 있음** · 필터·페이지 파라미터 왕복 유지 · 집 수 = 헤더와 일치.

### W5 — 실패 4단계 결과 띠 (DONE)
성공/실패 카운터 → 펼침 → 건별 사유 → 실패건만 재시도. `data-foms-no-autodismiss` 필수.
**완료 기준**: 실패가 있을 때만 뜸 · 5초 뒤에도 남음 · 재시도가 실패건만 대상.

### W6 — 리다이렉트 + 통합 검증 (DONE)
게이트 on 일 때 `/admin/naver-ingest` → 본진 리다이렉트. 옛 템플릿 정리 여부 판단(게이트 남기면 유지).
**완료 기준**: `pytest tests/services/integrations/ -q` 전건 · `APP_OK` · `pre_push_smoke.ps1` exit 0 ·
1440 실브라우저에서 4탭 왕복·모달·선택 게이트 확인 · AI_STATUS 갱신(상단 40줄 예산 준수).

## 함정 메모

- 계약 테스트가 **정확 마크업**을 문다(22곳). 배지 축·단위를 바꾸면 반드시 깨진다 — 게이트로 분리해 회귀 감지력을 지킨다.
- `.alert` 5초 자동닫힘 → 상시 안내·결과 띠는 `data-foms-no-autodismiss`.
- 새 감사 행위를 만들면 `audit_message_display` 라벨 등재 필수(pre_push_smoke 사각 → CI red).
- 주문 JSONB 직접 쓰기는 REV-99 게이트 → `execute_order_mutation` 경유.
- 집 수를 세는 식은 `naver_commerce/grouping.py` 하나뿐 — 새로 쓰지 말고 그걸 부른다.
- 템플릿 800줄 초과 시 partial 분리, 인라인 script 300줄 초과 시 `.js` 분리(프로젝트 규칙).
- 인라인 스타일 금지 → `erp-pro.css` 체계.

## 진행 기록
- 2026-08-20 스펙·플랜 작성. 현 구조 실측(템플릿 372+627줄·라우트 1066줄·계약 테스트 79건/정확 마크업 22곳). 승인 대기.
- 2026-08-20 사용자 승인 — W1 시작.
- 2026-08-20 **W1 완료**. 테스트 12건 먼저 red → 구현 → green. 최종 18건.
  파일: `feature_flags.is_naver_workbench_enabled` · `templates/admin/naver_workbench.html` ·
  `static/css/admin/naver-workbench.css`(인라인 스타일 금지 규칙) · `static/js/admin/naver-workbench.js` ·
  라우트에 `_active_tab()`·`_member_rows()` 추가.
  검증: `tests/services/integrations/` **306 passed**(게이트 off 경로 기존 79건 포함 전부 green) · `APP_OK` ·
  1440 실브라우저 렌더 확인(가로 스크롤 없음·JS 에러 0·2단 그리드 400px+1004px·색띠 5px).
  **실브라우저에서 테스트가 못 잡은 결함 2건을 잡았다**:
  ① 템플릿이 `selected.naver.customer_name` 을 읽었는데 정본 키는 `recipient_name` 이라
     대조표 수취인·연락처가 **조용히 빈 칸**이었다(섹션 존재만 확인하던 테스트는 통과했다).
     → 값 존재를 무는 테스트 추가 후 수정. 옵션 원문도 `option`(단수)이 정본이었다.
  ② 취소·반품 줄에 "손대지 않음"과 "주문 만들기"가 **동시에** 떴다(next_step 이 클레임을 모른다).
     → 테스트 추가 후 클레임이면 next_step 배지를 숨긴다.
  **W3 로 넘길 메모**: 지금 work 탭 큐는 미확인 전체라 취소·반품 집도 섞여 보인다.
  목표 화면(v2 목업)에서는 취소·반품 탭으로 분리된다 — 탭별 모집단 필터를 W3 에서 넣는다.
- 2026-08-20 **W2 완료**. 테스트 6건 먼저 red → 구현 → green. 워크벤치 테스트 25건.
  라우트 `_place_groups()` 추가(모집단=`_place_pending_clause()` + 취소·반품 제외),
  템플릿 place 탭(집 단위 체크박스·발송기한 배지·전부 선택), JS `wirePlaceOrder()`
  (선택 개수 ↔ 버튼 ↔ 모달 문장 동기), 기존 `/fulfillment` 라우트 재사용(집마다 1회 POST).
  검증: `tests/services/integrations/` **314 passed** · `APP_OK` ·
  1440 실브라우저(JS 에러 0·초기 버튼 disabled·2집 선택 시 활성·모달 문장
  "선택한 2집(배수경, 장효원)을 네이버에 발주확인으로 보냅니다"·가로 스크롤 없음).
  **다시 브라우저가 잡은 결함 1건**: 탭 배지 4집인데 목록 3줄. 배지는 SQL 로 세서
  취소·반품까지 포함했고 목록은 뺐다 — 취소 여부는 raw_snapshot 안이라 SQL 이 못 거른다.
  `_place_groups()` 결과를 배지·목록이 나눠 쓰도록 통일. (내가 그 함수 docstring 에
  "21집이라 써 놓고 목록이 19줄이면 사람이 헤맨다"고 적어 두고 그대로 냈다.)
- 2026-08-20 **W3 완료**. 테스트 6건 먼저 red → 구현 → green. 워크벤치 테스트 33건.
  큐를 `work_groups`(취소 제외) / `claim_groups`(취소만) 두 갈래로 나누고 배지도 각 목록 길이를 쓴다
  (W2 에서 낸 배지·목록 불일치의 재발 방지를 계약 테스트로 고정).
  취소 상세는 주문 만들기·발주확인을 `title` 사유와 함께 잠그고 `확인 완료`만 연다.
  JS `wireClaimDone()` 은 묶음 전체를 `/review` 로 순차 호출한다 — 형제 한 건이 남으면 같은 집이 다시 뜬다.
  **모달을 두지 않은 판단**: 큐에서 빼기는 네이버에 영향이 없다(불가역 아님).
  불가역이 아닌 일에 경고 모달을 달면 진짜 불가역 경고가 값을 잃는다.
  **W1 테스트 2건을 새 사실에 맞춰 고쳤다** — 취소건이 처리 대기에서 빠진 건 의도된 변화라 탭을 claim 으로 옮겼다.
  **또 잡은 결함 1건**: 기본 선택을 큐 전체에서 골라서, 처리 대기 탭인데 오른쪽 상세에 취소 집이 펼쳐졌다
  (목록엔 없는데 상세만 뜨는 상태). 탭 안에서 고르도록 고치고 `?link_id=` 명시는 존중한다 — 계약 테스트 2건 추가.
  검증: `tests/services/integrations/` **322 passed** · `APP_OK` ·
  1440 실브라우저 3탭(배지=줄 수 일치 work 3/3·place 2/2·claim 2/2 · 버튼 잠금 [create True, place True, done False] · JS 에러 0).
- 2026-08-20 **W4 완료**. 테스트 6건 먼저 red → 구현 → green. 워크벤치 테스트 39건.
  `_history_view()` 추가 — 표 데이터는 기존 관리 화면과 **같은 함수**(`_link_rows`)를 쓴다.
  집 묶음·페이징·클레임 판정이 두 벌이 되면 두 화면 숫자가 또 갈린다.
  취소·반품은 빼지 않고 `wb-hist--muted` 회색 행으로 남긴다(결정 2). 필터 칩·페이지 링크는
  `tab`·`status`·`place` 를 그대로 들고 간다(선행 결함 #8 의 워크벤치 쪽).
  **브라우저에서 다듬은 것 2건**: ① 잠긴 버튼이 파란 primary 그대로여서 잠긴 티가 안 났다 —
  회색 outline + 빨간 사유 줄로 바꿨다(기존 이력 화면이 이미 그러고 있었다).
  ② 승격 불가한 행(FAILED 등)에도 버튼을 냈다 — 기존 화면과 같은 `pending_link_id` 게이트로 맞췄다.
  검증: `tests/services/integrations/` **328 passed** · `APP_OK` ·
  1440 실브라우저(행 5·회색 2·잠긴 버튼 2·실패 사유 노출·가로 스크롤 없음·JS 에러 0).
- 2026-08-20 **W5 완료**. 테스트 8건 먼저 red → 구현 → green. 워크벤치 45건 + fulfillment 18건.
  **착수 전 진짜 원인을 찾았다(사용자 승인 후 원인까지 수정)**: 결정 7 은 화면 문제가 아니었다.
  `fulfillment.py:128` 이 실패 사유를 **일부러** `triage_state.fulfillment.last_error` 에 적고 올리는데,
  워커(`tasks.py`)가 모든 예외에 `db.rollback()` 을 걸어 그 기록까지 지워 왔다 —
  실패가 DB 어디에도 안 남고 로그·RQ 에만 있었다. 화면은 보여줄 데이터 자체가 없었다.
  수정: 워커가 `FulfillmentError` 만 커밋하고 다시 올린다(그 경로는 네이버 호출 실패라 성공 표식이
  아직 하나도 쓰이지 않았다). 다른 예외는 무엇이 쓰였는지 알 수 없어 그대로 롤백한다.
  반대편도 고정했다 — 실패 커밋이 성공 표식을 데려오지 않고, 재시도가 실제로 네이버를 부르며,
  성공하면 낡은 사유가 지워지는지까지 테스트 2건.
  화면: `_failure_rows()` 가 그 기록을 집 단위로 접어 읽고, 결과 띠가 4단계를 담는다.
  실패가 없으면 띠 자체가 안 뜬다(빈 경고는 사람이 안 읽게 만든다). 탭과 무관하게 항상 보인다.
  검증: `tests/services/integrations/` **336 passed** · `APP_OK` ·
  1440 실브라우저(실패 3줄·재시도 대상 3·**6초 뒤에도 띠 유지**·가로 스크롤 없음·JS 에러 0).
- 2026-08-20 **W6 완료 — 플랜 전체(W1~W6) 종료**. 테스트 3건 먼저 red → 구현 → green. 워크벤치 48건.
  게이트 on 이면 `/admin/naver-ingest` 가 본진 `?tab=all` 로 리다이렉트하고 `status`·`place`·`page` 를
  그대로 넘긴다(조건을 잃으면 방금 좁힌 목록을 다시 만들어야 한다). off 면 옛 화면 그대로 — 롤백이 실제로 된다.
  옛 템플릿 2종은 **지우지 않았다**: 게이트 off 경로의 정본이고, 그 경로가 green 이어야 롤백이 의미를 갖는다.
  최종 검증: `tests/services/integrations/` **339 passed** · **PG 레인 737 passed** ·
  `pre_push_smoke.ps1` **PASSED(323)** · `APP_OK` ·
  1440 실브라우저 4탭 왕복(탭 선택 정확·결과 띠 전 탭 유지·가로 스크롤 없음·JS 에러 0) ·
  리다이렉트 실측 `302 → /admin/naver-ingest/triage?tab=all&status=FAILED&place=PENDING`.
  AI_STATUS 갱신(상단 40줄 3781자/예산 4000).

## 남은 일 (다음 세션)
1. **미푸시** — 사용자 결정으로 세션 브랜치에만 있다. deploy 승격 시 `pre_push_smoke` 재확인.
2. **배포 시 backfill 필수** — `python scripts/maintenance/backfill_naver_group_key.py`.
   안 돌려도 화면은 죽지 않고 예전 폴백으로 떨어질 뿐이다.
3. **게이트 켜기** — `FOMS_NAVER_WORKBENCH_ENABLED=1` + `FOMS_NAVER_WORKBENCH_COHORT=<id>` 로 소수 먼저.
4. **실사용 확인 후 옛 화면 정리 여부 결정** — 지금은 롤백 경로라 남겨 둔다.

## 코드 리뷰 결과 (2026-08-20, 멀티에이전트 5축 + 적대적 검증)

리뷰 45건 지적 / 검증 25건 판정(19건 반증 실패). 워크플로는 30/35 에서 승인 대기로 멈춰 종합 단계 미실행 —
아래는 **감독자가 코드로 직접 재확인한 것만** 적는다. 나머지 high 9건은 미검증 상태로 다음 세션 몫.

### 반드시 고칠 것 (직접 확인 완료 — 전부 이번 세션이 만든 것)

1. **[권한 확대] STAFF 가 수집 이력을 보게 됐다** — `foms/web/admin/naver_ingest.py`
   `naver_ingest_dashboard` 는 `@role_required(["ADMIN"])`(358행)인데 `naver_ingest_triage` 는
   `["ADMIN","MANAGER","STAFF"]`(505행). W4 가 ADMIN 전용 `_history_view`(수집 이력·상태 집계·실패 사유)를
   STAFF 도 여는 라우트 안에 넣었다. **회귀가 아니라 신규 노출**이다.
   조치: `?tab=all` 을 ADMIN 에게만 열거나(비 ADMIN 은 탭 자체를 숨기고 접근 시 work 로), 이력 데이터를 권한별로 나눈다.

2. **[구분자가 공백문자] 파이썬과 SQL 의 묶음키가 또 갈린다** — `naver_commerce/grouping.py`
   `''.isspace()` 가 **True** 라 `resolve_group_key` 의 `.strip()` 이 앞뒤 구분자를 잘라낸다:
   `'N-K'.strip()` → `'N-K'`. SQL 쪽 `nullif(group_key,'')` 는 안 자른다.
   전화·주소가 빈 상세(claim_watch 갱신 등)에서 두 경로가 다른 키를 만든다 —
   **이번 세션이 없애려던 '정의가 두 벌' 결함을 새로 만든 것**이다.
   조치: `.strip()` 대신 `or ""` 만 쓰거나, 구분자를 공백이 아닌 문자로 바꾼다. 계약 테스트 동반 필수.

3. **[불가역 호출이 옆 집까지 나간다] `_links_of_group` 이 아직 주문번호 기준** — `naver_commerce/fulfillment.py:63`
   화면은 `group_key`(주문번호+전화+주소)로 집을 가르는데 워커는 같은 `external_order_no` 전부를 처리한다.
   분할배송에서 A집만 체크해도 B집 상품주문까지 발주확인이 나간다. **되돌릴 수 없다.**
   조치: `_links_of_group` 도 `group_key` 기준으로 좁히거나, 화면이 대상 링크 id 전부를 명시적으로 보낸다.

### 미검증(다음 세션에서 코드로 확인할 것) — 리뷰가 high 로 든 나머지
- 재시도 버튼이 항상 `action:'confirm'` — dispatch 실패는 영구히 띠에 남는다(js:34)
- `group_key_expression()` 의 coalesce 가 `ix_external_order_link_group` 를 무력화(seq scan)
- `_failure_rows` 가 `triage_state.isnot(None)` + LIMIT 250 — 진짜 실패가 창 밖으로 밀릴 수 있다
- `_place_groups` 가 탭과 무관하게 매 렌더 실행(비용)
- 네이버 200 + `failProductOrderInfos` 부분 실패를 성공으로 커밋(fulfillment.py:182)
- 워크벤치에 **발송처리 버튼이 없다** — T16-H 계약 테스트는 전부 게이트 off 로 돌아 못 잡는다
- `_place_groups` 가 클레임 판정을 '발주확인 전 멤버'만 보고 내린다
- `resolve_group_key` 계약 테스트 부재(변이해도 190건 green)

**판단: 지금 상태로 게이트를 켜면 안 된다.** 1·3 은 권한·불가역 호출이라 승격 전 필수.
