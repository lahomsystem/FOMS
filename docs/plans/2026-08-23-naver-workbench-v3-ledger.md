# 네이버 수집 워크벤치 v3 — 구현 원장 (2026-08-23)

계약: `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md`
목업: `docs/design/mockups/naver-workbench-v3.html`
근거: 3CEO 토론(현장 가치·불가역 위험·비용 순서) — 사용자 지목 통증 2개
(① 한 집 처리에 탭 왕복 ② 행 클릭마다 전체 페이지 재요청)

작업 위치: `c:\tmp\foms-s-naver-ingest` / 브랜치 `session/naver-ingest`
시작 시점 HEAD: `4c8d7a2f` 직전 = 목업 커밋

## 파일 소유권 (동시 편집 충돌 방지)

| 담당 | 파일 |
|---|---|
| 서버 | `foms/web/admin/naver_ingest.py` |
| 템플릿 | `templates/admin/naver_workbench.html`, `templates/admin/partials/naver_workbench_pane.html` |
| nav | `foms/services/menu_config.py`, `templates/partials/shared/layout_nav.html`, `foms/services/naver/triage_count.py`, `tests/services/integrations/test_naver_nav_entry.py` |
| JS·CSS | `static/js/admin/naver-workbench.js`, `static/css/admin/naver-workbench.css` |
| 테스트 | `tests/services/integrations/test_naver_workbench.py` 외 |

**손대지 않는 것**: `templates/admin/naver_triage.html`(게이트 OFF 롤백 경로),
불가역 mutation 라우트의 동작(`fulfillment.py` 전체).

## Task

| Task | 내용 | 완료 기준 | 상태 |
|---|---|---|---|
| V-1 | 서버 — 탭 2개·필터·`_work_groups` 병합·pane 프래그먼트 라우트 | APP_OK + 컨텍스트 키가 계약 §2.4와 일치 | DONE — 신설 11함수 전부 50줄 이하, ingest+place 45 passed |
| V-2 | 템플릿 — 셸 축소 + pane 파셜 신설 + 액션 2종 신설 | Jinja PARSE_OK + `id="wb-` 중복 0 | DONE — 셸 973→475줄, pane 파셜 478줄, 중복 id 0 |
| V-3 | nav — 이름/진입구 4→1 + 뱃지 모집단 일치 | APP_OK + nav 테스트 green | DONE — 15 passed, 진입구 1개, 뱃지 캐시 게이트별 분리 |
| V-4 | JS — 전면 위임 전환 + 행 클릭 부분 갱신(fetch) + 벌크 재배선 | 실브라우저에서 전체 리로드 없음 확인 | DONE — 417→750줄, headless 하네스 33건 PASS |
| V-5 | CSS — 칩·벌크바·잠금행·pane sticky, `max-height` 제거 | 1440/991px 두 폭 확인 | DONE — 353줄, `.wb-queue` max-height 제거·`#wb-pane` sticky(≥992px)·잠금행 색 무의존 3층 |
| V-6 | 계약 테스트 갱신 + 신규 8종 (계약 §7) | `tests/services/integrations` 전건 green | 진행 중 (3차 위임) |
| V-7 | 통합 검증 — APP_OK·전건·pre_push_smoke·실브라우저 QA | 목업 대비 동작 일치, 모든 버튼 실동작 | PENDING |
| V-8 | 2CEO 통합 리뷰 (불가역 위험 / 통합 품질) | 지적 전량 원장 등재 후 처리 | PENDING |
| V-9 | 커밋 + deploy 푸시 + CI green | pre_push_smoke exit 0, CI 4개 green | PENDING |

## 진행 기록

- (1차 위임 시작) 서버·템플릿·nav 3갈래 병렬. 계약 문서로 컨텍스트 키·DOM id 를 선고정 —
  이게 어긋나면 세 사람이 서로 다른 화면을 만든다.

### V-3 / V-5 완료 (검증 직접 확인)

- **CSS**: `.wb-queue` 의 `max-height:640px` 제거 확인, `#wb-bulk` 기본 `display:none` + `.on` 토글,
  `.wb-row--locked` 는 끊긴 띠 + opacity + 취소선(색 단서 0). `#wb-pane` sticky 는 `min-width:992px`
  안에서만. 판단 갈릴 지점 1곳: pane 에 `max-height: calc(100vh - 24px)` + 자체 스크롤을 줬다
  (sticky 요소가 뷰포트보다 길면 아래쪽에 손이 안 닿는다). 되돌리려면 그 두 줄만 지우면 된다.
- **nav**: 진입구 4 → 1. `data/admin/menu_config.json` 이 실제 SSOT 라 파이썬 기본값만 고치면
  화면이 안 바뀐다(함정). 게이트 OFF ADMIN 은 `naver_triage.html:13-18` 의 '수집 상태 화면으로'
  버튼으로 옛 화면에 그대로 간다 — **기능 소실 없음 확인**, 회귀 테스트로 고정.
- **뱃지**: 게이트 ON = `len(_work_groups(db)[0])` (SQL 재계산 금지 — 취소 표식이 JSONB 라
  SQL 로는 같은 수가 안 나온다. 이게 67 vs 45 의 원인이었다). 게이트 OFF 는 옛 정의 유지,
  캐시 키를 `NAVER:queue` / `NAVER:work` 로 분리(같은 칸이면 서로의 숫자를 읽는다).
  순환 import 는 함수 안 지연 import 로 해소, `naver_ingest.py` 무접촉.
- **성능 메모(승격 전 확인)**: 뱃지가 COUNT 1회 → `_work_groups`(조회 여러 번)로 바뀐다.
  30초 전역 캐시 + 현재 코호트 38 단독이라 무해하나, 전 직원 개방 시 TTFB 재측정 필요.
- **운영 메모**: `data/admin/menu_config.json` 은 `/admin/menu` 런타임 저장 대상. 운영에서
  관리자가 저장한 적이 있으면 배포본 이름이 안 보일 수 있다 — 그때는 `/admin/menu` 재저장.

### V-1 / V-2 완료

- **서버**: 신설 11함수(`_queue_links`·`_orders_by_id`·`_link_by_id`·`_pane_context`·`_selected_link`·
  `_render_workbench`·`naver_ingest_triage_pane`·`_active_filter`·`_group_matches_filter`·
  `_filter_counts`·`_work_groups`), 전부 50줄 이하(최대 45). `_pane_context` 가 pane SSOT —
  전체 렌더와 프래그먼트가 이 함수 하나를 쓴다(모집단 갈라짐 차단).
  **F5 로직 유지 확인**: pane 의 집은 `_group_of_link` 결과를 **무조건** 쓴다(v2 의 큐 폴백 제거 —
  그게 절대 규칙 2 위반이었다).
