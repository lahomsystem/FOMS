# 운영 반영 대기분 판정 (2026-09-09)

> 판정만 한다. 승격은 사용자가 묶음을 고른 뒤 별도 작업이다(production push 는 사용자 명시 요청 시에만).

## 기준

| | |
|---|---|
| origin/production | `93a2addf7` |
| origin/deploy | `103eb092e` — 판정 중 세 번 전진했다(`3c2253802` → `0e64a559a` → `103eb092e`) |
| 파일 차이 | 188개 · +18,083 / −776 (지시서의 "60개 · +3,880" 이후 AS 전달 배정·채널톡 경합 수정이 deploy 에 더 올라갔다) |
| 코드 파일 | 97개 (docs/·.claude/·.cursor/·README 류 제외) |
| 판정 방식 | 파일 diff 만 본다(cherry-pick 승격이라 SHA·제목은 양쪽 다 안 맞는다). 근거는 원장·AI_STATUS 원문. 충돌 여부는 production 기준 탐침 워크트리에서 `cherry-pick --no-commit` 으로 실측하고 결과는 버렸다 |
| 이 워크트리 | `session/s0908-102606` = `103eb092e` (origin/deploy 와 동일, 로컬 중복 커밋 1건은 rebase 로 흡수) |

## 제품 코드 묶음

### A. 로그인 전용 한도 + 실패 잠금(임계 8·15분) + 레이트리미터 폴백 관측

- 파일: `foms/services/rate_limit.py` · `foms/services/security/auth_rate/login_lockout.py`(신규) · `foms/web/auth/routes.py` · `foms/services/audit_message_display.py`(`LOGIN_LOCKED` 라벨 1줄) · `tests/domains/test_login_rate_limit_lockout.py`(신규). deploy 커밋 `40d25bb1b`, 5 파일 +840.
- **왜 운영에 없나: 일부러 보류했다.** 원장 `2026-09-07-foms-now-ratchet-ledger.md` T10 — "승격 범위는 AS 수정 1건만. 나머지 12건은 deploy 에만 있다(특히 로그인 한도·잠금은 실사용자 동작 변화라 별도 판단)". 후속표(세션 2 마감) — "T6 로그인 한도·잠금 승격 — 사용자 판단".
- AI_STATUS 의 "잔여는 production 승격 후(cron·dispatch)와 SENTRY_DSN 미설정" 은 **낡은 문장**이다. cron·dispatch(F-13)는 PR #303 으로 이미 운영에 있고, SENTRY_DSN(F-12)은 09-09 워커 관측 4건에서 "web 에만 있던 값을 복사, F-12 는 오판" 으로 정정됐다. 남은 것은 로그인 잠금뿐이다.
- 스테이징 검증: 원장 T8 — "잠금 8번째 429 · `LOGIN_LOCKED` 1건".
- cherry-pick 탐침: **CLEAN**.
- 되돌릴 수 있나: 코드 revert 만으로 끝난다. 실패 카운터·잠금은 limiter 저장소 키(TTL 15분)라 저절로 사라진다.
- 운영 데이터: DB 쓰기는 `LOGIN_LOCKED` 보안 로그 행 추가뿐. 저장소는 limiter 가 이미 쥔 것을 재사용한다(REDIS_URL 있으면 Redis 공유, 없으면 replica 별 메모리 — 운영 web 은 레이트리미터가 이미 Redis 경로).
- env: 필수 없음. 선택 4종 기본값 있음 — `FOMS_LOGIN_RATE_LIMIT`(`10 per minute;100 per hour`) · `FOMS_LOGIN_LOCKOUT_THRESHOLD`(8) · `FOMS_LOGIN_LOCKOUT_WINDOW_SECONDS`(900) · `FOMS_LOGIN_LOCKOUT_SECONDS`(900).
- 실사용자 영향(승격 판단의 핵심): 잠금 키는 (아이디, IP) 쌍. 잠긴 15분 동안은 **맞는 비밀번호를 넣어도 429** 다(`is_login_locked` 가 인증 앞에 있다). 관리자 해제 UI 는 없다 — `clear_login_failures` 는 로그인 성공 시에만 불린다. 사무실 NAT 처럼 IP 를 공유하면 한 사람의 8회 실패가 같은 아이디를 쓰는 옆 사람도 막는다(같은 아이디일 때만).

