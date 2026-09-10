# FOMS 프로젝트 — AI 에이전트 공통 규칙

이 파일은 어떤 IDE(Cursor, VS Code, JetBrains 등)·어떤 LLM(Claude, GPT, Gemini, Codex 등)에서도 준수해야 하는 규칙의 **정본(SSOT)** 이다. Cursor 는 `.cursor/rules/`, Claude Code 는 루트 `CLAUDE.md` 가 도구 전용 보강만 담고, 충돌하면 이 파일이 우선한다. bash/`&&` 예시는 "Claude Code 전용" 으로 명시된 때만 따른다(저장소 문서 기본 셸은 아래 운영 환경 참조).

---

## 하네스 정책 단일 기준 (Cursor · Claude · Codex 공통)

- **앱 import 검증 성공 문자열(표준)**: `APP_OK` — `python -c "import app; print('APP_OK')"` 로 확인한다.
- **브라우저**: 탐색·수동 재현·디버깅은 Cursor browser MCP, 반복 가능한 QA·릴리스 스모크는 gstack browse 런타임, 디자인 검수는 gstack-design-review.
- **훅 fail-open**: 세션을 막지 않기 위해 예외를 삼키는 방식은 실패가 로그 등으로 남는 경우에만 허용한다. 묵시적 무시(조용한 swallow)는 금지한다.
- **작업 레벨**: 코어 변경(DB/Auth/API, 배포 인프라, 하네스 인프라 — Hooks/Rules/Agents/검증 흐름)은 아래 공통 실행 프로토콜을 따른다. 단순 UI 변경·타이포는 바로 코딩한다. 코어 변경 게이트는 Stop 훅·pre_push_smoke·branch protection 이 코드로 강제한다.

## 공통 실행 프로토콜 (핵심 코어 변경 시)

- **Research**: `docs/harness/policy/DECISIONS.md` + `docs/ARCHIVE_INDEX.md` 를 먼저 조사한다.
- **Plan**: `docs/guides/SPEC_TEMPLATE.md` 기준으로 Spec 또는 실행 계획을 먼저 확정하고 사용자 승인을 받는다.
- **Implement**: 승인 후 구현하고, 완료 전 `.agents/workflows/verify-result.md` 기준으로 검증한다.

## 절대 규칙: 성능 회귀 원천 차단

코드/기능 추가가 서버·페이지를 느리게 만드는 것을 머지 전에 차단한다(모든 도구·모델 공통).
- **자동 강제**: `tests/performance/test_perf_regression_guard.py`(`scripts/ops/pre_push_smoke.ps1` 포함, exit 0 아니면 push 금지) — G1 `<script>` 는 기본 `defer`/`type=module`, 렌더 차단 동기 스크립트 금지 · G2 외부 CDN 동기 스크립트 금지(무거운 라이브러리는 사용 시점 lazy 로드, 공용 partial 에 페이지 전용 무거운 JS 금지) · G3 서비스워커 network-first fetch 는 timeout+캐시 폴백(무한 대기 금지) · G4 ERP shell fragment 에서 재실행되는 JS 는 idempotent(전역 listener 는 `window.__*_BOUND` 같은 singleton guard). 규칙 본문·사유: `docs/guides/PERFORMANCE_GUARDRAILS.md`.
- **쿼리**: JSONB/text `cast(...).ilike` 인덱스 없이 hot path 금지(부분일치=trigram, id=`@>`). N+1 금지(`in_(ids)` 배치), 매 요청 무거운 계산은 캐시. 마이그레이션 CONCURRENTLY+다중 replica 는 세션 레벨 advisory lock.
- **검증**: 대시보드/리스트/검색/액션 변경은 서버 TTFB 측정 + `EXPLAIN` 으로 Seq Scan 없음 확인. "느리다"는 서버 TTFB 부터 분리 측정. SW 는 실제 Chrome 에서 검증.
- **점검 스킬(모든 도구 공통)**: SSOT `.cursor/skills/perf-guard/` · `perf-audit/`(중복 global `~/.codex/skills/perf-*` 금지). Claude=`/perf-guard`·`/perf-audit`(`.claude/commands` → SSOT 포인터), Cursor=동일 SKILL, Codex=repo cwd 에서 SSOT SKILL 또는 `python tools/perf/perf_scan.py`. 절차·체크리스트 `docs/guides/PERFORMANCE_GUARDRAILS.md` · `ERP_SLOWDOWN_RADAR.md`.