- **템플릿**: 셸 973 → 475줄(800줄 규칙 통과), pane 파셜 478줄 신설. 모달은 카드 밖·pane 안에 둬서
  카드 `overflow:hidden` 회피 + pane 교체 시 함께 갈린다.
  계약과 다르게 한 것 4건(전부 타당, 승인):
  1. 트리거 `#wb-create` 신설 — 기존 JS 가 `#wb-create-order` 를 **submit** 으로 물고 있어
     그걸 트리거로 바꾸면 모달 없이 즉시 주문 생성(불가역)이 된다.
  2. 붙이기는 `.wb-attach` **클래스** — 후보 수만큼 렌더돼 id 면 중복(절대 규칙 1 위반).
  3. `전부 선택`을 벌크 바가 아니라 목록 카드 헤더에 — 벌크 바는 0집이면 숨어 첫 선택을 못 한다.
  4. 이력 행의 `열어서 만들기` 버튼 → 평범한 텍스트 링크(절대 규칙 3 을 문자 그대로).
- 남은 테스트 실패 25건은 전부 v2 마크업 전제 — V-6 담당 몫. 브리틀 3건은 템플릿 쪽에서 되돌려 green.

### ⚠ 사고 — 로컬 dev Postgres 행 데이터 소실 (2026-08-23)

서버 담당의 임시 검증 pytest 파일이 `tests/conftest.py` 보다 **먼저** `db` 를 import 했다.
엔진이 sqlite 가 아니라 로컬 dev Postgres(`localhost/furniture_orders`)에 묶인 채
`app` 픽스처 티어다운의 `Base.metadata.drop_all(bind=engine)` 이 돌아 테이블 86개가 드롭됐다.

- 스테이징·운영 **무관**. pytest 정상 경로(sqlite 인메모리)도 무관.
- 스키마는 `create_all` 로 재생성(현재 88 테이블, `alembic_version=access_log_00`).
- **행 데이터는 복구 불가** — 직접 확인: `orders 0 · users 0 · external_order_links 0 · notifications 0`,
  `stage_gate_templates 18` 만 생존. 로컬 pg_dump 백업 없음.

**근본 수정 완료**: `tests/postgres_guard.assert_not_postgresql` 는 **환경변수 문자열**만 봤다.
`db.py` 는 `DATABASE_URL` 이 없으면 로컬 Postgres 하드코딩 fallback 으로 붙는데, conftest 가
`setdefault` 로 env 에 sqlite 를 넣는 순간 가드는 "sqlite 니까 안전"으로 통과한다.
→ `assert_engine_not_postgresql(engine)` 신설(**엔진이 실제 붙은 곳**으로 판정),
`assert_safe_for_schema_reset(..., engine=engine)` 로 확장, conftest 의 `create_all` **앞**과
`drop_all` 앞 양쪽에 배선. 자체 검증: Postgres URL 엔진 → 차단, sqlite → 통과.

### V-4 완료 + 열린 결정 3건 처리 (2026-08-23)

**JS**(417 → 750줄). 리스너는 `document` 4개뿐(`click`·`change`·`show.bs.modal`·`popstate`),
요소 단발 배선 0 — pane 이 교체돼도 죽지 않는다. 모달을 **여는** 일은 마크업의 `data-bs-toggle`
이 하고 JS 는 확인 버튼만 문다(모달 없이 POST 하는 경로 0).

부분 갱신: 요청 토큰으로 경합 차단(늦게 온 응답이 새 선택을 못 덮는다) · 비200·네트워크 실패·
**조각이 아닌 응답**(로그인 리다이렉트) 전부 `location.href` 폴백 · `popstate` 로 뒤로가기 지원 ·
pane 교체 직전 pane 안 모달 인스턴스 `dispose()`(열린 채 교체되면 백드롭·`body.modal-open` 이
남아 화면이 어둡게 잠긴다).

헤드리스 하네스 33건 PASS: 체크박스 클릭이 행을 열지 않음 / 전부 선택이 잠긴 행을 안 고름 /
모달 재진술 집·건수 일치 / 행 클릭 시 pane 라우트 호출·전체 이동 없음 / 늦은 응답이 새 선택
미덮음 / 열린 모달 안은 채 교체해도 백드롭 0 / 뒤로가기 복귀.

**열린 결정 3건 — 처리 완료**

1. **성공 피드백 자리 없음** → `#wb-pane-ack` 신설(파셜) + CSS + `submitConfirm` 배선.
   발주확인은 큐에 넣기만 해서 pane 을 다시 받아도 화면이 그대로다. 표시가 없으면 사람은
   "안 눌렸나" 하고 **한 번 더 누른다** — 불가역 호출에서 재클릭은 그 자체가 사고 경로다.
   `:empty` 면 접히고, `data-foms-no-autodismiss` 로 전역 5초 자동닫힘을 피한다.
2. **`aria-busy` 시각 피드백 없음** → `#wb-pane[aria-busy="true"]` 흐림 + `pointer-events:none`.
3. **칩 이동 시 선택 유지** → **하지 않는다(결정).** 칩 href 에 `link_id` 를 실으면
   `_selected_link` 가 그걸 무조건 우선해 **목록엔 없는 집이 상세에만 열린다** — 절대 규칙
   (화면 집 == 서버 집)을 정면으로 깬다. 필터를 바꾸면 보이는 목록의 첫 집으로 초기화되는
   현재 동작이 정본이다.

**?v 핀**: 이미 `20260823b`. 이번 JS·CSS 수정도 같은 v3 변경셋 안이고 `b` 로 나간 배포가 없어
추가 범프 불필요.

## V-8 통합 리뷰 — 품질 렌즈 지적 (2026-08-23, 전량 등재)

판정: **조건부** — [H1][H2] 고치고 나간다. 다섯 겹(서버·템플릿·JS·CSS·테스트) 이름은 거의 맞물린다.
어긋난 건 이름이 아니라 **판정이 갈라진 자리** — v2 에서 `_place_groups` 한 곳에만 있던 안전장치가
v3 병합 후 한쪽 원천에만 남았다.