### B. 지난 날짜에도 그 날 발송 상황 표시(버튼은 오늘만)

- 파일: `foms/web/measurement/dashboard.py` · `templates/measurement/partials/naver_dispatch_strip.html` · `foms/web/admin/naver_ingest.py`(`is_today: True` 한 줄) · `tests/services/integrations/test_naver_bulk_dispatch_measurement_strip.py`. deploy 커밋 `bdff05c8b`(2026-09-01 12:52 KST), 4 파일 +72/−21.
- **왜 운영에 없나: 이유 불명.** 원장 `2026-08-31-naver-bulk-dispatch-result-ui-ledger.md` T9 는 "deploy `bdff05c8`, CI green" 까지만 적고 승격 언급이 없다. 이 기능의 마지막 승격 PR #227 은 같은 날 11:02 KST 머지라 이 커밋(12:52)을 못 담았다. 같은 절의 다음 항목은 "더 큰 사실 발견(소급 수집 필요)" 이다. AI_STATUS·AI_CHANGELOG·09-01~09-05 원장 어디에도 이 커밋 언급 없음.
- 스테이징 실화면 검증 기록: 없다(CI green 만).
- cherry-pick 탐침: **CLEAN**(deploy 의 `dashboard.py` 는 D 묶음 변경도 품고 있지만 이 커밋만 떼면 깨끗하다).
- 되돌릴 수 있나: 표시 전용 변경이라 revert 로 끝난다.
- 운영 데이터: 쓰기 없음. 불가역 조작(일괄 발송 버튼·재시도 배선)은 `is_today` 로 오늘만 열린다. 워크벤치 쪽은 값이 항상 True 라 동작 불변.
- env: 없음.

### C. 곁다리 2종

- `foms/services/audit_message_display.py` — 지시서는 1줄이라 했지만 지금은 **2줄**이다: `LOGIN_LOCKED`(A 의 일부, `40d25bb1b`) + `AS_SALES_DELIVERY_CHANGED`(D 의 일부, `3fdfe48ea`). 단독 항목이 아니라 각 묶음에 따라간다.
- `foms/services/security/ops_control_root.py`(22줄) + `tests/domains/test_ops_control_root_acl.py`(신규). deploy 커밋 `f730cd851`(2026-09-06 19:12, 래칫 세션).
  - **왜 운영에 없나: 이유 불명.** 원장에 이 커밋 개별 언급이 없다(키워드 ACL·icacls·cp949 로 0건). 커밋 본문만 사유를 말한다 — "운영 백필 dry-run 이 이 지점에서 멈춰 발견했다".
  - 운영 런타임 영향: **0.** `resolve_control_root` 는 `os.name != "nt"` 면 즉시 예외라 Railway(Linux)에서는 이 코드가 실행되지 않는다. 운영자 CLI(감사·백필·서명 활성화 등 `tools/ops/*` 20개)만 탄다. 한국어 Windows 에서 production 체크아웃으로 그 CLI 를 돌리면 지금은 `TypeError` 로 터진다.
  - cherry-pick 탐침: **CLEAN**. 되돌림 쉬움. 데이터·env 무관.

### D. AS 영업/택배 건 전달 배정 (지시서에 없던 묶음 — 오늘 deploy 반영)

