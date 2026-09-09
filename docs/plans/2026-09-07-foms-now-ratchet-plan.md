# FOMS 검토 보고서 ④ '지금' 구간 실행 플랜 (2026-09-07)

> 정본 입력: `docs/plans/2026-09-06-foms-system-review-report.md` ④ '지금(첫 2~4주)' 1~7번.
> 이 플랜은 그 7항목을 T1~T7 로 옮긴 것이고, 각 task 의 완료 기준은 보고서 '검증' 칸의
> 명령을 그대로 쓴다(문구 변경 없음). 진행 상태·검증 출력 원문은
> `docs/plans/2026-09-07-foms-now-ratchet-ledger.md` 에 task 단위로 남긴다.

## 0. 기준 커밋·작업 위치

- 지시 기준 커밋 `0d1e37fa7` = 메인 트리 `C:\DEV\FOMS` 의 로컬 `deploy` HEAD. **일치 확인됨**
  (`git log --oneline -1` → `0d1e37fa7 docs(review): FOMS 시스템 전체 개발 검토 보고서 + 진행 원장`).
- 다만 로컬 `deploy` 는 `origin/deploy`(`da7d4ab9b`) 대비 **2 ahead / 11 behind** 다. ahead 2 는
  이번 검토 문서 커밋 2건(`062723348`, `0d1e37fa7`)이고 아직 push 되지 않았다.
- 따라서 작업 위치는 **`origin/deploy` 기반 세션 worktree**(`python tools/harness/session_worktree.py create --name now0907`)
  이고, 그 위에 문서 커밋 2건을 cherry-pick 해 보고서를 동반한다. 실작업 base 는
  `da7d4ab9b + (062723348, 0d1e37fa7)` 이며, 지시의 `0d1e37fa7` 과 이 점에서 어긋난다(병기).
- 모든 bash 호출은 `cd /c/tmp/foms-s-now0907 && ...` 로 시작한다. worktree 세션의 cwd 는 턴 경계에서
  메인 트리로 리셋되므로 `cd` 없는 명령은 조용히 메인 트리에서 돈다.

## 1. 실행 모델 (CEO 총괄 + 멀티 에이전트)

사용자 명시 지시: "멀티 에이전트 사용해서 병렬로 처리하고 CEO 에이전트가 총괄 지휘".

| 단계 | 구성 | 대상 |
|---|---|---|
| A (병렬) | CEO 설계 1 → 워커 3 병렬 → 리뷰어 2(스펙/품질 분리) → CEO 판정 1 | T1 · T2 · T5 |
| B (순차) | 워커 1 + 리뷰어 1, task 마다 반복 | T3 → T4 → T6 |
| C (총괄 직접) | 세션 총괄이 직접 수행(git 작업 포함) | T7 · ci.yml 등재 · 커밋 · push · 스테이징 QA |

무신뢰 규율: 서브에이전트의 "완료" 보고는 주장일 뿐이다. **총괄이 `git diff` 를 직접 읽고 검증
명령을 직접 실행한 뒤에만** 원장에 DONE 을 적는다. 리뷰 findings 는 받는 즉시 전량 원장에 보존한다.

### 파일 소유권 표 (워커 간 편집 충돌 0)

| 소유자 | 편집 허용 파일 |
|---|---|
| T1 워커 | `tests/contracts/runtime/test_layer_dependency_ratchet.py`(신규) · `tests/contracts/runtime/layer_dependency_baseline.json`(신규) |
| T2 워커 | `tests/harness/test_canonical_doc_paths.py`(신규) · `tests/harness/test_file_size_ratchet.py`(신규) · 두 기준선 JSON(신규) · `CLAUDE.md` · `.cursor/rules/00-project-context.mdc` · `foms/README.md` |
| T5 워커 | `docs/incidents/*.md`(신규 7) · `docs/harness/policy/DECISIONS.md` |
| T3 워커 | `.github/workflows/drift-audit-daily.yml`(신규) · `foms/services/integrations/naver_commerce/order_candidates.py` · 신규 계약 테스트 1 |
| T4 워커 | `scripts/maintenance/run_naver_auto_dispatch.py` · `foms/services/jobs/tasks.py` · 신규 계약 테스트 1 |
| T6 워커 | `foms/web/auth/routes.py` · `foms/services/rate_limit.py` · `foms/services/audit_message_display.py` · 신규 계약 테스트 1 |
| 총괄 전용 | `.github/workflows/ci.yml` · `README.md` · `.env.example` · `docs/AI_STATUS.md` · 이 플랜/원장 · 모든 git 명령 |