## 절대 규칙: 문제 수정 정책

- **근본 원인 수정만**: 문제 수정은 근본 원인(Root Cause)을 먼저 파악한 뒤 그것을 제거한다(클린코드 원칙). 증상만 덮는 수정, "일단 돌아가게" 하는 임시 조치, 워크어라운드, 더 높은 규칙으로 기존 코드 덮어쓰기는 정식 수정으로 제출하지 않는다.
- **금지 행위**: 에러 숨기기(`try/except: pass`, 빈 catch, 경고 무시, lint 비활성화, 로그 없는 fail-open) · 증상 우회(조건문으로 에러 경로만 회피, 하드코딩 값 삽입) · 구시대 방식(deprecated API, 레거시 패턴 복사, 폴리필 남용) · 미봉책(`# TODO: 나중에 고치기` 주석으로 대체).
- **프로세스**: 현상 확인(에러 메시지·로그·재현 조건 기록) → 근본 원인 분석(코드·데이터·환경 수준 추적) → 수정 설계 → 근본 원인을 제거하는 구현 → 원래 문제가 재현되지 않음을 검증. 디버깅 루프 상세는 `.claude/skills/diagnosing-bugs/SKILL.md`(버그를 빨강으로 만드는 단일 명령 먼저).
- **디버깅(Occam)**: 정확한 라인 매핑 우선, 국소 수정 우선, "고칠 수 있는가"보다 "없앨 수 있는가", "지금 보인다" ≠ "아까도 있었다"(Timing Gap 경계). 원인 100% 규명 전 가설 기반 대규모 리팩토링 금지.
- **예외 없음**: "긴급", "시간 부족"은 예외 사유가 아니다. 진짜 긴급 대응이 필요하면 임시 조치임을 명시적으로 선언하고 즉시 후속 근본 수정 계획을 문서화한다.

---

## 프로젝트 기본 정보

- **이름**: FOMS (Furniture Order Management System) — 가구 주문 관리 ERP. 워크플로우 RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION → CS → COMPLETED.
- **스택**: Flask 2.3 + SQLAlchemy 2.0 + PostgreSQL + Jinja2 + Bootstrap 5 + Vanilla JS. 코드 `foms/`(api·services·web·persistence·platform), 모델 `models.py`, 템플릿 `templates/`, 정적 `static/`. `app.py` 는 앱 초기화만(라우트 추가 금지, 새 API 는 `foms/api/` Blueprint).
- **배포**: Railway(PostgreSQL + Cloudflare R2). 서비스 web·WORKER·FOMS-cron·SIDEFX 4종, 환경변수가 서비스마다 다르다. 브랜치 `deploy`(스테이징) → `production`(운영).
- **운영 환경**: Windows 11 — **저장소 문서·예시 명령의 기본 셸은 PowerShell 5.x**(`.cursor/rules/50-win11-shell.mdc` 참고). bash/`&&` 등은 **Claude Code 전용**으로 문서에 명시된 때만 적용한다.
- **Git 커밋**: 한글, 무엇을 왜 수정했는지 명확히 기록. Windows cp949 때문에 UTF-8 파일로 저장해 `git commit -F <파일>` 로 커밋한다.
- **한글 출력 인코딩 (절대 규칙, 계약 `PS-ENC-01`)**: 한국어 로케일 Windows는 콘솔·프로세스 기본이 cp949다. ① 한글(비-ASCII)을 담은 `.ps1`은 **UTF-8 BOM 필수** — BOM이 없으면 PowerShell 5.1이 소스를 cp949로 디코드해 문자열이 깨지고 파싱 에러까지 난다. ② 같은 스크립트는 상단(`param` 블록 뒤)에서 콘솔 출력을 UTF-8로 강제한다: `$OutputEncoding = New-Object System.Text.UTF8Encoding $false` + `[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false`. ③ python은 `PYTHONIOENCODING=utf-8`·`PYTHONUTF8=1` 전제(Claude Code는 `.claude/settings.json` env에 등재) — 미설정 시 한글 출력이 mojibake가 되고 em-dash(`—`) 같은 비-cp949 문자는 `UnicodeEncodeError`로 스크립트가 죽는다. ④ 파일 입출력은 항상 `encoding="utf-8"` 명시. 강제: `tests/harness/test_powershell_encoding_contract.py` (pre_push_smoke 서브셋 포함).
- **실서버 측정 계정 `claude_master` (전 에이전트 공통 구속)**: 기본 테스트=staging(전 활동 허용), production=사용자 명시 요청 1건당 1회·관측만·기본 잠금(`is_active=false`)·실데이터 불가침(가상 주문 `CLAUDE-TEST-`+더미 연락처, 부하 테스트 금지). 정본: [`docs/guides/REAL_SERVER_TEST_ACCOUNT.md`](docs/guides/REAL_SERVER_TEST_ACCOUNT.md).