- 코드 34 파일 +3,134/−51(`foms/api/cs/as_orders.py` +342 · `foms/services/orders/sales_delivery_link.py` 신규 360 · `sales_delivery_map.py` 신규 143 · `schedule_recommendations.py` · `nearby.py` · AS/실측/v3 템플릿·CSS·JS). 테스트·인벤토리까지 56 파일 +6,128. deploy 커밋 `3fdfe48ea`(백엔드) · `f05bd931b`(화면 3표면) · `c4cd51c4e`(담당자 문자열 500 수정) · `3c2253802`(fail-open 인벤토리 재생성).
- **왜 운영에 없나: 일부러 대기.** AI_STATUS(`103eb092e`) — "AS 전달 배정 스테이징 반영(deploy `3c2253802`) … 잔여: 스테이징 QA → 승격". 원장 `2026-09-09-as-sales-delivery-ledger.md` T7 은 "DONE(푸시 제외) — 푸시는 사용자 지시 대기" 였고 그 뒤 deploy 로 나갔다. 검증 기록은 로컬 dev 실화면까지. deploy CI 4종 green(`3c2253802`).
- cherry-pick 탐침: 코드 **CLEAN**, `docs/harness/foms_audit_coverage_inventory.json` · `foms_failopen_inventory.json` 2개만 충돌 — 둘 다 테스트가 재생성하는 인벤토리(`tools/harness/audit_coverage_scan.py` · `failopen_scan.py`)라 승격 트리에서 재생성하면 된다.
- 되돌릴 수 있나: 코드 revert. 그 사이 적힌 전달 배정 링크(`structured_data` 의 shipment 하위 노드)는 남지만 읽는 코드가 없으면 무해하다(지워지지는 않는다).
- 운영 데이터: **신규 쓰기 있음** — 전달 배정 링크를 주문 `structured_data` 에 적는다(커맨드 파이프라인 경유, deepcopy/flag_modified 는 호출자 책임으로 명시). 감사 action `AS_SALES_DELIVERY_CHANGED` 신규. 마이그레이션 없음. 실측 대시보드에 역방향 맵 조회 1회 추가(cap 300, `in_` 배치 1회).
- env: 없음. 핫파일 `templates/partials/shared/layout_head.html` 핀 2줄(v3 CSS/JS `20260909a`).
- 부속 `c4cd51c4e`(담당자 문자열 500): **운영 코드에도 dict 가정이 살아 있다**(`erp_display.py:496` `(parties.get('manager') or {}).get('name')`). 스칼라 담당자 주문이 운영 DB 에 있는지는 확인하지 않았다(재현은 로컬 실측 DB). 단독 cherry-pick 은 `foms/services/erp_mobile_order_display.py` 에서 **충돌**(D 앞 커밋 위에 얹혀 있다) — 타 세션 의존 신호라 D 와 함께만 간다. 미처리 2곳(`erp_orders_drawing.py:222,572`)은 메모리 `project_manager_field_shape_trap` 대로 남아 있다.

### E. 채널톡 push 동시클릭 경합 수정 (지시서에 없던 묶음 — 오늘 16:51 deploy 반영)

- `foms/api/channel/channel_integration.py` +61 · `tests/domains/test_channel_push_slot_guard.py` · `tests/postgres/test_channel_push_slot_lock.py`. deploy 커밋 `0e64a559a`.
- **왜 운영에 없나: 이유 불명(방금 올라갔다).** AI_STATUS 항목은 "deploy 대기" 로 적혀 있고 승격 언급 없음. deploy CI 4종 green.
- 내용: 판정 전에 `pg_try_advisory_xact_lock(주문, push 종류)` 로 슬롯을 잡고 못 잡으면 409. 진입점 2곳. SQLite 레인은 통과시키고 로그.
- cherry-pick 탐침: 코드 **CLEAN**(`docs/AI_STATUS.md` 만 충돌 — 문서를 빼면 된다). 되돌림 쉬움. 데이터 쓰기 없음. env 없음. PG 전용 기능이라 운영(PostgreSQL)에서만 실제로 동작한다.

## 하네스·도구 (91 파일 중 운영에서 실제로 도는 것)