`.github/workflows/ci.yml` 은 여러 task 가 한 줄씩 필요로 하는 공유 파일이라 **총괄만 편집**한다.
워커는 넣을 줄을 보고서에 적어 넘기고, 총괄이 적용한다.

### 워커 공통 규칙 (브리프에 그대로 박는다)

1. CRLF 보존. 기존 파일 개행 방식을 바꾸지 않는다.
2. 모든 명령을 `cd /c/tmp/foms-s-now0907 && pwd && ...` 로 시작한다.
3. git 명령 금지(add·commit·push·checkout 전부). 총괄 몫이다.
4. 전체 pytest 금지. 단일 파일 실행과 `--collect-only` 만. `python` 앞에 `PYTHONIOENCODING=utf-8`.
5. 새 패키지 설치 금지. 표준 라이브러리와 이미 설치된 의존만 쓴다.
6. 근본 원인 수정만. 증상 덮기·우회·`try/except: pass`·하드코딩 우회 금지.
7. 인라인 스타일 금지, jQuery 금지, `static/css/foundation/erp-pro.css` SSOT.
8. 소유권 표 밖 파일을 건드려야 하면 편집하지 말고 보고한다.

## 2. Task

### T1. 의존 방향 래칫 계약 테스트 [보고서 ④ 지금 1 · D2]

- 무엇: `tests/contracts/runtime/` 에 표준 라이브러리(`ast`)만 쓰는 테스트 1개. 현재 위반
  (services→web 8 · api→web 53 · services→api 15 · persistence→services 1 · 지연 import 473)을
  기준선 JSON 으로 동결해 **순증만 red**.
- 왜: 경계가 디렉토리 이름일 뿐이라 에이전트 속도로 역방향이 계속 는다. 기준선 래칫은 코드를
  고치지 않고 오늘부터 악화를 막고, 줄어드는 숫자가 분해 진척의 척도가 된다.
- 설계 제약:
  - 기준선은 **개수가 아니라 위반 항목 집합**(모듈 쌍 단위)으로 동결한다. 개수만 세면 한 곳을
    지우고 다른 곳에 넣는 교환이 통과한다.
  - 금지 방향 정본은 `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md:315-322`.
  - 함수 안 지연 import 도 `ast` 로 같이 센다(순환을 숨기는 경로라 기준선에 포함).
  - 실패 메시지에 "기준선 파일 경로 + 새 위반 목록 + 되돌리는 법"을 적는다. 새 세션이 테스트
    실패만 보고 배울 수 있어야 한다.
- 완료 기준(보고서 검증 칸 원문): **`foms/services` 아무 파일에 `from foms.web import auth` 한 줄을
  넣으면 그 테스트만 red, 되돌리면 green.**
- 원장에 남길 출력: 주입 전 green 1줄 · 주입 후 red(assert 메시지 포함) · 되돌린 뒤 green 1줄.

### T2. 파일 크기 래칫 + 정본 경로 정정 [④ 지금 2 · D2·D8]

- 무엇: ① 500줄+ 파이썬 · 300줄+ JS 목록을 기준선으로 동결(순증만 red).
  ② `CLAUDE.md:48-51` · `.cursor/rules/00-project-context.mdc:31` · `foms/README.md` 의
  `apps/` · 루트 `services/` · `constants.py` 를 실경로로 고친다(세 경로는 2026-04-12 에 사라졌다).
  ③ 정본·안내서의 백틱 경로 실존 테스트를 `tests/harness` 에 둔다(현재 MISSING 20).
- 왜: 판단 규칙(문서)이 죽고 동결 계약(테스트)만 살아남은 상태다. 규칙을 테스트로 옮겨야 다음
  6k 줄 파일이 안 생기고, 새 세션이 테스트 실패로 배운다.
- 설계 제약:
  - 경로 실존 테스트는 `tests/harness/` 에 둔다. 이 트리는 `test_docs_facing_registry.py` 의
    스캔 대상 밖(`_OTHER_LANES`)이라 ci.yml 문서 서브셋 등재 의무가 걸리지 않고, `harness-ci.yml`
    이 전담한다. **만약 워커가 `tests/domains/` 등 메인 레인에 두면 ci.yml 서브셋 등재가 강제된다
    (CI-DOCSCOPE-01)** — 그때는 총괄이 ci.yml 에 줄을 넣는다.
  - MISSING 20 을 한 번에 다 고치려 들지 않는다. 이번 범위는 **정본 3벌**(CLAUDE.md·cursor rule·
    foms/README.md)이고, 나머지는 기준선에 '알려진 MISSING' 으로 동결해 순증만 red.