| ID | 등급 | 지적 | 처리 |
|---|---|---|---|
| H1 | 높음 | **형제 취소 가드가 두 원천 중 하나에만.** `_claim_blocked_group_keys` 가 `_place_groups`(원천2) 안에만 있어, 원천1(큐) 출신 집은 검사 없이 목록에 오른다. 결과: 잠겨야 할 집에 **체크박스가 열리고**(벌크 발주확인 대상) 잠금 표시·취소 칩에도 안 뜬다. 그런데 그 행을 열면 pane 은 `_household_has_claim` 으로 형제 전부를 읽어 잠근다 → **목록과 상세가 정반대를 말한다**. 워커 `_claim_guard` 가 실호출은 막지만 화면이 거짓말하고 실패 띠가 오염된다. v2 는 체크박스가 `place_groups` 루프 안에만 있어 구조적으로 불가능했다 — **병합이 만든 신규 회귀** | 대기 |
| H2 | 높음 | **벌크 모달 건수 ≠ 서버가 처리할 건수.** `data-count={{ group.count }}` 는 `_group_queue` 가 만든 **큐 부분집합** 크기인데 워커 `_links_of_group` 는 `reviewed_at` 무관하게 **집 전체**를 처리한다. pane 은 F5 로 `_group_of_link` 를 쓰게 고쳤는데 **벌크는 안 고쳤다**. 같은 화면에서 목록 줄 "1건" · 벌크 모달 "1건" · pane 모달 "3건" 이 동시에 뜬다 | 대기 |
| M1 | 보통 | nav 뱃지가 `_work_groups` 전체를 부르는데 `except SQLAlchemyError` 만 잡는다. 스냅샷 하나가 예상 밖이면 `TypeError` 가 새어 **nav 렌더하는 모든 페이지 500**. docstring 은 "뱃지는 부가 정보라 페이지를 죽이지 않는다"고 약속 중 | 대기 |
| M2 | 보통 | 성능: 뱃지가 COUNT 1회 → 조회 4~6회 + JSON 파싱 수백 건. 30초 캐시·코호트 38 단독이라 지금 무해. **전 직원 개방 전 TTFB 측정 필수** | 원장 완료 기준으로 승격 |
| M3 | 보통 | `aria-current` 미부착 케이스. 행은 `selected_group.id == group.id` 비교인데 `group.id`(목록 모집단 최대금액) ≠ `selected_group.id`(집 전체 최대금액)일 수 있다 → 열린 집이 하이라이트 안 되고, `init()` 이 `aria-current` 를 못 찾아 뒤로가기가 전체 리로드로 떨어진다 | 대기 |
| M4 | 보통 | pane 판정 단위 혼재 — `dispatched` 만 링크 1건 기준(나머지는 집 단위). 워커는 상품주문별로 찍어 부분 성공 가능 → 어느 상품주문으로 들어왔느냐에 따라 취소 버튼이 있기도/없기도 | 대기 |
| M5 | 보통 | 판정 중복 — `place` 술어 2벌(서버·템플릿), `locked` 3벌(서버·셸·pane). 계약이 "술어 SSOT 하나"라 선언했는데 화면 두 겹이 재구현. **H1 이 정확히 이 갈라짐에서 나왔다** | 대기 |
| M6 | 보통 | 원장 "열린 결정 3"의 불변식 문장이 부정확. 이력 탭 `처리 탭에서 열기` 가 실제로 "목록에 없는 집을 상세에" 연다(필요한 경로). 문장을 안 고치면 6개월 뒤 누가 링크를 지운다 | 대기 |
| L1 | 낮음 | 불가역 모달 4종이 `#wb-pane`(overflow:auto + max-height) 안에 있다. `position:fixed` 라 안 잘릴 것으로 보나 **미검증** — 실브라우저 1440/991 확인 | QA 담당 확인 중 |
| L2 | 낮음 | pane 버튼의 `naver-attach-btn` 클래스 + JS 대응 분기 = 죽은 이중 배선 | 대기 |
| L3 | 낮음 | 계약 테스트가 **속성 순서**를 단언(`id="..." disabled` 문자열 split) → 마크업 포맷을 인질로. 파싱으로 바꾸면 그 제약과 주석이 함께 사라진다 | 대기 |
| L4 | 낮음 | `assert "네이버 주문" not in html` 이 전체 HTML 전역 검사 — 고객명·메모가 그 글자를 담으면 깨진다 | 대기 |
| L5 | 낮음 | `naver_ingest_triage_pane` 반환 타입 힌트 없음 | 대기 |
| L6 | 낮음 | `test_zz_review_probe.*.pyc` 잔재(로컬 DB 드롭한 그 파일) | 대기 |

**죽은 코드**: `_pane_context` 의 `sales_users`(두 템플릿 미사용 — pane 조각 요청마다 `User` 전 행 조회 낭비) ·
CSS `.wb-row__amt`·`.wb-cmp__sum`·`:has()` 중복 규칙 · `naver-attach-btn` 이중 배선.
**CSS 없는 클래스 7종**: `.wb-detail*`·`.wb-acts`·`.wb-acts__why`·`.wb-result__why`·`.wb-hist`.
실피해는 `.wb-acts__why` 하나 — 계약 §3.3 이 "목업 문장 그대로"라 못박은 안내 문구 3종이 맨 텍스트로 나온다.
**동어반복 테스트**: `test_naver_workbench_v3_population.py` 의 뱃지 테스트가
`len(_work_groups(...))` 를 `len(_work_groups(...))` 와 비교 — 어떤 회귀도 못 잡는다.

**규칙 위반**: `_place_groups` 가 44 → 52줄(50줄 초과, 대부분 주석) · `naver_ingest_triage_pane` 타입 힌트.
나머지(인라인 스타일·jQuery·tojson·800줄·fetch 검증·API 형식·bare except)는 전부 통과.

**잘된 것(되돌리지 말 것)**: `_pane_context` 단일 SSOT · pane 판정값 선계산 블록 ·
모달을 pane 안에 둔 결정 + `teardownModals` · 전면 위임 + 요청 토큰 경합 차단 ·
행 `href` 유지 + `location.href` 폴백 · 불가역 모달 없이 POST 하는 경로 0 ·
잠긴 버튼을 지우지 않고 `title` 로 이유 남기기 · `#wb-pane-ack` · 뱃지 캐시 게이트별 분리 ·
`assert_engine_not_postgresql`.

## V-8 통합 리뷰 — 불가역 위험 렌즈 지적 (2026-08-23, 전량 등재)

판정: **막아야 함**(리뷰 시점 기준). 계약 §0 절대 규칙 6개 중 2·6 이 X.
※ 이 리뷰는 **H1·H2·M1 수정이 들어가기 전 워킹트리**를 봤다 — 아래 상태 열이 정본.