| 파일 | deploy 커밋 | 지금 production 상태 | 승격 뜻 | 탐침 |
|---|---|---|---|---|
| `tools/ops/backfill_deleted_at_core.py` · `_utc.py` | `7a4a8fd9b`(09-08 철회) | **틀린 전제의 -9시간 갈래가 살아 있다.** 운영 실측으로 철회된 논리(234행을 보정하면 85행이 생성 시각보다 앞선다). ISO 28행은 이미 deploy 코드로 운영 반영 완료 | 안전장치. production 체크아웃에서 실행하면 234행이 9시간 틀어질 코드를 없앤다(승인 게이트는 있으나 코드 자체가 틀림) | CLEAN |
| `tools/ops/drift_baseline.json` | `017153194` | `erp_flat.drift` **1750**. 운영 워크플로 `drift-audit-daily` 가 production 브랜치 값을 읽으므로 래칫이 실측(924)보다 826 헐겁다 | 조임. AMBIGUOUS 924(결제금액, 자동 수정 불가)가 순증하면 매일 red — 의도된 규칙 | CLEAN |
| `tools/perf/perf_budgets.json` | `c1eaaa024`(revert) | `/erp/completion?view=fragment` `body_bytes_max` **33941**. 완료 대시보드 코드는 production = deploy(되돌린 상태, 실측 13.6KB)인데 예산만 재시드 값이 남았다(`303b53b33` 이 재시드만 반입) | 조임(18466). deploy perf-gate 는 18466 으로 green. perf-gate 는 deploy push + production PR 에서 돌고 PR 은 브랜치 파일을 읽는다 | (파일 1개, 단독 반영 가능) |
| `tools/ops/naver_return_watch.py` | `144a4a7c0` | 없음 | 읽기 전용 관측 CLI 신설. 운영 동작 무관 | — |

나머지(래칫 계약 테스트 + baseline JSON 3종·CTX-GATE·ci_watch·guard_policy·PowerShell 인코딩 계약·정본 경로 계약·ci.yml DOCSCOPE/VISUAL·`.claude/` 스킬·`.env.example`)는 운영 런타임과 무관하다. 올린다면 **테스트와 baseline JSON 을 쌍으로** 통째 올려야 한다 — 원장 T11 에서 `layer_dependency_baseline.json` 이 DU 충돌을 낸 전례.

## 참고 관측(범위 밖, 손대지 않음)

- 운영 `drift-audit-daily` 09-08 21:15Z 실패 — 로그인 502(`Login POST returned an unauthenticated session_staging cookie`, PR 머지 직후 배포 중으로 보임). 기준선과 무관. 다음 실행 09-09 밤.
- 운영 `worker-heartbeat-daily` 09-08 21:27Z 실패 — `NAVER_SETTLE_SYNC` STALE 3479초. 09-09 05:44Z 실행은 success.
- 이 워크트리 검증: 아래 갱신.

## 판정 뒤 일어난 일 (같은 날 저녁)

- **production 이 판정 중에 두 번 움직였다.** PR #337(E 채널톡 동시클릭 경합, `b3fa32f35`) · PR #338(D AS 전달 배정, `e4064acea`~`cc67d7188`) — 각자 세션이 승격했다. production `93a2addf7` → `9e89d8e3a`. deploy `12532a70f`(문서 1건 추가).
- 사용자 선택(AskUserQuestion): 제품 **B·E**, 도구 **백필+ACL · drift 924 · perf 18466 · 하네스 나머지 통째**. A·D 는 제외. E 는 이미 운영에 있어 빠진다.
- 승격 브랜치 `promote/triage-20260909`(worktree `c:/tmp/foms-promo-20260909`, base `9e89d8e3a`) — 7 커밋:

| 커밋 | 출처 | 방식 |
|---|---|---|
| `0dbed45d0` B 지난 날짜 발송 띠 | deploy `bdff05c8b` | cherry-pick CLEAN |
| `19a1bb271` ACL 가드 | deploy `f730cd851` | cherry-pick CLEAN |
| `2d943b381` 백필 -9시간 갈래 철회 | deploy `7a4a8fd9b` | cherry-pick CLEAN |
| `3a235ce8e` drift 기준선 924 | deploy `017153194` | cherry-pick CLEAN |
| `031f1370a` perf 예산 18466 | deploy `c1eaaa024` 의 JSON 1줄만 | 파일 반입(코드 hunk 는 production 에 이미 동일) |
| `99e704f1f` 하네스·도구·문서 동기화 | origin/deploy `12532a70f` 파일 125개 | 파일 반입 — A 파일 5개·`docs/harness/*.json` 제외 |
| `ec234106a` 인벤토리 재생성 | 이 트리 코드 | 스캔 5종 실행(`--check` 전부 exit 0) |

