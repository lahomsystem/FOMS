# FOMS 프로젝트 — AI 에이전트 공통 규칙

이 파일은 **어떤 IDE(Cursor, VS Code, JetBrains 등)**, **어떤 LLM 모델(Claude, GPT, Gemini, Codex 등)**을 사용하더라도 반드시 준수해야 하는 규칙을 정의한다.

---

## 하네스 정책 단일 기준 (Cursor · Claude · Codex 공통)

- **이식 가능한 기준선**: 본 파일(`AGENTS.md`)이 모든 도구에서 공유하는 정책의 기준이다. Codex·기타 CLI는 여기를 우선한다.
- **Cursor**: `.cursor/rules/`(특히 `00-project-context.mdc`)가 IDE 컨텍스트로 보강하며, **기준선과 충돌하면 안 된다.**
- **Claude Code**: 루트 `CLAUDE.md`가 세션 규칙으로 보강한다. **Unix/bash 예시는 “Claude Code 전용”으로 명시된 경우에만** 따른다(저장소 문서 기본값은 아래 셸 규칙).
- **앱 import 검증 성공 문자열(표준)**: `APP_OK` — `python -c "import app; print('APP_OK')"` 로 확인한다.
- **브라우저**: 탐색·수동 재현·디버깅은 **Cursor browser MCP**. 반복 가능한 QA·릴리스 스모크용 **gstack browse** 런타임은 로컬 setup가 완료된 경우 사용하고, setup 전에는 미도입으로 본다.
- **훅 fail-open**: 세션을 막지 않기 위해 예외를 삼키는 방식은 **실패가 로그 등으로 남는 경우에만** 허용한다. **묵시적 무시(조용한 swallow)는 금지**한다.
- **작업 레벨·RPI 판단**: 작업 레벨·RPI 판단은 문서 규칙(CLAUDE.md 새 세션 시작 프로토콜)을 따르고, 코어 변경 게이트는 Stop 훅·pre_push_smoke·branch protection이 코드로 강제한다.

## 공통 실행 프로토콜 (핵심 코어 변경 시)

- **대상**: DB/Auth/API, 배포 인프라, 하네스 인프라(Hooks/Rules/Agents/검증 흐름) 같은 코어 변경
- **Research**: `docs/harness/policy/DECISIONS.md` + `docs/ARCHIVE_INDEX.md`를 먼저 조사한다.
- **Plan**: `docs/guides/SPEC_TEMPLATE.md` 기준으로 Spec 또는 실행 계획을 먼저 확정한다.
- **Implement**: 승인 후 구현하고, 완료 전 `.agents/workflows/verify-result.md` 기준으로 검증한다.
- **원칙**: 세부 절차는 도구별 문서(`CLAUDE.md`, `.cursor/rules/*.mdc`)가 보강할 수 있지만, 이 공통 프로토콜과 모순되면 안 된다.

## 절대 규칙: 성능 회귀 원천 차단
코드/기능 추가가 서버·페이지를 느리게 만드는 것을 **머지 전에 차단**한다(모든 도구·모델 공통). 상세·사유: `docs/guides/PERFORMANCE_GUARDRAILS.md`. 자동 강제: `tests/performance/test_perf_regression_guard.py`(`scripts/ops/pre_push_smoke.ps1`에 포함, exit 0 아니면 push 금지).
- **프론트 `<script>`는 기본 `defer`/`type=module`**. 렌더 차단 동기 스크립트·외부 CDN 동기 스크립트 신규 추가 금지(가드 G1/G2). 무거운 라이브러리는 사용 시점 lazy 로드, 공용 partial에 페이지 전용 무거운 JS 금지.
- **ERP shell fragment에서 재실행되는 JS는 idempotent 필수**(가드 G4). 모바일 shell/P2 bundle에 추가되는 JS가 `window`/`document`/`body` 전역 listener를 걸면 `window.__*_BOUND` 같은 singleton guard로 중복 바인딩을 막는다.
- **서비스워커 network-first fetch는 timeout+캐시 폴백 필수**(가드 G3). 무한 대기→탭 스피너 금지.
- **JSONB/text `cast(...).ilike` 인덱스 없이 hot path 금지**(부분일치=trigram, id=`@>`). **N+1 금지**(`in_(ids)` 배치), **매 요청 무거운 계산은 캐시**. 마이그레이션 CONCURRENTLY+다중 replica는 세션 레벨 advisory lock.
- **검증**: 대시보드/리스트/검색/액션 변경은 서버 TTFB 측정 + `EXPLAIN`로 Seq Scan 없음 확인. "느리다"는 서버 TTFB부터 분리 측정. SW는 실제 Chrome에서 검증.
- **점검 스킬(모든 도구 공통)**: SSOT `.cursor/skills/perf-guard/` · `perf-audit/` (중복 global `~/.codex/skills/perf-*` 금지). Claude=`/perf-guard`·`/perf-audit`(`.claude/commands` → SSOT 포인터), Cursor=동일 SKILL, Codex=repo cwd에서 SSOT SKILL 또는 `python tools/perf/perf_scan.py` 직접 실행. 절차·체크리스트 `docs/guides/PERFORMANCE_GUARDRAILS.md` · `ERP_SLOWDOWN_RADAR.md`.

## 절대 규칙: 문제 수정 정책

### 1. 근본 원인 파악 → 근본 수정 (Root Cause Fix Only)
- 문제 수정 시 **반드시 근본 원인(Root Cause)을 먼저 파악**한 뒤 수정한다.
- 코드 수정이나 문제 해결 시, 임시적인 방법(우회, 더 높은 규칙 적용으로 기존 코드 덮어쓰기 등)이나 근본 문제 해결 없는 수정은 **절대 금지**한다.
- **무조건 근본적인 해결(클린코드 원칙 입각)**을 하도록 수정해야 한다.
- 증상만 덮는 수정이나 "일단 돌아가게" 하는 임시 조치, 워크어라운드를 정식 수정으로 제출하지 않는다.