- 완료 기준(보고서 검증 칸 원문): **`grep -c 'apps/' CLAUDE.md .cursor/rules/00-project-context.mdc foms/README.md`
  전부 0, 없는 경로를 한 줄 넣으면 red.**
- 원장에 남길 출력: grep 출력 3줄 원문 · 없는 경로 주입 시 red · 되돌린 뒤 green · 크기 래칫 테스트 green.

### T5. 사고 원장·결정 기록 선등재 [④ 지금 5 · D8·D3·D7] — T1·T2 와 병렬

- 무엇: 데이터 사고 3건(08-14 AS 55건 · 08-24 서버 키 소실 · 09-03 AS 2건)과 운영 사고 4건
  (08-07 13시간 정지 · 08-31 852초 · DEAD 1,188 · 실패잡 2,544)을 `docs/incidents` 에 **같은 양식**
  (유형 · 원인 축 · 복구 · 구조 변경 여부 · 재발 여부)으로 등재. `docs/harness/policy/DECISIONS.md` 에
  AS-AXIS-01 결정 1줄과 ept_b8 복귀 정정 1줄.
- 왜: 같은 유형이 넷인데 등재는 하나라 '반복' 이 시스템에 안 보이고, 다음 ablation(2027-02)이
  오염된 기록으로 판정한다.
- 설계 제약:
  - **새 사실을 지어내지 않는다.** 각 문서의 모든 줄은 저장소 안 근거(커밋 SHA · 도구 docstring ·
    AI_CHANGELOG · AI_STATUS · 기존 plans/ledger)를 앵커로 달고, 근거가 없는 칸은 `미상(근거 없음)`
    으로 적는다. 근거 출처는 보고서 R1·R3·R8 과 `docs/guides/DATA_INCIDENT_RECOVERY.md:3-4`,
    `docs/AI_CHANGELOG.md:50`.
  - ept_b8 정정은 `docs/harness/policy/DECISIONS.md:35`(ept_b8 'DEAD 삭제')와
    `.github/workflows/perf-gate.yml:44`(라이브 의존)의 모순을 기록하는 것이다. 워크플로는 안 고친다.
- 완료 기준(보고서 검증 칸 원문): **`ls docs/incidents | grep -c 2026-0[89]` ≥ 4,
  `grep -c 'AS-AXIS' docs/harness/policy/DECISIONS.md` ≥ 1.**
- 원장에 남길 출력: 두 명령 출력 원문 · 신규 문서 파일 목록.

### T3. 드리프트 감사 배선 + 09-01 원인 줄 제거 [④ 지금 3 · D3] — 순차 1

- 무엇: ① `tools/ops/audit_erp_flat_columns.py` · `tools/ops/audit_as_axis_drift.py` 를 `rum-daily.yml`
  패턴의 워크플로로 매일 실행(스케줄 + `workflow_dispatch`, 리포트는 step summary).
  ② `foms/services/integrations/naver_commerce/order_candidates.py:822-823` 의 `Order.phone == digits`
  갈래 제거(읽기 14곳을 `erp_phone_digits` 로 옮기는 첫 건).
- 왜: 사본 구조를 바꾸기 전에도 어긋남을 사람이 아니라 기계가 세야 한다.
- 설계 제약:
  - `rum-daily.yml` 은 "schedule 은 기본 브랜치(production)의 워크플로 파일만 실행한다" 는 주석을
    달고 있다. 새 워크플로도 같은 주석을 달고, deploy 단계에서는 `workflow_dispatch` 로만 검증한다.
  - 갈래 제거는 `or_(Order.erp_phone_digits == digits, Order.phone == digits)` 에서 두 번째 항만
    없앤다. 남는 것은 인덱스 컬럼 단독 매칭이다. 주석의 "phone 원문은 보조로만 본다" 도 같이 정정한다.
  - 이 변경으로 빨개질 수 있는 기존 테스트를 워커가 먼저 `--collect-only`/단일 파일 실행으로 찾는다.