- **잔차 검사**: `git diff --name-only P origin/deploy` = A 파일 5개 + 인벤토리 JSON 4개(deploy 쪽은 A 항목을 품고 있어 다른 게 정상). 그 외 0 — 즉 P = deploy − A.
- `promote_completeness.py --shas bdff05c8b,f730cd851,7a4a8fd9b,017153194` 는 `naver_ingest.py`·`naver_dispatch_strip.html` 을 건드린 타 커밋 12건을 `+`(missing)로 찍었다. 그 두 파일은 P 와 deploy 가 바이트 동일(잔차 0)이라 **내용은 이미 production 에 있고 SHA 만 다른 오탐**이다(원장 T10 의 `30836696` 과 같은 축).
- 인벤토리 cherry-pick 함정: E 커밋을 옛 base 에 얹었을 때 `docs/AI_STATUS.md` 만 충돌했다(코드 무충돌). 새 base 에서는 E 자체를 빼서 문제 없음.

## 검증 (승격 브랜치 P, HEAD `ec234106a`)

```
python -c "import app; print('APP_OK')"                         -> APP_OK
python -m pytest tests/harness -q                                -> 471 passed
python -m pytest -q --ignore=tests/visual --ignore=tests/harness -p no:playwright -n auto --dist loadfile
                                                                 -> 9326 passed, 595 skipped
CI 'UI structural' 서브셋(tests/visual 15 파일)                  -> 149 passed, 2 skipped
scripts/ops/pre_push_smoke.ps1                                   -> PRE-PUSH SMOKE PASSED (exit 0)
tools/harness/*_scan.py --check (5종)                             -> exit 0
```

- 브랜치 push → **PR #339** (`gh pr create --base production`, `HEAD:production` 직접 push 없음). 머지는 사용자 확인 뒤.
- PR #339 검사 4종 **전부 pass**(FOMS CI 3m26s · Harness 1m19s · pg-lane 2m5s · perf-gate 1m36s). `mergeable=MERGEABLE · CLEAN`.

## 머지 (사용자 승인 "지금 머지", 2026-09-10 08:41 KST)

- 머지 직전 `git ls-remote origin production` = `9e89d8e3a`(base 불변) 재확인 → `gh pr merge 339 --merge`.
- production `9e89d8e3a` → **`3888da9ab`**. `ec234106a` 가 production 조상임을 확인.
- 배포: `/healthz` 가 21초 뒤 `commit=3888da9ab · status=ok`.
- 머지 커밋 자체에는 워크플로 런 0건(선례와 같음, `ci_watch --quick` 은 "런 없음 → green 취급" — 근거는 PR 검사 4종이다).
- 정리: 승격 워크트리 `c:/tmp/foms-promo-20260909`·로컬/원격 브랜치 `promote/triage-20260909` 삭제.

## 운영 관측 (머지 전 09-09 밤 스케줄 런, 손대지 않음 — 다음 세션 판단)

- `drift-audit-daily` 09-09 20:59Z(`9e89d8e3a`, 옛 기준선) **실패**: "AS 축 투영(as_axis_status) 드리프트 0 → 1 (+1)", 총 927건. **운영에 AS 축 투영 누락 1건이 새로 생겼다** — 09-08 은 로그인 502 였고 이번은 진짜 순증이다. 오늘 밤 런은 새 기준선(flat 924)으로 돈다 — flat 도 924 를 넘으면 red 가 두 줄이 된다.
- `worker-heartbeat-daily` 09-09 21:15Z **실패**: `NAVER_SETTLE_SYNC` 하트비트 나이 2760초(예산 180) STALE — 09-08 밤(3479초)에 이어 이틀째. 다른 루프는 OK.

## 조사: 정산 동기화 하트비트 STALE (2026-09-10, 읽기 전용 — 사용자 선택)

**원인 확정**: `scripts/maintenance/run_naver_settle_sync.py:270` `_heartbeat_metadata` 가
`int(stats.get("calls") or 0)` 를 하는데 `run_settle_sync` 의 `stats["calls"]` 는 endpoint 별 **dict**
(`rows` 도 table 별 dict). 매일 05:30 KST 정기 실행(61~62초, OK)이 끝난 그 tick 에서 `TypeError` →
이 호출은 `_run_loop` 의 `try` **밖**이라 루프 프로세스가 죽는다. `start.sh` 의 `… --json &` 루프에는
감독자가 없다(감시 루프는 RQ 소비자만) → 다음 WORKER 재배포까지 하트비트 정지.