| ID | 등급 | 지적 | 상태 |
|---|---|---|---|
| 치명-1 | 치명 | `_attach_household_counts` 가 `group["external_order_no"]` 를 읽는데 **그 키가 없다** → 항상 no-op → 벌크 재진술이 여전히 큐 부분집합 크기 | **이미 수정됨** — 대표 링크에서 주문번호를 뽑도록 고쳤고 `household_count==3` 회귀 테스트가 잡는다(처음엔 `1 == 3` red 였다) |
| 치명-2 | 치명 | **`#wb-pane` 의 `position:sticky` 가 stacking context 를 만든다.** Bootstrap 백드롭은 `body`(z:1050)에 붙는데 모달 4종은 pane 안이라 그 컨텍스트에 갇힌다 → **백드롭이 모달을 덮어 데스크톱에서 단건 불가역 액션 4종이 실행 불가**. 벌크 모달만 `.wb-split` 밖이라 멀쩡 → "벌크만 되고 단건은 안 되는" 최악의 비대칭. 원장 L1 은 clipping 으로 오진했는데 진짜 원인은 stacking context | 수정 |
| H-A | 높음 | 형제 취소 가드 여전히 반쪽 — `_claim_blocked_group_keys` 가 `place_order_status='OK'` 형제의 **클레임만** 읽는다. ① 발주확인 전 형제의 클레임 ② 우리가 취소한 형제(`canceled_at`) 미커버 → 행이 안 잠기고 체크박스가 열린다 | 수정 |
| H-B | 높음 | FAILED/PENDING_REVIEW 제외가 **화면에만** 있고 액션엔 없다. `_links_of_group` 에 status 필터가 없고, 이력 탭 `처리 탭에서 열기` 가 `pending_link_id`(PENDING_REVIEW 포함)를 그대로 열어 **깨진 집에 발주확인 버튼이 열린다** | 수정 |
| H-C | 높음 | `aria-current` 미부착(대표 링크 id 비교) | **이미 수정됨**(M3) |
| H-D | 높음 | nav 뱃지가 전 페이지에서 `_work_groups` 전체를 돈다 — TTL 만료 후 첫 요청이 비용을 문다. **전 직원 개방 전 TTFB 측정 없이 승격 불가** | 승격 게이트로 등재 |
| M-1 | 보통 | `확인 완료 — 큐에서 빼기` 가 행을 안 없앤다(그 집이 `place_pending` 이면 원천 2 로 남는다). 버튼 title·목록 헤더 "확인 대기"가 v3 에서 거짓이 됐다 — 사람이 같은 버튼을 반복해 누른다 | 수정(문구) |
| M-2 | 보통 | 주문 만들기 모달이 건수 과대 진술 — `member_count`(집 전체) vs `promote_link_to_order` 의 `_group_siblings`(`order_id IS NULL` + COLLECTED/PENDING_REVIEW). 방향은 안전하나 재진술이 거짓 | 원장 등재 |
| M-3 | 보통 | `?link_id=` 가 목록 밖 집을 완전무장 상태로 연다. 계약 테스트가 그 동작을 못박아 뒀다 — pane 에 "지금 목록에 없는 집" 표시 필요 | 원장 등재 |
| M-4 | 보통 | 이력 탭에서도 `_work_groups`·`_pane_context` 를 전부 계산하고 버린다 | 원장 등재 |
| M-5 | 보통 | `_pane_context` 의 `sales_users` 미사용 — pane 조각 요청마다 `User` 전 행 조회 | 수정 |
| M-6 | 보통 | pane 프래그먼트에 대한 STAFF 계약 테스트 없음(§0.4 그물이 새 라우트를 안 덮는다) | 수정 |
| M-7 | 보통 | `naver_ingest_fulfillment` 라우트에 게이트 검사 없음(cancel 은 있다). 롤백 시 이 경로가 열린 채 남는다 | 수정 |
| L-1~L-5 | 낮음 | 집 키 폴백 2벌 · popstate 초기 reload · 이력/처리 칩 모집단 상이 · `_group_of_link` 의 `limit=PAGE_SIZE` 폴백이 과소 진술 방향 · 벌크 실패가 alert+reload 뿐 | 원장 등재 |
| INV | 필수 | `triage_count.py` 신규 broad except 1건 → `foms_failopen_inventory.json` 재생성 안 하면 **CI red**(pre_push_smoke 사각) | 수정 |

**확인된 정상(중복 수정 금지)**: pane 의 집 == `_group_of_link` == `_links_of_group`(단건 모달 완결) ·
벌크 대상 ⊆ 화면 목록("선택 없으면 전체" 패턴 0건 — 2026-08-14 AS 증발 패턴 재발 없음) ·
모달 없이 POST 되는 불가역 경로 0 · 한 번 눌러야 할 게 두 번 나가는 자리 없음 ·
경합 토큰·폴백·모달 잔재 정리 · 체크박스가 행을 안 연다 · STAFF 는 `all` 컨텍스트 자체를 못 받는다 ·
서버 최종 방어선(`_claim_guard`·`_cancel_guard`·사유 코드 재검증) 무접촉 · `?v` 핀 양쪽 범프 ·
게이트 OFF 롤백 경로 무변경.

## V-7 실브라우저 QA 결과 (2026-08-23) — 18항목 중 17 PASS

로컬 시드 11집·링크 16건·주문 3건(계정 `qa_v3` ADMIN / `qa_v3_staff` STAFF, 코호트 1,2).
**네이버 실호출 0건** — RQ 워커 미기동 + Redis 없음이라 enqueue 라우트가 전부 503 으로 정상 실패.
스테이징·운영 무접촉. 시드는 로컬 dev DB 에 남겨 뒀다(비어 있던 DB라 덮어쓴 데이터 없음).

PASS: 행 클릭 부분 갱신(문서 요청 0) · 칩 4종 숫자==줄수 · 체크박스가 행을 안 엶 ·
전부 선택이 잠긴 행 제외 · 벌크 재진술 5집·6건 일치 · 벌크 enqueue 5건 · 주문 만들기 200 ·
발주확인 단건 `{action:'confirm'}` + 성공 시 pane 만 갱신 + `#wb-pane-ack` · 발송처리 분기
(NEW disabled / ADDON `지금 닫기`) · 취소 모달 사유 7코드 + 재진술 3건 일치 · 확인 완료 후
스트립·탭·칩 동시 감소 · 붙이기/되돌리기 200 + rel 칩 2↔3 · 잠긴 집 4버튼 disabled ·
이력 탭 행 액션 0 + STAFF 는 `all` 강제 차단 · 실패 띠 + 재시도 + 확인함 · 지금 수집 ·
1440/991 두 폭(2단↔1단, sticky, 목록 미잘림). `id="wb-` 중복 0, 잔여 백드롭 0,
nav 뱃지==스트립==탭==목록 줄수.

**치명-2(모달이 백드롭 아래) 브라우저 재현·해소 확인**: 수정 전 `Element not interactable`,
`pane.style.position='static'` 로 격리하면 정상 → 원인 확정. 수정본에서 create·confirm·cancel
모달 전부 `clickable:true`, 1440 에서 발주확인·취소 POST 실성사.

**H2 브라우저 재현·해소 확인**: 형제 2건이 확인 완료된 3건 묶음에서 수정 전 `data-count="1"`
(벌크 모달 "1건" vs pane "3건"), 수정 후 `data-count="3"`.

### QA 가 잡은 미해결 1건 — 수정 완료

