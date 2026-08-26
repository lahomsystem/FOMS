# 재결제 정리 R-3 진행 원장 (2026-08-25)

> 설계: `docs/specs/2026-08-25-naver-repay-reconcile_SPEC.md` (§2.5 개정 — 네이버 직접취소 제외)
> 목업: `docs/design/mockups/naver-repay-reconcile.html` (2판)
> 선행: R-1 `7daaa4fd` · R-2 `7ac7abb8` · nav 표식 `6d14abf8` (전부 deploy CI green)
> 작업 트리: `c:\tmp\nvfix` (브랜치 `tmp/naver-fix-20260825`)

## 착수 전 확정한 것 (사용자 판단 1건)

**질문**: 정리 카드에서 `취소 처리`(옛 주문 휴지통)를 고르면 새 집을 그 주문에 **붙이기도**
같이 하는가? 목업 §2 1번 칸("항상 실행")과 2-(b) 칸("새 집으로 주문을 새로 만든다")이
서로 어긋났다.

**답(2026-08-25 사용자 확정)**: **붙이지 않는다.** 취소 처리만 하고 새 집은 큐에 그대로
남긴다 — 사람이 `주문 만들기` 를 누른다(D-2 와 같은 자리).

> 근거: 붙여 놓고 그 주문을 접으면 새 집이 **휴지통에 든 주문**에 묶인다. 그러면
> `주문 만들기` 가 막히고(이미 `order_id` 있음) 상세는 삭제된 주문을 가리켜, 사람이
> `되돌리기` 를 한 번 더 눌러야 빠져나온다. 되돌릴 수 있는 설계의 뜻이 사라진다.

## 무엇을 만들었나

| # | 조각 | 위치 | 상태 |
|---|---|---|---|
| T1 | 정리 서비스(계획 산출 · 두 갈래 실행) | `foms/services/integrations/naver_commerce/repay_reconcile.py` (신규) | **DONE** |
| T2 | 후보 사실에 `naver_alive_rows` 추가(살아 있는 옛 집) | `order_candidates.py` | **DONE** |
| T3 | mutation 라우트 `POST /admin/naver-ingest/<link_id>/reconcile` | `foms/web/admin/naver_ingest.py` | **DONE** |
| T4 | 계약 4종 등재 + 인벤토리 2종 재생성 | manifest 2 · `audit_message_display.py` · 스캐너 2 | **DONE** |
| T5 | 정리 계획 카드(화면) | `naver_workbench_pane.html` · `naver-workbench.css` · `naver-workbench.js` · `?v=20260825e` | **DONE** |
| T6 | 서비스 단위 테스트 22건 | `tests/services/integrations/test_naver_repay_reconcile.py` | **DONE** |
| T7 | 라우트 계약 테스트 10건 | `tests/services/integrations/test_naver_repay_reconcile_route.py` | **DONE** |
| T8 | 화면 계약 테스트 5건 | `tests/services/integrations/test_naver_repay_reconcile_card.py` | **DONE** |
| T9 | deploy 푸시 + CI | `231b3ad3` | **DONE** |
| T10 | 스테이징 실화면 확인 | — | **PENDING** |

## 못박은 규칙 (테스트가 지킨다)

- **네이버로 나가는 호출 0.** 옛 결제는 상태만 본다. 살아 있으면 판매자센터 링크로 안내만.
- **예약금 자동 반영 없음.** 라우트가 `structured_data['payment']['deposit']` 을 쓰지 않는다.
  화면이 "넣을 금액"을 말하고 입력은 사람이 한다 — 재결제는 **바꾸고**, 추가결제는 **더한다**.
- **DISCARD 는 붙이지 않는다.** 실행 뒤에도 링크 `order_id is None` · `sync_status COLLECTED`.
- **취소 처리는 soft delete.** 행은 남고 `deleted_at` 만 찍힌다(휴지통 복구).
- **접수(RECEIVED) 단계에서만** 취소 처리가 열린다 — 화면뿐 아니라 **서버도 거절**한다.
  판정 상수는 유령 주문 띠(R-2)와 같은 `ghost_orders.DISCARDABLE_STATUSES` 하나다.
- **후보 목록 밖 주문은 거절.** 이 라우트가 범용 삭제·연결 경로가 되면 안 된다.
- **원자성**: 커밋 1회. 실패하면 붙이기도 ERP 처리도 미반영.

## 화면 동선

후보 표의 `추가결제로 정리` / `재결제로 정리` 버튼은 **바로 붙이지 않는다** — 정리 계획
카드를 연다(1 붙이기 · 2 갈래 라디오 · i 네이버 상태). `정리 실행` 뒤에는 새로고침 대신
카드 안에 결과를 쓴다 — **예약금에 넣을 금액**을 사람이 읽고 옮겨 적어야 하므로 그 숫자가
화면에서 사라지면 안 된다. `닫기` 를 누를 때 새로고침한다.

레거시 트리아지 화면(`naver_triage.html`, 게이트 off 경로)의 `붙이기` 버튼은 그대로 둔다 —
정리 카드는 워크벤치 전용이고, 게이트를 끄는 것이 이 기능의 롤백 경로다.

## 검증 기록