근거(전부 읽기 전용):
- 운영 `naver_settle_sync_runs`: SCHEDULE run 35(09-08 20:30:35Z) · 38(09-09 20:30:26Z) 둘 다 61~62초, OK,
  calls `{'settle/case': 45, 'settle/daily': 3, 'settle/commission-details': 45}`.
- 일일 점검의 나이 3479초(09-08 21:27Z)·2760초(09-09 21:15Z) → 마지막 하트비트 20:29Z = 실행 시작 직전 tick.
- WORKER 이전 배포(`0e7f589a`, 09-09 12:02Z) 로그: `2026-09-09T20:31:30Z Traceback … run_naver_settle_sync.py
  line 270, in _heartbeat_metadata / TypeError: int() argument must be … not 'dict'`. 루프 시작 로그
  12:03:21Z(tick=60s) 이후 정확히 정기 실행 1회 뒤.
- 감시자는 제대로 울렸다: `WORKER_STALLED` 20:32:42Z "NAVER_SETTLE_SYNC(3분째)" → `WORKER_RECOVERED`
  23:43:17Z(PR #339 머지 재배포로 루프 재기동). 낮 점검이 초록이던 것은 재배포가 잦았기 때문.
- 로컬 재현(스크래치 탐침 `probe_settle_loop_death.py`): 운영과 같은 결과 모양을 돌려주면 `_run_loop` 이
  `TypeError` 로 탈출, 그 tick 하트비트 0 — 3초 만에 RED.

기각한 가설: "sync 가 오래 걸려 그동안 하트비트가 없다" — 실행 표가 61초라고 말한다.

왜 못 잡았나: `test_settle_sync_loop_beats_outside_its_window` 는 창 밖(result=None)만 돌린다. 창 안 성공
tick 을 실제 `_finish` payload 모양으로 돌리는 테스트가 없다.

같은 로그의 다른 Traceback 6건(22:15Z~23:39Z)은 전부 `botocore ClientError 404 HeadObject`(R2 객체 없음) —
별개 축, 손대지 않음.

수정안(A 등급): ① dict 면 값을 합산(`sum(calls.values())`), rows 도 같이 ② `emit_heartbeat`·metadata 조립을
루프의 예외 가드 안으로(하트비트 결함이 루프를 죽일 수 없게) ③ 회귀 테스트 — 창 안 성공 tick 을 실제 payload
모양으로 1 tick 돌려 루프 생존 + 하트비트 1건 단언(`test_loop_heartbeat_wiring.py` 의 `_drive_one_tick` 시임)
④ 사고 원장 `docs/incidents/2026-09-10-settle-loop-dies-after-success-tick.md`.

## 남은 것

- 로그인 한도·잠금(A, deploy `40d25bb1b`) — 사용자 판단 대기(운영에 올리면 8회 실패 → 15분 429, 관리자 해제 UI 없음).
- 운영 관측: AS 축 드리프트 1건 원인 조사(미착수). 정산 동기화 STALE 은 원인 확정·수정(위 절, 사고 원장 `docs/incidents/2026-09-10-settle-loop-dies-after-success-tick.md`) — 운영 승격 뒤 다음 05:31 KST 지나서 수동 dispatch 로 확인.

## 검증 (이 워크트리, HEAD `103eb092e` = origin/deploy)

코드 변경 없음. deploy 트리 그대로 검증 명령을 돌렸다.

```
$ python -m pytest tests/services/integrations tests/harness -q
2337 passed, 1 warning in 158.85s
$ python -c "import app; print('APP_OK')"
APP_OK
$ powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/pre_push_smoke.ps1
792 passed · [OK] Pytest subset (32 targets) · === PRE-PUSH SMOKE PASSED === (exit 0)
```

`docs/harness/*.json` 은 `git checkout -- docs/harness/` 로 원복(테스트 재생성분).