**[FAIL #2] 뒤로가기가 전체 리로드가 된다.** 원인은 워크벤치가 아니라 **전역 nav 런타임**이었다:
`static/js/global-nav-runtime.js` 의 popstate 폴백이 `st.gnav` 키가 없으면 무조건
`location.reload()` 를 한다. 워크벤치는 `{wbLinkId}` 를 push 하므로 남의 state 로 분류돼
부분 갱신 UI 가 전체 재요청으로 되돌아갔다(요청도 2번 나갔다). 계약이 지목한 통증 ②
(전체 리로드 제거)가 뒤로가기에서만 깨지는 자리였고, `nav.layout-global-nav` 가 있는
**모든 페이지**에 해당한다.

수정: `didSwapMain` 플래그 신설. 리로드는 **이 런타임이 실제로 `#main-content` 를 갈아 끼운 뒤**
원래 항목으로 돌아왔을 때만 옳다 — 한 번도 스왑한 적 없으면 DOM 은 서버가 준 그대로다.
브라우저 실증: 스왑 없는 페이지에서 `{wbLinkId}` state 로 뒤로가기 → 마커 생존(리로드 없음),
URL 정상 복귀. gnav 계약 테스트 6건 green.

## 리뷰 지적 처리 요약

| 지적 | 처리 |
|---|---|
| 치명-1 벌크 no-op | 이미 수정(대표 링크에서 주문번호 추출) + 회귀 테스트 |
| 치명-2 sticky stacking | sticky 를 `#wb-pane > .wb-detail` 로 이동, 브라우저 실증 |
| H-A 형제 가드 반쪽 | `_attach_household_counts` 같은 쿼리에서 `claim_blocking`·`canceled` 재계산 |
| H-B 깨진 수집분 | 서비스 층 `_broken_collection_guard` + 양방향 테스트 |
| H-C aria-current | 링크 포함 비교로 수정 |
| H-D / M2 뱃지 성능 | **전 직원 개방 전 TTFB 측정**을 승격 게이트로 등재(미측정) |
| M-1 문구 거짓 | title·목록 헤더 수정 |
| M-5 죽은 조회 | `_pane_context` 의 `sales_users` 제거 |
| M-6 pane STAFF 그물 | 프래그먼트 누출 테스트 추가 |
| M-7 fulfillment 게이트 | **기각** — 게이트 OFF 화면(`naver_triage.html:513`)이 그 라우트를 쓴다. 막으면 롤백 경로가 죽는다 |
| INV 인벤토리 | failopen 재생성(신규 broad except 1건) — pre_push_smoke 사각이라 안 했으면 CI red |
| M-2·M-3·M-4·L-1~L-5 | 미처리, 원장 등재(다음 세션 후보) |

## 미처리 지적 후속 처리 (2026-08-23, 사용자 지적으로 재개)

푸시 후 사용자가 "미처리한 이유"를 물었다. 정직하게 나누면 세 갈래였고, 앞의 둘은 내 잘못이다.

**1. 그냥 놓친 것 — `.wb-acts__why` CSS 0.** 계약 §3.3 이 "목업 문장 그대로"라 못박은
안내 문구 3종이 스타일 없이 맨 텍스트로 나갔다. 리뷰가 "CSS 없는 클래스 7종 중 실제 피해는
이거 하나"라고 콕 집어줬는데 지나쳤다. **원인은 분류 실수** — 치명·높음부터 쳐내고 "보통 이하"를
미뤘는데, 이건 등급은 낮아도 **목업 대비 눈에 보이는 차이가 나는 유일한 항목**이었다.
등급이 아니라 "사용자가 보게 되는가"로 갈랐어야 했다.
→ `.wb-acts`·`.wb-acts__why`(+`--locked` 변형)·`.wb-detail__head` 스타일 추가.

**2. 컨텍스트 압박으로 임의 축소.** 62% 를 넘기며 "치명·높음 → 검증 → 푸시"로 스스로 스코프를
좁혔다. 사용자는 "모든 배선 확인"을 요구했지 "치명만 고쳐라"라고 한 적이 없다.
→ 이번에 처리: **판정 3벌 통합**(아래) · L-2 죽은 이중 배선 제거 · 죽은 CSS 규칙 2개 제거.

**3. 근거 있는 보류(유지)**: M-2(방향이 안전 + v2부터의 동작, promotion 의미론 결정 필요) ·
M-3(이력→처리 이동에 필요한 경로, 계약 테스트가 이미 못박음, 표시 UI 는 별도 스펙) ·
M-4(발송 판정 단위 혼재 — 남김, 다음 세션) · L-1(어긋나는 방향이 과대 진술=안전) ·
L-3·L-4(브리틀하나 현재 green) · H-D(측정 없이 못 고친다 — 승격 게이트).

### 판정 3벌 → 1벌 (H1 의 뿌리 제거)

`locked` 가 서버·목록 템플릿·pane 에 각각, `place` 술어가 서버·템플릿에 각각 있었다.
리뷰가 "H1 이 정확히 이 갈라짐에서 나왔다"고 지적했는데 1차 처리에서는 **증상만**
고쳤다(병합 후 재계산). 이번에 구조를 고쳤다:

- `_attach_row_flags(groups)` 신설 — `_group_matches_filter` 를 그대로 불러
  `group["locked"]`(= claim 칩 술어) · `group["can_pick"]`(= place 칩 술어)을 싣는다.
- 호출 순서가 중요하다: `_mark_sibling_claims` → `_attach_household_counts` → `_attach_row_flags`.
  형제 클레임이 반영된 **뒤에** 판정해야 한다.
- 목록 템플릿은 이제 값을 읽기만 한다(`group.locked` · `group.can_pick`).
- 계약 테스트: 모든 집에서 `locked == _group_matches_filter(g,'claim')` ·
  `can_pick == _group_matches_filter(g,'place')`.

### 테스트 헬퍼 결함 발견 (부산물)

`test_naver_workbench_v3_population.py` 의 `_link` 가 `external_order_no=external_id[:-2]` 를
써서, 서로 다른 링크가 **같은 주문번호**를 갖고 한 집으로 합쳐졌다. 앞선 테스트들이
green 이었던 건 우연이고 **재려던 것과 다른 걸 재고 있었다.** 링크마다 고유 주문번호를
쓰도록 고쳤다(형제는 `order_no` 명시). 이 결함은 판정 통합 테스트가 `KeyError` 로 드러냈다.

## 사용자 지적 — 좌우 패널 밸런스 (2026-08-23, 스테이징 실화면)

사용자가 스테이징 1440 폭 스크린샷으로 지적. **왼쪽 목록이 잘린다**:
- 제품명이 중간에서 끊긴다(`라홈 로라 무몰딩 붙박이장 작은방 여닫이 푸쉬타입 180` 에서 절단)
- 배지가 줄바꿈돼 행 높이가 들쭉날쭉하다 — '안경필' 행은 `주문 만들기`·`발주확인 전`·
  `발송기한 2026-09-10` 이 한 줄에 못 들어가 `발주확인 먼저` 가 아래로 밀렸다
  (다른 행은 2줄인데 이 행만 3줄)

반대로 **오른쪽 상세는 여백이 남는다** — 상품주문 표의 금액 열이 화면 끝까지 밀려 헐겁다.

원인: `static/css/admin/naver-workbench.css:161`
`.wb-split { grid-template-columns: minmax(320px, 400px) 1fr; }` — 좌측 상한 400px 고정이라
넓은 화면에서 남는 폭을 전부 오른쪽이 먹는다.

수정 방향(다음 세션): 좌측 상한 상향 또는 비율 기반 · 상세 표 `max-width` 로 여백 회수 ·
행 배지 줄 `flex-wrap`+`row-gap` 정돈. **지킬 것**: 991.98px 1단 전환,
`#wb-pane > .wb-detail` sticky(루트로 올리면 모달이 백드롭 아래로 죽는다),
목록 `max-height` 재도입 금지.

**부수 확인(좋은 신호)**: 같은 스크린샷에서 nav 뱃지 `네이버 수집 58` == 목록 헤더
`처리할 집 … 58집` 으로 일치한다 — 67 vs 45 불일치가 실화면에서 해소된 것이 확인됐다.
`확인 완료 — 큐에서 빼기` 도 모든 집에 노출된다.

## 좌우 밸런스 수정 + 남은 지적 처리 (2026-08-23, 이어지는 세션)

### 선행 확인
`a7d82df8` CI **4/4 green** (FOMS CI `32632127707` 이 마지막으로 붙었다 — 앞 세션이 진행 중으로 두고 나온 그 런).

### 좌우 패널 밸런스 (사용자 지적 처리)
로컬 시드(10집, 계정 `qa_v3`)로 1440/1280/991 실측. **행 높이가 세 폭 모두 93px 로 균일**해졌다
(수정 전 1440 에서 93px·116px 혼재).

| 폭 | 좌:우 | 행 높이 | 대조표 폭 | 가로 넘침 |
|---|---|---|---|---|
| 1440 | 510 : 894 (전 400 : 1004) | 93 | 860 | 없음 |
| 1280 | 452 : 792 | 93 | 760 | 없음 |
| 991 | 1단 967 | 93 | 860 | 없음 |

- `.wb-split` 좌측 상한 `400px` → `36%`, 우측 `1fr` → `minmax(0, 1fr)`(긴 옵션 원문이 격자를 밀지 않게).
  하한 360px 유지. 비율 후보 34%/36%/38% 를 실측해서 골랐다 — 34% 는 1280 에서 배지 줄이
  19px 모자라 한 행만 2줄이 됐다.
- **접수시각을 배지 줄 → 이름 줄 오른쪽으로 옮겼다.** 이름 줄은 오른쪽이 통째로 비어 있었고,
  배지 줄에서 날짜가 먹던 폭이 배지 하나를 아래로 밀던 실제 원인이었다.
- `.wb-cmp { max-width: 860px }` — 넓은 화면에서 금액 열이 화면 끝까지 밀리던 것 회수.
- 제품명 `title` 속성(잘려도 원문 확인) + 이름 줄 ellipsis(긴 이름이 날짜를 밀어내지 않게).
- 폭 전수 실측(로컬 시드 10집): 1920 `683:1201` · 1600 `567:997` · 1440 `510:894` ·
  1280 `452:792` — **여기까지 행 높이 전부 93px**. 1200 `423:741` · 1024 `360:628` 에서는
  배지가 가장 많은 한 행이 다시 2줄(116px)이 된다. 이 화면은 데스크톱 업무용이고
  1단 전환점이 991.98 이라 그 사이 구간은 남긴다 — 더 좁히려면 배지 자체를 줄여야 하는데
  그건 계약 §3.3(글자 라벨 3층)과 부딪힌다.
- 지킨 것: 991.98 1단 전환 · sticky 는 `#wb-pane > .wb-detail` 그대로(발주확인 모달 열고
  `elementFromPoint` 로 모달이 백드롭 위인지 실측) · 목록 `max-height` 재도입 안 함 · `?v` 핀 `20260823b→c`.

### 미처리 지적 4건 처리 (M-4·M-3·M-2·L-1)

| ID | 처리 | 자리 |
|---|---|---|
| M-4 | 발송 판정을 **집 단위**로. `_group_queue` 에 `dispatched`(전부)·`dispatched_any`(하나라도)·`dispatched_count` 추가, pane 이 링크 표식 대신 이 값을 읽는다. 취소는 `dispatched_any` 로 닫는다(서버 `cancel_order` 가 형제 중 발송분이 있으면 집 전체를 거절한다). 부분 발송 집에 "N건 중 M건이 이미 발송처리 — 취소는 열리지 않습니다" 안내 신설 | `naver_ingest.py:_dispatched_count`·pane 상단 set 블록 |
| M-3 | 목록 밖 집을 열면 pane 이 "지금 왼쪽 목록에 없는 집입니다"를 말한다. **경로는 막지 않는다**(이력 탭 `처리 탭에서 열기` 가 그 길이다). 판정은 모집단 술어 재구현이 아니라 **실제 목록 멤버십**(`_selected_offlist`) — 프래그먼트는 목록을 모르므로 판정하지 않는다(행을 눌러야 도달 = 정의상 목록 안) | `naver_ingest.py:_selected_offlist` |
| M-2 | 주문 만들기 모달이 **서버가 옮길 건수**를 말한다. `promotion.is_promotable` / `PROMOTABLE_SYNC_STATUSES` 를 술어 SSOT 로 신설하고 `_group_siblings` 쿼리와 화면이 나눠 쓴다. 남는 형제가 있으면 "나머지 N건은 이미 주문이 있어 옮기지 않습니다" 한 줄 | `promotion.py` + pane 생성 모달 |
| L-1 | `_group_queue` 가 `group_key` 직접 호출 + 자체 폴백을 쓰던 것을 워커와 같은 `household_key` 한 벌로. 화면에만 없던 두 번째 폴백(키가 통째로 비면 링크 단독)이 이제 함께 적용된다 | `naver_ingest.py:_group_queue` |

회귀 테스트 신설: `tests/services/integrations/test_naver_workbench_v3_followup.py` **8건**
(부분 발송 어느 형제로 열어도 취소 닫힘 / 남은 발송은 열림 / 전부 발송이면 완료 배지 ·
목록 밖 경고 유무 · 프래그먼트는 판정 안 함 · 승격 건수 재진술 2종 · 빈 원본 2건 = 2집).

**테스트를 쓰다 잡은 것**: 모달 조각을 `</div></div></div>` 로 자르면 옆 모달이 딸려 온다
(발송 모달 설명문의 "발송처리 완료"·건수 문장이 주문 만들기 단언에 섞였다). `_modal_of` 로
다음 모달 시작 전까지만 자른다.

### L-3 · L-4 — 계약 테스트 견고화 (위임 → 직접 재검증)

- 신규 `tests/services/integrations/_markup.py` — `open_tag`(id 로 여는 태그를 통째로,
  따옴표 밖 `>` 까지) · `has_attribute`(속성 **값** 안 글자에 안 속는다) · `is_disabled`.
  순수 문자열 함수만 둔다(`db` import 금지 — conftest 가드보다 먼저 로드돼도 안전하게).
- L-3: `'id="wb-dispatch" disabled' in body` 류 단언을 4개 파일에서 파싱으로 교체.
  **의미가 세졌다**: 옛 부정 단언은 버튼이 통째로 사라져도 통과하는 거짓 green 이었는데,
  `is_disabled` 는 요소가 없으면 AssertionError 로 터진다.
- L-4: `assert "네이버 주문" not in html` 전역 검사를 `_menu_labels()`(셸 헤더 + 메인 메뉴
  nav 안의 `.nav-link`/`.dropdown-item` 라벨만)로 좁혔다. 라벨이 0개면 조용히 green 이 되므로
  있어야 할 이름(`네이버 수집`) 단언을 카나리아로 함께 둔다.
- 템플릿의 "속성 순서(class → id → disabled)를 지켜라" 주석은 사문이 되어 제거.
- **직접 재검증**: `pytest tests/services/integrations/ -q` → `490 passed in 126.51s`.
  위임자가 보고한 수치와 일치.

## CEO 검수 2판정 반영 (2026-08-23)

두 렌즈로 나눠 검수했다. **불가역 위험 렌즈** = 조건부(높음 3건), **사용자 가치 렌즈** =
부분 해소(상 2건·중 3건·하 2건). 두 렌즈가 독립적으로 같은 자리를 지목한 것 1건(목록 밖
경고가 첫 액션에서 증발) — 그 자리를 제일 먼저 고쳤다.

| 지적 | 판정 | 처리 |
|---|---|---|
| **높음-1** 발송 모달이 집 전체 수를 재진술(서버 todo 는 이미 나간 형제를 뺀다). M-4 가 부분 발송을 화면에 드러내면서 **새로 생긴** 모순 | 사실 | 모달 건수 = `member_count - dispatched_count` + "이미 발송처리된 N건은 다시 보내지 않습니다" |
| **높음-2** `_selected_offlist` 가 **링크** 멤버십으로 판정 — 큐 모집단 밖 형제(PENDING_REVIEW 옵션 건)를 열면 집이 왼쪽에 멀쩡히 있는데(aria-current 하이라이트까지) "목록에 없는 집"이라고 말한다 | 사실 | 판정을 집 단위로(`household.link_ids ∩ visible`), 회귀 테스트 신설 |
| **높음-3 / 중** 목록 밖 경고가 **발주확인 성공 직후 증발**(`submitConfirm` → `loadPane` → 프래그먼트는 `visible=None`). 경고가 가장 필요한 시점에 없다 | 사실 | 문구를 항상 렌더하고 `hidden` 으로 접는다. 판정 주체는 서버 그대로, JS 가 조각 교체 너머로 값만 옮긴다(`paneOfflist`·`applyOfflistFlag`). 행 클릭은 false(정의상 목록 안) |
| **상** `.wb-cmp{max-width:860px}` 가 **이력 탭 7열 표까지** 조인다 — M-3 이 "이력에서 처리하러 가는 길"이라고 지킨 그 표 | 사실(확인: `naver_workbench.html:407` 이 `wb-cmp wb-hist`) | 상한을 `#wb-pane .wb-cmp` 로 한정 |
| **상** 주문 만들기 POST 가 대표 링크로 나간다 — 대표가 이미 주문을 가진 집에서 승격 대상 형제를 열면 "N건 옮깁니다" 뒤 **0건** 이동(멱등 반환) | 사실 | `promotable_lead_id` 신설(승격 대상 중 최고금액)로 POST, `can_create` 에 `promotable_count > 0` 추가(모달 "0건" 렌더도 함께 사라짐) |
| **중** 제품명 줄만 **16px**(Bootstrap 본문 상속) — 고객명 13.5px 보다 크고, 잘림의 절반이 여기서 왔다 | 사실(브라우저 실측 `line2:16px` / `name:13.5px`) | `font-size: 12px` — 같은 폭에 글자 33% 더 들어간다 |
| **중** 부분 발송 안내가 `can_dispatch` 를 안 봐서 **없는 동작을 약속**(발주확인이 남았으면 버튼이 잠겨 있다) | 사실 | 문장을 `can_dispatch` 로 가르고 길이도 줄였다 |
| **하** `_claim_blocked_group_keys` 만 옛 어휘(`mapping.group_key`) — 빈 키 집에서 `group["key"]` 와 어긋난다(지금은 `_attach_household_counts` 가 메운다) | 사실 | `household_key` 로 통일 — L-1 의 "폴백 한 벌" 목표 달성 |
| **하** 잠김 + 부분 발송이 겹치면 취소 버튼이 사라진 이유가 **어디에도 없다** | 사실 | 잠금 안내에 취소 항목 추가 |
| **4-1** `발주확인 전` 배지가 같은 줄 `.wb-can`("발주확인 먼저")과 같은 말 | 사실 | `row_kind != 'wait'` 일 때만(주문 있는 집은 글자 라벨이 "규격 입력할 차례"라 정보가 사라지지 않는다) |
| **4-2** 접수시각 19자(초·연도) | 사실 | 목록만 `%m-%d %H:%M`(상세·이력 표기는 그대로) |
| **보통(선재)** `_group_queue` 가 `PAGE_SIZE` 로 말없이 자른다 — `work_truncated` 는 링크 250 상한만 본다 | 사실, **미처리** | 전 직원 개방 전 승격 게이트에 등재(뱃지 TTFB 와 같은 묶음). 지금 58집이라 안 터진다 |
| **하** 태블릿에서 `title` 이 안 뜬다(잠금 사유가 다른 표면 없음) | 사실, **미처리** | 이번 변경이 만든 문제는 아니나 의존을 하나 더 얹었다 — 별도 스펙 |

**두 렌즈가 함께 확인한 정상(중복 수정 금지)**: 서버 방어선 6종 무손상 ·
취소 게이팅 `dispatched_any` 는 서버 `cancel_order` 와 정확히 일치(좁아지는 방향) ·
L-1 모집단 부작용 없음 · sticky stacking 재발 없음 · 계약 §0 여섯 규칙 유지 ·
접수시각을 이름 줄로 옮긴 결정은 **오히려 낫다**(날짜가 세로 열을 이뤄 접수순 훑기가 쉬워졌다).

회귀 테스트 5건 추가(발송·발주확인 모달 건수, 승격 0건 버튼 차단, 승격 대상으로 POST,
집 단위 목록 밖 판정) → followup 파일 **13건**.

## 스테이징 실데이터 눈 확인 (2026-08-24, claude_master · 코호트 임시 38,58 → **38 원복 완료**)

58집·상품주문 195건. 불가역 버튼은 누르지 않았다(모달 열기까지만). 네이버 실호출 0건.

| 항목 | 결과 |
|---|---|
| 칩 == 목록 == 탭 == nav 뱃지 | 전체 58 == 58행 == 스트립 58집 == 뱃지 58 |
| 행 클릭 | `fetch` **1회**(프래그먼트), 문서 요청 0, 주소 갱신 |
| 뒤로가기 | JS 카나리아 생존 = 전체 리로드 아님, `aria-current` 이전 행 복원 |
| 잠긴 행 | 6행 == 취소·반품 칩 6집(이름 취소선 + "손대지 않음") |
| 전부 선택 | 33개 == 발주확인 전 칩 33집(잠김·확인완료 25개 disabled) |
| 이력 탭 | 51행, 표 폭 **1256px** — `.wb-cmp` 상한이 안 걸린다(CEO 상 지적의 회귀 없음 실증) |
| 제품명 잘림 | **58행 중 0행**(12px 전환 효과) |

**남아 있던 것 — 행 높이 55/58만 균일.** 3행이 116~122px 로, CEO 사용자 가치 렌즈가 예측한
"주문 만든 뒤" 조합(묶음·규격 입력·발주확인 전·발송기한·주문 #N)이 실데이터에 실제로 있었다.
로컬 시드에는 그 조합이 없어 안 잡혔다 — **시드로는 못 보는 것을 실데이터가 보여준 자리**다.

스테이징 DOM 에 세 손질을 주입해 실측(`{"88": 58}` — 58행 전부 같은 높이) 후 코드에 반영:
1. 목록 배지 패딩 `6px 10px → 4px 7px`(정보를 지우지 않고 폭만 회수)
2. `규격 입력` 배지 제거 — 같은 줄 오른쪽 `.wb-can` 이 이미 "규격 입력할 차례"(`발주확인 전` 과 같은 손질)
3. 발송기한 연도 제거(목록만, 상세·모달은 전체 날짜)

**벌크 재진술도 함께 고쳤다**(CEO 보통): 스테이징이 "33집 · 상품주문 119건" 이라고 말하는데
서버 `confirm_place_order` 는 이미 확인된 형제를 뺀다. `_attach_household_counts` 가 같은
쿼리에서 발주확인 남은 수를 세도록 해 `data-count` 를 그 값으로(조회 증가 0). 단건 모달만
고치면 한 화면에서 두 모달이 다른 규칙을 쓰게 된다.

부산물: `test_place_tab_shows_shipping_due_so_urgency_is_visible` 이 전체 날짜를 문서 전역에서
찾고 있었다 — 줄 단위로 좁히고 "연도 없음"까지 단언하도록 고쳤다(L-4 와 같은 부류).

## CI red 1건 — 없는 order_id (2026-08-24)

**FOMS CI 가 두 커밋(45077645·fbe13363) 모두 red.** 나머지 3개(Harness·PG Lane·perf-gate)는 green.
원인은 **내가 새로 쓴 테스트 3개**가 `order_id = 999999` 처럼 존재하지 않는 주문 id 를 꽂은 것:
로컬 SQLite 는 FK 를 강제하지 않아 green 인데 CI 는 강제해서 `FOREIGN KEY constraint failed`.
`_order()` 헬퍼로 실제 `Order` 를 만들어 붙이도록 고쳤고 함정을 docstring 에 남겼다.
로컬에서 CI 와 같은 환경(`DATABASE_URL=sqlite:///:memory:`)으로 재확인 — 16 passed.
**로컬 재현은 안 됐다**(같은 URL 로도 FK 미강제) — pre_push_smoke·로컬 전수로는 못 잡는 부류다.

## 사용자 지적 — 오른쪽 여백 (2026-08-24)

`#wb-pane .wb-cmp { max-width: 860px }` 가 넓은 화면에서 카드 오른쪽을 통째로 죽였다.
"화면 비율에 따라 꽉 차게, flexible 하게" 요구 — **상한을 빼고 숫자 열을 고정**하는 방식으로 바꿨다.
남는 폭은 제품·옵션 원문(사람이 읽고 규격을 채우는 값)이 먹고, 수량 92px·금액 128px 은
자릿수만큼만 차지한다. 실측: 1920 카드 1201 / 표 1169, 1440 카드 894 / 표 862 —
오른쪽 죽은 공간은 카드 패딩 16px 뿐. 이력 탭 표는 원래대로 전체 폭.

## 스테이징 최종 재확인 (2026-08-24, `9bc59846` 배포본)

실데이터 58집·1440 폭, claude_master:
- **행 높이 `{"88": 58}`** — 58행 전부 같다(수정 전 93·116·122 혼재).
- **제품명 잘림 0/58**.
- 상세 표 862px / 카드 894px — 오른쪽 죽은 공간은 카드 패딩뿐(사용자 지적 해소).

**코호트 38 원복 확인 완료.** 불가역 버튼 미클릭·네이버 실호출 0건.

## 캡 결함 재발 — 내가 만든 것 (2026-08-24)

선재 결함 ①(캡 침묵)을 고치면서 **새 결함을 만들었다.** 사용자가 스테이징 실화면 HTML 을
붙여 줘서 잡혔다.

증상: `집이 한 화면에 다 들어가지 않아 58집만 보입니다` 가 뜨는데 바로 위 탭·스트립도
`58집` 이다. "58집만 보입니다" 옆에 총량도 58집 — 사람 눈에는 모순이고, 무엇이 빠졌는지
알 길이 없다.

원인 둘:
1. **캡을 원천별로 걸었다.** 큐 묶음이 `PAGE_SIZE`(50)를 넘어 잘리며 띠가 켜졌는데,
   그 뒤 '발주확인 전' 집 8개가 병합돼 화면은 58줄이 됐다. 띠는 켜졌는데 줄수는 캡보다 크다.
2. **상한 50 이 실제 운영 물량(58집)보다 작았다.** 상한은 "평소엔 안 닿는 안전장치" 여야
   하는데 상시 발동했다 — 늘 켜진 경고는 아무도 안 읽고, 정작 진짜로 잘릴 때 못 알아챈다.

수정:
- 캡을 **병합 뒤 한 곳**(`WORK_GROUP_LIMIT`)으로. 원천별 캡 제거, `_place_groups` 도 같은 상한.
- 50 → **200**. 발동 시 `logger.warning`.
- 띠 문구를 "목록이 상한에 닿아 **일부 집이 안 보입니다**" 로 — 보이는 줄수를 재진술하면
  탭 숫자와 같아져 또 모순이 된다.
- 회귀 2건: 상한을 3으로 낮춰 캡 발동 + 모순 문구 부재 확인 / **12집에서 캡 경고가 안 뜨는지**.

부산물 실수: 캡 SSOT 를 바꾸며 `PAGE_SIZE` 몽키패치 3곳을 일괄 치환했는데 그중 하나는
**이력 탭 페이징**이라 되돌렸다. 두 상수의 역할 차이를 주석으로 못박았다.

## CI 결과 (2026-08-24)
- `9bc59846` **4/4 green** — FK 수정(없는 order_id) 확인.
- `63889608`(docs) PG Lane·Harness green, FOMS CI 진행 중.

**남은 상한 하나(승격 게이트에 묶는다)**: `QUEUE_LINK_FETCH_LIMIT`(링크 250건)이 이제
실질 상한이다 — 실데이터가 집당 링크 3.4건이라 **집 약 73개**에서 먼저 닿는다. 닿으면
`truncated` 가 서서 띠는 정직하게 뜨지만, 물량이 늘면 다시 상시 발동이 된다. 올리는 것은
링크당 JSONB 파싱 비용을 늘리므로 **뱃지 TTFB 측정과 같은 묶음**에서 함께 정해야 한다.

## 세션 종료 상태 (2026-08-24)

deploy HEAD = `2ef90874`. **CI 4/4 green** (FOMS CI · PG Lane · Harness · perf-gate).
`9bc59846` 도 4/4 green, `63889608`(docs)은 실행된 3개 green(perf-gate 미실행).

푸시 5건: `45077645`(밸런스+리뷰 6건+CEO 2판정) → `fbe13363`(실데이터 행 높이+벌크 건수)
→ `9bc59846`(표 꽉 채우기+FK CI red 수정+선재 2건) → `63889608`(기록) → `2ef90874`(캡 결함).

**다음 세션이 할 일 (승격 게이트 — 전 직원 개방 전 필수)**
1. nav 뱃지 TTFB 측정 — COUNT 1회 → `_work_groups` 전체(조회 4~6회 + 스냅샷 JSONB 파싱
   수백 건, 30초 전역 캐시). 측정 없이 코호트를 넓히지 마라. 지금은 upperkill 단독이라 무해.
2. `QUEUE_LINK_FETCH_LIMIT`(링크 250 = 실데이터 기준 집 약 73개) 상향 여부 — 1번과 같은 묶음.
3. 터치 기기 잠금사유 표면 — `발주확인 완료` 배지로 부분 해소했으나 체크박스·나머지 버튼
   `title` 은 여전히 hover 전용. disabled 버튼은 click 이 안 나와 `pointer-events` 조작 +
   위임이 필요하다(별도 스펙).

**운영 승격은 별건이다** — production 에 네이버 코드 0줄, 미승격 커밋 123개·마이그레이션 8개.
v3 커밋만 cherry-pick 하면 깨진다. 전체 승격은 별도 스펙·원장 + 사용자 명시 요청 시에만.