### 2. 금지 행위
- **에러 숨기기 금지**: `try/except: pass`, 빈 catch, 경고 무시, lint 비활성화 (훅의 fail-open도 **로그 없는** 실패 삼킴은 동일하게 금지)
- **증상 우회 금지**: 조건문으로 에러 경로만 회피, 하드코딩 값 삽입
- **구시대 방식 적용 금지**: deprecated API 사용, 레거시 패턴 복사, 폴리필 남용
- **미봉책 금지**: `# TODO: 나중에 고치기` 식의 주석으로 대체

### 3. 수정 프로세스 (필수 순서)
1. **현상 확인** — 에러 메시지, 로그, 재현 조건을 정확히 기록
2. **근본 원인 분석** — 왜 발생하는지 코드·데이터·환경 수준에서 추적
3. **수정 설계** — 올바른 현대적 방법으로 해결책 설계
4. **수정 구현** — 근본 원인을 제거하는 코드 작성
5. **검증** — 수정 후 원래 문제가 재현되지 않음을 확인

### 4. 예외 없음
- "긴급", "시간 부족"은 이 규칙의 예외 사유가 될 수 없다.
- 진짜 긴급 대응이 필요하면, 임시 조치임을 **명시적으로 선언**하고 즉시 후속 근본 수정 계획을 문서화한다.

---

## 프로젝트 기본 정보
- **이름**: FOMS (Furniture Order Management System)
- **스택**: Flask 2.3 + SQLAlchemy 2.0 + PostgreSQL + Jinja2 + Bootstrap 5 + Vanilla JS
- **운영 환경**: Windows 11 — **저장소 문서·예시 명령의 기본 셸은 PowerShell 5.x**(`.cursor/rules/50-win11-shell.mdc` 참고). bash/`&&` 등은 **Claude Code 전용**으로 문서에 명시된 때만 적용한다.
- **Git 커밋**: 한글, 무엇을 왜 수정했는지 명확히 기록
- **한글 출력 인코딩 (절대 규칙, 계약 `PS-ENC-01`)**: 한국어 로케일 Windows는 콘솔·프로세스 기본이 cp949다. ① 한글(비-ASCII)을 담은 `.ps1`은 **UTF-8 BOM 필수** — BOM이 없으면 PowerShell 5.1이 소스를 cp949로 디코드해 문자열이 깨지고 파싱 에러까지 난다. ② 같은 스크립트는 상단(`param` 블록 뒤)에서 콘솔 출력을 UTF-8로 강제한다: `$OutputEncoding = New-Object System.Text.UTF8Encoding $false` + `[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false`. ③ python은 `PYTHONIOENCODING=utf-8`·`PYTHONUTF8=1` 전제(Claude Code는 `.claude/settings.json` env에 등재) — 미설정 시 한글 출력이 mojibake가 되고 em-dash(`—`) 같은 비-cp949 문자는 `UnicodeEncodeError`로 스크립트가 죽는다. ④ 파일 입출력은 항상 `encoding="utf-8"` 명시. 강제: `tests/harness/test_powershell_encoding_contract.py` (pre_push_smoke 서브셋 포함).
- **실서버 측정 계정 `claude_master` (전 에이전트 공통 구속)**: 기본 테스트=staging(전 활동 허용), production=사용자 명시 요청 1건당 1회·관측만·기본 잠금(`is_active=false`)·실데이터 불가침(가상 주문 `CLAUDE-TEST-`+더미 연락처, 부하 테스트 금지). 정본: [`docs/guides/REAL_SERVER_TEST_ACCOUNT.md`](docs/guides/REAL_SERVER_TEST_ACCOUNT.md).

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
- **세션 worktree 격리 (선택 표준, 2026-07-27 Phase 1)**: 동시 2+창 코드 편집 시 `python tools/harness/session_worktree.py create` → 생성된 `c:/tmp/foms-s-*`에서 작업한다(Claude CLI=`cd` 후 실행, Cursor=폴더 열기, Codex=`codex exec` cwd). deploy 반영은 `git push origin HEAD:deploy` — 세션 worktree는 ledger **union 판정**으로 own=allow, 훅 없는 Codex 창은 ask가 정상(전체 포함 승인은 그 worktree 커밋 전수 확인 후에만). **union own=allow는 그 worktree에서 에이전트를 새로 기동해야 걸린다** — 메인 세션에서 `cd <worktree> && git push`로는 훅이 메인 트리 기준으로 분류해 안전측 ask가 된다. non-fast-forward 시 `session_worktree.py sync`(ledger 밖 커밋은 refuse — cherry-pick/merge 유입 세탁 차단). 종료 시 `cleanup`(dry-run 확인 → `--remove`). **강제 아님**: 단일 창·한 줄 수정·핫파일(tablet 계약테스트 2종·`layout_head.html`·`foms-tablet-bundle.css`) 작업은 공유 트리 유지, 동시 권장 상한 2–3. 세션 worktree에서 alembic·dev 서버 startup DDL은 코드 수준 차단됨. worktree push 후 메인 트리 작업 전 `git pull --ff-only origin deploy`. 메인 트리 미커밋/미추적 파일은 worktree로 넘어가지 않는다. 플랜: `docs/plans/2026-07-27-session-worktree-isolation-phase1.md`.
- `production` 강제푸시·히스토리 리라이트(reset)는 고위험이므로, 명시 승인과 함께 정확한 타깃 커밋·영향 범위를 먼저 보고하고 `--force-with-lease`로만 수행한다.
