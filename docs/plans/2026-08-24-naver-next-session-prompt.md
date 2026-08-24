# 다음 세션 프롬프트 — 네이버 워크벤치 (2026-08-24 작성)

아래를 **그대로 복사해서** 새 세션 첫 프롬프트로 넣는다.

---

**C 네이버 워크벤치 — 불가역 3종 결과 즉시 반영 + 남은 승격 게이트.
작업 위치 `c:\tmp\foms-s-naver-ingest` (브랜치 `session/naver-ingest`)

원장 `docs/plans/2026-08-23-naver-workbench-v3-ledger.md` 의 맨 아래 세 절부터 읽어라:
"CI 결과" · "캡 결함 재발 — 내가 만든 것" · "세션 종료 상태".
계약 `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md` (§0 절대 규칙 6개가 판정 기준).

## 지금 상태
- deploy 에 v3 + 후속 6차까지 올라가 있고 **CI 4/4 green** 확인했다.
- 스테이징 실데이터 58집으로 눈 확인 끝: 행 높이 균일(88px), 제품명 잘림 0,
  칩==목록==탭==nav 뱃지, 행 클릭은 프래그먼트 1회, 뒤로가기 부분 갱신.
- 게이트는 upperkill 단독(`FOMS_NAVER_WORKBENCH_COHORT=38`). railway 링크 디렉토리는
  `/c/tmp/foms-devlink`(FOMS-DEV). 저장소 디렉토리는 FOMS-PRODUCTION 링크라 거기서 railway 금지.
- 스테이징을 claude_master 로 보려면 코호트를 잠시 `38,58` 로 넓히고 **반드시 38 로 원복**한다
  (실계정 upperkill 차용 금지 — `docs/guides/REAL_SERVER_TEST_ACCOUNT.md`).

## 1순위 — 불가역 3종의 결과를 **즉시** 화면에 반영

지금은 발주확인·발송처리·취소처리를 눌러도 **새로고침해야** 결과가 보인다. 사용자 지적이다.

### 지금 구조 (바꾸기 전에 이해할 것)
- 네이버 HTTP 는 **WORKER 에서만** 나간다(커머스API IP 3슬롯 계약). web 라우트는 큐에 넣고
  `{"queued": true}` 만 돌려준다 — `foms/web/admin/naver_ingest.py:naver_ingest_fulfillment`
  (`confirm`/`dispatch`), `naver_ingest_cancel`. **이 계약을 깨지 마라**(web 에서 직접 호출 금지).
- `enqueue_naver_fulfillment` 는 **bool 만** 돌려준다(`foms/services/jobs/queue.py`) — job id 가 없다.
- 워커(`foms/services/integrations/naver_commerce/fulfillment.py`)가 성공하면
  `triage_state.fulfillment` 에 `place_confirmed_at` / `dispatched_at` / `canceled_at` 을 찍고,
  실패하면 `last_error`·`last_error_at`·`last_error_action` 을 적는다(성공 시 지운다).
- 화면 쪽 현재 동작: 발주확인은 성공 응답 즉시 `loadPane()` + "잠시 뒤 반영됩니다" 문구
  (`static/js/admin/naver-workbench.js:submitConfirm`), 발송·취소·주문 만들기는 `location.reload()`.
  **둘 다 워커가 끝나기 전에 도는 갱신이라** 화면이 안 바뀐다.

### 방향(제안 — 설계는 네가 판단하고 근거를 남겨라)
- pane 프래그먼트(`GET /admin/naver-ingest/triage/pane?link_id=N`)가 이미 상세 SSOT 다.
  성공 응답 뒤 **상태가 뒤집힐 때까지 짧게 폴링**해서 pane 을 갈아 끼우는 쪽이 가장 작다.
- 무엇이 "뒤집힘"인지 서버가 말해 줘야 한다. 후보: ① 가벼운 상태 엔드포인트
  (`link_id` → `{place_confirmed, dispatched, canceled, last_error, last_error_at}`)
  ② enqueue 가 job id 를 돌려주고 job 상태를 묻는 경로. ①이 싸고 워커 계약을 안 건드린다.
- **실패도 즉시 보여야 한다.** 지금 실패는 `#wb-result` 띠(전체 렌더)에만 있어서 새로고침
  전에는 안 보인다. 폴링이 `last_error` 를 보면 pane 에 바로 사유를 띄울 수 있다.
- 폴링은 **끝이 있어야 한다**: 타임아웃(예 20~30초) 후에는 "네이버 응답이 늦습니다 — 잠시 뒤
  목록에서 확인하세요" 로 접고 폴링을 멈춘다. 무한 폴링 금지.
- 여러 집을 연속으로 조작할 때 **폴링이 겹치면 안 된다**. `paneToken` 과 같은 경합 차단이 필요하다
  (늦게 온 응답이 새 선택을 덮으면 화면과 조작 대상이 갈린다 — 이미 v3 에서 막아 둔 자리).
- 벌크(여러 집 발주확인)도 같은 문제다. 우선순위는 단건 3종 → 벌크.

### 지킬 것
- 계약 §0-2: **모달 재진술 건수 == 서버가 처리할 건수**. 지금 단건 모달은
  `place_pending_count`/`member_count - dispatched_count`/`promotable_count` 를 쓴다 — 건드리면 안 된다.
- pane 판정 SSOT 는 `_pane_context` 하나. 폴링용 엔드포인트를 만들더라도 **판정을 두 벌로 만들지 마라**
  (v3 리뷰 H1 이 그 갈라짐에서 나왔다).
- "목록에 없는 집" 경고는 JS 가 조각 교체 너머로 옮긴다(`paneOfflist`·`applyOfflistFlag`).
  폴링으로 pane 을 갈아 끼울 때도 그 값이 살아 있어야 한다.