- 완료 기준(보고서 검증 칸 원문): **두 감사가 2주 연속 0건(워크플로 아티팩트), 스테이징에서 전화 변경
  1회 뒤 트리아지 자동 매칭이 같은 고객을 찾음(09-01 재현 시나리오).**
  - 이 세션에서 닫히는 부분: `workflow_dispatch` 1회 green + 로컬 감사 2종 실행 출력 + 매칭 계약
    테스트 green + 스테이징 09-01 재현 시나리오 통과.
  - 이 세션에서 못 닫는 부분: **"2주 연속 0건"** 은 시간이 필요하다. 원장에 `DONE(부분) + 추적:
    2026-09-21 재확인` 으로 명시하고, 감춰서 DONE 으로 올리지 않는다.

### T4. 루프 하트비트 1줄 + 워커·SIDEFX Sentry 배선 [④ 지금 4 · D7] — 순차 2

- 무엇: `scripts/maintenance/run_naver_auto_dispatch.py` tick 끝에
  `upsert_heartbeat(engine, 'NAVER_AUTO_DISPATCH', ...)`(전례 `foms/services/sidefx_worker.py:497-524`),
  `foms/services/jobs/tasks.py` 상단과 루프 진입점에서 `init_sentry()`(DSN 없으면 no-op).
- 왜: 지금은 사용자 화면이 모니터링 장치다(2026-02 워커 offline · 2026-08-31 SIDEFX 미배포, 두 번 다
  사용자가 지도에서 발견).
- 설계 제약:
  - 하트비트 표는 `side_effect_worker_heartbeats`(`models.py:2677`), upsert 는 PK `worker_kind` 로
    `ON CONFLICT DO UPDATE`. 새 kind `NAVER_AUTO_DISPATCH` 를 쓴다.
  - `check_sidefx_readiness.py` 는 `foms/services/sidefx_worker.py:45` 의 3종 고정을 순회하므로
    **그대로는 못 쓴다**. 준비 판정 일반화는 보고서 ④ 12~24개월 23번이라 이번 범위 밖 —
    검증은 도구 무관 직접 질의로 한다.
  - 하트비트 실패가 본 작업(자동 발송)을 막으면 안 된다. 다만 삼키지도 않는다 —
    `logging.warning` + Sentry 이벤트로 남기고 tick 은 계속한다(훅 fail-open 로그 의무와 같은 원칙).
- 완료 기준(보고서 검증 칸 원문): **스테이징에서 루프가 도는 동안 하트비트 표
  `side_effect_worker_heartbeats`(`models.py:2677`)의 `NAVER_AUTO_DISPATCH` 행 `last_heartbeat_at` 이
  tick 마다 갱신되고, 루프 프로세스를 kill 하면 60초 넘게 갱신이 멈춘다(도구 무관 직접 질의);
  워커 실패잡 1건이 Sentry 에 environment=staging 이벤트로 잡힘.**
  - 로컬 선행: 계약 테스트 1개(루프 1회 뒤 heartbeat 행 존재) green.
  - 스테이징 부분은 deploy push + Railway 배포 뒤 수행한다.

### T6. 로그인 전용 한도 + 실패 잠금 + 레이트리미터 폴백 로그 [④ 지금 6 · D6] — 순차 3

- 무엇: `foms/web/auth/routes.py:293` 의 `login()` 에 `limiter.limit`(username+IP 키)과 실패 카운터·
  `LOGIN_LOCKED` 감사, `foms/services/rate_limit.py:58-70` 뒤 폴백 진입 시 `logging.warning` + Sentry 1건.
- 왜: 고급 통제는 있는데 가장 흔한 공격면을 막는 층이 0 이고, 열림이 관측되지 않으면 사업 판단
  원장이 만들어질 수 없다.
- 설계 제약:
  - **새 감사 action 은 라벨 등재가 필수다.** `foms/services/audit_message_display.py:292` 의
    `"LOGIN_FAIL": "로그인 실패"` 옆에 `"LOGIN_LOCKED"` 한글 라벨을 같이 넣는다. 빠뜨리면 감사
    화면에 raw 태그가 뜬다.
  - 키는 username+IP 조합이다. username 만 쓰면 한 사용자를 밖에서 잠글 수 있고(DoS), IP 만 쓰면
    사무실 공용 IP 가 통째로 잠긴다.
  - 기존 `sign_rate_bucket`(`foms/services/security/auth_rate/key_state.py:113`) 브리지를 깨지 않는다.
  - 잠금은 **fail-open** 이다. Redis 가 없거나 카운터 조회가 실패하면 로그인을 막지 않고
    `logging.warning` 을 남긴다. 열림을 조용히 넘기지 않는 것이 이 task 의 절반이다.
  - 설치 없이 가능해야 한다(`flask-limiter` 는 이미 있다). 새 패키지 없음.