## 코딩 규약 (모든 도구 공통)

- **Python**: 함수 50줄 이하·한 가지 역할. docstring(목적·파라미터·반환값)·타입 힌트 필수(신규 함수). bare except 금지(구체적 예외 명시), 하드코딩 비밀키 절대 금지. API 응답 형식 통일 `{'success': True/False, 'data': ..., 'error': ...}`.
- **structured_data(JSONB) 수정 패턴 (필수)**:
  ```python
  import copy
  from sqlalchemy.orm.attributes import flag_modified
  sd = copy.deepcopy(order.structured_data or {})
  # ... 수정 ...
  order.structured_data = sd
  flag_modified(order, 'structured_data')
  db.commit()
  ```
- **Frontend**: 인라인 스타일 금지 → `static/css/foundation/erp-pro.css` 체계(ratchet 테스트 `tests/harness/test_harness_drift_guard.py` 가 개수 증가를 막는다). jQuery 금지 → `querySelector`·`fetch()`(try/catch + `data.success` 검증 필수). 인라인 script 300줄 초과 시 `.js` 분리, 템플릿 800줄 초과 시 partial 분리. Jinja2→JS 데이터는 `JSON.parse('{{ x|tojson }}')` 금지 → `data-*` 속성 + `safeJsonParse`.
- **Database**: PostgreSQL 15+, SQLAlchemy 2.0 ORM, Alembic. 마이그레이션은 autogenerate 후 수동 검토 + `downgrade()` 포함.

## 푸시 전 로컬 검증 (deploy/main)

`deploy` / `main` push **직전** 수동 실행: `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` (APP_OK, harness verify, SSOT lint, CI 자주 실패 pytest subset, ~2–5분). **UI/CSS/템플릿 변경 시** 기본 게이트는 PNG visual regression이 아니라 **`test_p1_mockup_*` 구조 테스트**(subset 포함). win32 PNG `--update-snapshots`·`-Visual`은 UI 안정기에만 선택. 머지 직전 전체 pytest: `-Full` (느림). **git push 시 자동 실행 아님** — GitHub Actions `test` job이 담당(PNG visual job 비활성). 상세: [`docs/guides/PRE_PUSH_SMOKE.md`](docs/guides/PRE_PUSH_SMOKE.md).

- **push 후 CI green 확인이 "push 완료"의 정의다(모든 도구·모델 공통) — 단, 확인은 논블로킹**: `deploy`/`production` 반영 후 `python tools/harness/ci_watch.py`(기본 HEAD·deploy; production은 `... HEAD production`)로 CI 완료를 감시한다. exit 0=green, **exit 1=코드 실패 → 근본 수정 → pre_push_smoke → 재푸시까지가 한 작업 단위**, exit 2=자동 재실행(재폴링), exit 3=gh 미설치/미인증. **블로킹 완주 대기 금지** — 백그라운드 실행하거나 `--quick`(폴링 없이 단발 조회: exit 0/1/3 + **4=진행 중**)으로 즉시 상태만 보고 작업을 계속한다. Claude Code는 push 감지 시 `post_push_watch` 훅이 논블로킹 안내를 주입하고, Cursor는 `afterShellExecution`이 기록한 마커를 `afterAgentResponse`가 소비해 매 턴 `--quick`을 직접 돌려 결과를 리마인드한다(진행 중이면 마커 유지 → 다음 턴 자동 재확인).

## 브랜치·푸시 권한 (절대 규칙)