- `#wb-pane` 루트에 `position:sticky` 를 다시 걸지 마라(모달이 백드롭 아래로 죽는다).
- 게이트 OFF 경로 `templates/admin/naver_triage.html` 은 롤백 경로 — 손대지 않는다.
- 폴링 주기는 nav 뱃지 부하와 겹친다. 뱃지는 이미 무겁다(아래 2번) — 폴링 엔드포인트는
  **가볍게**(집 하나, 조회 1회) 만들고 주기도 보수적으로.

### 검증
- 로컬은 Redis·RQ 워커가 없어 enqueue 라우트가 503 으로 정상 실패한다 —
  폴링의 **성공 경로는 로컬에서 못 본다**. 상태를 직접 써 넣어(테스트 픽스처처럼
  `triage_state.fulfillment` 갱신) 폴링이 화면을 바꾸는지 확인하는 방식이 현실적이다.
- 스테이징에서 **불가역 버튼을 누르지 마라**(실고객 주문이다). 즉시 반영 확인이 필요하면
  사용자에게 요청해 승인받고, 가상 주문(`CLAUDE-TEST-`)으로만.

## 2순위 — 승격 게이트 3건 (전 직원 개방 전 필수)
1. **nav 뱃지 TTFB 측정**. 뱃지가 COUNT 1회 → `_work_groups` 전체(조회 4~6회 + 스냅샷 JSONB
   파싱 수백 건, 30초 전역 캐시)로 무거워졌다. **측정 없이 코호트를 넓히지 마라.**
2. **`QUEUE_LINK_FETCH_LIMIT`(링크 250건) 상향 여부** — 실데이터가 집당 링크 3.4건이라
   **집 약 73개**에서 먼저 닿는다(지금 58집). 닿으면 "상한에 닿아 일부가 안 보입니다" 띠가
   상시 발동한다. 올리면 링크당 JSONB 파싱 비용이 는다 — 1번과 **같은 묶음에서** 정한다.
3. **터치 기기 잠금 사유** — `발주확인 완료` 배지로 부분 해소했지만 체크박스·나머지 버튼
   `title` 은 여전히 hover 전용이다. disabled 버튼은 click 이 안 나와
   `pointer-events` 조작 + 위임이 필요하다(별도 스펙).

## 3순위 — 운영 승격 (별건, 사용자 명시 요청 시에만)
production 에 네이버 코드가 **0줄**이고 미승격 커밋 123개·마이그레이션 8개가 쌓여 있다.
v3 커밋만 cherry-pick 하면 깨진다. 전체 승격은 별도 스펙·원장이 필요하다.

## 함정 (이번 세션에서 실제로 걸린 것만)
- **로컬 dev 서버가 옛 템플릿을 서빙한다.** 파일은 새 `?v` 핀인데 응답은 옛 핀이면
  포트 5000 에 stale 프로세스가 떠 있는 것이다. bash kill 로는 안 죽는다 —
  `powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*run.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"`
  로 정리하고 **한 개만** 다시 띄운다. 템플릿을 고쳤으면 서버를 재시작해야 반영된다.
- **없는 `order_id` 를 테스트에 꽂지 마라.** 로컬 SQLite 는 FK 를 강제하지 않아 green 인데
  CI 는 강제해 `FOREIGN KEY constraint failed` 로 터진다(이번에 2커밋 연속 red).
  `_order()` 헬퍼로 실제 `Order` 를 만들어 쓴다.
- **`test_rev_99.py::test_no_new_external_writers` 는 lineno 를 문다.** 함수를 파일 위쪽에
  추가하면 줄밀림만으로 red — `python tools/harness/order_mutation_writer_scan.py` 로 재생성해
  **커밋한다**. 반대로 `foms_failopen_inventory.json` 줄밀림 diff 는 게이트가 안 보므로 커밋하지 마라.
- **`var` 상수는 `init()` 위에 둬라.** defer 스크립트라 `init()` 이 즉시 돌고, `var` 는 선언만
  끌어올려지고 대입은 안 따라온다(글자 크기 단계 상수에서 실제로 막혔다).
- **AI_STATUS 는 승격할 때마다 충돌한다.** deploy(HEAD) 쪽 블록을 통째로 채택하고 내 줄만
  최신 문장으로 교체한다. 상단 40줄 4000자 예산(`tests/harness/test_hook_log_hygiene.py`).
- JS/CSS 고치면 `templates/admin/naver_workbench.html` 의 `?v` 핀 범프(현재 `20260824g`).
- 새 broad except 를 넣으면 `python tools/harness/failopen_scan.py` 재생성 필요(내용 변경 시).
- 테스트 임시 파일을 저장소 루트에 만들지 마라(`conftest` 보다 먼저 `db` import → 로컬 DB drop 사고).
- 로컬 dev DB QA 시드: `qa_v3` / `qa_v3_staff` (비번 `qa!2026`), 10집. PG 레인은 `/c/tmp/pglane5441`.

## 확정 규칙 (다시 묻지 마라)
- 상세는 항상 한 집만. 벌크 대상 ⊆ 화면 목록. 잠금·선택 판정 SSOT 는 서버 `_attach_row_flags`.
- 이력 탭 행에 액션·`data-link-id` 금지. STAFF 응답에 이력 데이터 0.
- 목록 캡은 **병합 뒤 한 곳**(`WORK_GROUP_LIMIT`)에서만. 원천별로 걸지 마라.
- 이 화면 글자 크기는 CSS 변수 `--wb-fs` 하나로 흐른다. 새 `font-size` 는 반드시
  `calc(Npx * var(--wb-fs, 1))` — 고정 px 를 넣으면 계약 테스트가 red 다(조절기 자신만 예외).

**진행 상황은 나한테 매우 상세히 물어봐.**