- 완료 기준(보고서 검증 칸 원문): **스테이징 잘못된 비밀번호 11회 → 429 + security_logs 에
  LOGIN_FAIL 10 · LOGIN_LOCKED 1; REDIS_URL 을 도달 불가 주소로 둔 테스트에서 warning 레코드 1건이
  caplog 에 잡힘.**
  - 로컬 선행: 계약 테스트 1파일(11회 시나리오 + caplog warning) green.
  - 스테이징 부분은 deploy push + 배포 뒤 **가상 계정**으로 수행한다(실계정 잠금 금지).

### T7. 두 번째 개발자 부팅 경로 [④ 지금 7 · D8] — 총괄 직접

- 무엇: `README.md` 를 실제 절차(`DATABASE_URL` · `alembic upgrade` · `import app` → `APP_OK`)로
  재작성, 루트 `.env.example`(키 이름만, 값 없음) 추적, `.claude/skills` 4종 git add(**사용자 승인 뒤**).
- 왜: 규칙이 가리키는 도구가 클론에 없으면 규칙이 거짓이 된다. 현재 `git ls-files .claude/skills`
  → `.claude/skills/overnight/SKILL.md` 1건뿐이고 CLAUDE.md 가 가리키는 4종은 미추적이다.
- 설계 제약:
  - 현재 README `30-55` 는 `set DB_USER=...` · `python migration.py` 를 지시하는데, 앱의 실제 정본은
    `DATABASE_URL` 이다. 이 절을 실제로 도는 절차로 교체한다.
  - `.env.example` 에는 **키 이름만** 넣는다. 값·토큰·DSN 절대 금지.
  - `.claude/skills` git add 는 사용자 승인 항목이다. 승인 없으면 README·`.env.example` 만 하고
    이 줄은 BLOCKED 로 남긴다.
- 완료 기준(보고서 검증 칸 원문): **임시 디렉토리 clone 뒤 README 만 따라
  `PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"` 와
  `timeout 300 python -m pytest tests/harness -q` 통과, `git ls-files .claude/skills | wc -l` → 5.**

## 3. 게이트·순서

1. worktree 생성 + 문서 커밋 2건 cherry-pick → base 확인(`git log --oneline -3`).
2. A 단계 병렬(T1·T2·T5) → 총괄이 diff 직접 확인 + 검증 명령 직접 실행 → 원장 DONE → 커밋(pathspec).
3. B 단계 순차(T3 → T4 → T6) → task 마다 같은 절차.
4. T7 총괄 직접.
5. `python -c "import app; print('APP_OK')"` → `scripts/ops/pre_push_smoke.ps1` exit 0 확인.
6. `deploy` push(**production 은 절대 금지**) → `python tools/harness/ci_watch.py` 로 CI 확인.
   ci_watch 는 워크플로 1개만 보므로 "CI green" 판정은 **전 워크플로 나열**로 한다.
7. 스테이징 배포 뒤 T3·T4·T6 의 스테이징 검증 수행 → 원장 갱신.
8. `docs/AI_STATUS.md` 갱신.

## 4. 승인이 필요한 항목

1. **`.claude/skills` 4종 git add**(T7) — diagnosing-bugs · handoff · wayfinder · writing-great-skills.
   저장소에 세션 스킬 문서가 들어간다.
2. **새 패키지 설치: 없음.** T1 은 표준 라이브러리 `ast`, T6 은 이미 있는 `flask-limiter` 를 쓴다.
   계획이 바뀌어 설치가 필요해지면 착수 전에 이름·이유를 보고하고 승인을 받는다.
3. 스테이징 검증(T4·T6)은 deploy push 후 수행한다. production 은 건드리지 않는다.

## 5. 이번 범위 밖(명시)

- 보고서 ④ '이번 분기'(8~), '12~24개월'(20~) 전 항목.
- 읽기 경로 14곳 전체를 `erp_phone_digits` 로 옮기는 작업(T3 은 그 중 1건만).
- `check_sidefx_readiness.py` 준비 판정 일반화(보고서 12~24개월 23번).
- MISSING 20 경로 전체 정정(T2 는 정본 3벌 + 나머지 동결).