- **기본 푸시 대상은 `deploy`(스테이징, lahom-dev)** 다. 흐름은 `deploy`(스테이징) → 사용자 검증·승인 → `production`(운영) 승격이다.
- **운영(`production`) 브랜치로의 push·force-push·reset은 사용자가 명시적으로 "production 푸시/배포"를 요청했을 때만** 수행한다. 어떤 도구·모델도 임의로 `production`에 푸시하지 않는다.
- **production 승격 기본 = 세션 자기 커밋 cherry-pick (절대 규칙)**: 사용자가 "커밋 모두 푸쉬", "전체 푸쉬", "deploy 전체 승격" 등 전체 반영을 **명시**하지 않는 한, production 승격은 **해당 LLM 작업 창(세션)이 이번 작업에서 만든 커밋만 cherry-pick**해 반영한다. deploy HEAD 전체 merge·push 금지. 여러 창이 같은 워킹트리·`deploy` 브랜치를 공유하므로 deploy HEAD에는 타 세션의 미검증 커밋이 섞여 있다 — 전체 승격은 스테이징/운영 구분을 붕괴시키고 운영을 오염시킨다.
- **cherry-pick 승격 절차**: ① 세션이 만든 커밋 SHA 목록을 `git log`로 직접 확정(타 세션 커밋 혼입 검사) ② **baseline 완전성 사전검사** — `python tools/harness/promote_completeness.py --shas <sha…>` (파일 교집합 × `git cherry +`만 missing; cherry-pick 동등 `-`는 제외). incomplete면 의존 포함/PC-only/중단을 사용자에게 확인 ③ `git fetch` + `git ls-remote`로 `origin/production` 정본 확인 ④ 짧은 경로(`c:/tmp`) worktree를 production 기반으로 생성 ⑤ 확정 SHA만 `git cherry-pick` ⑥ `gh pr create --base production` (직접 `HEAD:production` 푸시 금지). 헬퍼: `python tools/harness/promote_own_to_production.py --session-id <id>` (또는 `--shas`). **cherry-pick 충돌은 타 세션 커밋 의존 신호 → 임의 해결 금지**, 의존 커밋 포함 여부를 사용자에게 먼저 확인한다. 설계: `docs/specs/2026-07-22-promote-completeness-design.md`.
- **"deploy 푸쉬"는 절대 `production`을 포함하지 않는다.** 모호하면 푸시 전 사용자에게 대상 브랜치를 확인한다.
- **deploy push 세션 격리 (ask)**: 공유 워킹트리에서 `git push … deploy` 시 `origin/deploy..HEAD`에 타 세션/미확인 커밋이 있으면 훅이 **ask** 한다. 사용자 선택: (1) **전체 포함 승인** — 기존 push / (2) **자기 몫만** — `python tools/harness/push_own_session_commits.py --session-id <id>` (임시 worktree + cherry-pick, production 승격과 대칭). 커밋 시 세션 레저(`docs/harness/runtime/session_commit_ledger.json`)에 SHA가 기록된다. 설계: `docs/specs/2026-07-16-deploy-push-session-isolation-design.md`.
- **세션 worktree 격리 (선택 표준, 2026-07-27 Phase 1)**: 동시 2+창 코드 편집 시 `python tools/harness/session_worktree.py create` → 생성된 `c:/tmp/foms-s-*` 에서 작업한다(Claude CLI=`cd` 후 실행, Cursor=폴더 열기, Codex=`codex exec` cwd). deploy 반영은 `git push origin HEAD:deploy`, 종료 시 `cleanup`(dry-run 확인 → `--remove`). **강제 아님** — 단일 창·한 줄 수정·핫파일(tablet 계약테스트 2종·`layout_head.html`·`foms-tablet-bundle.css`)은 공유 트리 유지, 동시 권장 상한 2–3. 플랜: `docs/plans/2026-07-27-session-worktree-isolation-phase1.md`. 함정:
  - own=allow(ledger union 판정)는 **그 worktree 에서 에이전트를 새로 기동해야** 걸린다 — 메인 세션에서 `cd <worktree> && git push` 는 메인 트리 기준으로 분류해 안전측 ask 가 된다. 훅 없는 Codex 창은 ask 가 정상(전체 포함 승인은 그 worktree 커밋 전수 확인 후에만).
  - non-fast-forward 는 `session_worktree.py sync`(ledger 밖 커밋은 refuse — cherry-pick/merge 유입 세탁 차단).
  - worktree 에서는 alembic·dev 서버 startup DDL 이 코드 수준에서 차단된다. 메인 트리의 미커밋·미추적 파일은 worktree 로 넘어가지 않는다. worktree push 뒤 메인 트리 작업 전 `git pull --ff-only origin deploy`.
- `production` 강제푸시·히스토리 리라이트(reset)는 고위험이므로, 명시 승인과 함께 정확한 타깃 커밋·영향 범위를 먼저 보고하고 `--force-with-lease`로만 수행한다.