| 항목 | 명령 | 결과 |
|---|---|---|
| import | `python -c "import app; print('APP_OK')"` | `APP_OK` |
| 서비스 테스트 | `pytest tests/services/integrations/test_naver_repay_reconcile.py -q` | `22 passed in 4.55s` |
| 라우트 테스트 | `pytest tests/services/integrations/test_naver_repay_reconcile_route.py -q` | `10 passed in 7.28s` |
| 화면 테스트 | `pytest tests/services/integrations/test_naver_repay_reconcile_card.py -q` | `5 passed in 2.94s` |
| 통합 전량 | `pytest tests/services/integrations -q` | `650 passed in 368.34s` |
| smoke | `powershell -File scripts/ops/pre_push_smoke.ps1` | `=== PRE-PUSH SMOKE PASSED ===` (exit 0) |
| CI | `gh run list --branch deploy` (전 워크플로 나열) | **4/4 green** — perf-gate · FOMS PostgreSQL Lane · Harness CI · FOMS CI (`231b3ad3`) |

## 곁가지로 확인한 것 — `지금 수집` 이 즉시 안 되는 이유 (2026-08-25 조사)

R-3 밖이지만 같은 화면 질문이라 여기 남긴다. **웹은 큐에 넣기만 하고 화면은 아무것도
기다리지 않는다.**

1. `static/js/admin/naver-workbench.js:1362` `submitRunNow` — POST 뒤 안내 문구만 바꾼다.
   폴링도 `softRefresh()` 도 없다("잠시 뒤 새로고침하면…" 문구가 구조를 자백한다).
   같은 파일에 폴링 배선이 이미 3종 있는데(단건 2s/25s · 벌크 3s/90s · 재시도 15s 1회)
   run-now 만 안 쓴다.
2. `foms/web/admin/naver_ingest.py:3009` — `enqueue` 만 한다. 네이버 HTTP 는 WORKER 단일
   출구 계약(IP 3슬롯)이라 web 동기 호출은 **의도적으로 없다**.
3. `watermark.py:32` `END_SAFETY_MARGIN = 1분` — 조회 창 끝이 항상 1분 과거다.
   **방금 결제된 주문은 지금 눌러도 창 밖**이다.
4. 워커는 `rq worker default` 동시성 1. 앞선 job 이 있으면 그 뒤에서 기다린다.
   큐는 붙는데 워커가 죽어 있어도 라우트는 200 을 준다(생존 확인 없음).

고치려면: run-now 응답에 워터마크 지문을 실어 폴링(기존 `fulfillment-state` 급 GET 하나) +
`get_rq_runtime_status()` 로 워커 생존 확인. 안전여유 축소는 워터마크 전진 없는 조회 전용
모드일 때만 — 지금처럼 `advance` 하면 경계 주문이 영구 유실된다(그게 60초를 둔 이유다).

### 2026-08-26 — 위 진단대로 고쳤다 (`확인 완료` 무새로고침과 한 묶음)

| 조각 | 무엇 | 위치 |
|---|---|---|
| 지문 | `_watermark_rev` — `last_run_at\|last_success_to\|last_error\|last_summary` 의 sha1 16자. `hash()` 는 `PYTHONHASHSEED` 로 프로세스마다 달라 web·워커가 다른 값을 본다 | `naver_ingest.py` |
| 폴링 자리 | `GET /admin/naver-ingest/run-state` — 읽기 전용이라 mutation 계약 4종 대상이 아니다. 권한은 run-now 와 같은 ADMIN | 〃 |
| 워커 게이트 | **큐에 닿는데 워커가 0대인 경우만** enqueue 없이 503. `disabled`·`unreachable` 은 기존 503 경로가 이미 잡는다 — 무조건 막으면 REDIS 미설정 계약이 red 가 된다 | 〃 |
| 화면 | `watchRun` 3초/90초 폴링. 지문이 뒤집히면 `softRefresh()` **먼저**, 그 다음 문구(갱신이 문구를 지운다). 토큰·타이머는 단건·벌크와 **따로** | `naver-workbench.js` |
| 확인 완료 | 통째 이동 제거 → 선택만 놓고 `softRefresh()`. 갱신이 안 되는 응답이면 예전 경로로 폴백 | 〃 |
| 교체 손실 복구 | `captureFind`/`restoreFind` + `scrollTo` — 서버는 사용자가 무엇을 쳤는지 모르고, 집 하나가 빠지면 문서가 짧아져 스크롤이 위로 당겨진다. `softRefresh` 한 곳에서 고쳐 기존 갱신 경로 전부가 같이 좋아진다 | 〃 |

**남은 한계**: 워커가 한 건도 못 가져와 워터마크를 아예 안 건드리는 실행이 있다면 지문이
안 움직여 폴링이 마감까지 간다(그 자리는 "아직 처리 중입니다" 문구가 맡는다).
워터마크 60초 안전여유는 **손대지 않았다** — 줄이려면 전진 없는 조회 전용 모드가 먼저다.

## 남은 것 (R-3 밖)

- **R-1·R-2·nav 표식·R-3 운영 승격** — 사용자 결정: 한 꾸러미로 올린다.
  오늘 승격분은 `099568a2` 까지(sticky·도크·쿠폰·계정 생성).
- 필드 인벤토리 §3 우선순위 3건: 취소·반품 사유 원문 · 발송처리 결과 시각/상태 ·
  부분취소 잔여(`remain*`). `docs/guides/NAVER_FIELD_INVENTORY.md`
