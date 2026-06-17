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
- **공통 작업 분류기**: `tools/harness/task_classifier.py`가 Cursor `beforeSubmitPrompt`, Codex 래퍼, Claude/Codex 플러그인 preflight의 단일 분류 기준이다. 출력은 `route_kind`, `level`, `context_mode`, 번들 경로, RPI·사용자 확인 필요 여부를 포함한다.
- **Wave 3 Codex wrapper**: `tools/harness/run_codex.ps1`는 작업을 `low / medium / high / top` 4단계로 자동 분류한다. 기본적으로 `low/medium`은 daily bundle, `high/top`은 `_HARNESS` bundle을 사용한다.
- **수동 override**: `-AdditionalPrompt "[level=top]"`, `-AdditionalPrompt "[레벨=최상]"`, `-AdditionalPrompt "이번 건 최상으로 진행"` 같은 형식을 지원한다.
- **고위험 downgrade 보호**: 자동 판정이 `high/top`인데 사용자가 더 낮은 레벨로 내리면, 대화형 확인이 필요하다. 비대화형 실행(CI 포함)은 `-AllowRiskyLevelOverride` 없이는 진행하지 않는다.

## 공통 실행 프로토콜 (핵심 코어 변경 시)

- **대상**: DB/Auth/API, 배포 인프라, 하네스 인프라(Hooks/Rules/Agents/검증 흐름) 같은 코어 변경
- **Research**: `docs/harness/policy/DECISIONS.md` + `docs/ARCHIVE_INDEX.md`를 먼저 조사한다.
- **Plan**: `docs/guides/SPEC_TEMPLATE.md` 기준으로 Spec 또는 실행 계획을 먼저 확정한다.
- **Implement**: 승인 후 구현하고, 완료 전 `.agents/workflows/verify-result.md` 기준으로 검증한다.
- **원칙**: 세부 절차는 도구별 문서(`CLAUDE.md`, `.cursor/rules/*.mdc`)가 보강할 수 있지만, 이 공통 프로토콜과 모순되면 안 된다.

## 절대 규칙: 성능 회귀 원천 차단
코드/기능 추가가 서버·페이지를 느리게 만드는 것을 **머지 전에 차단**한다(모든 도구·모델 공통). 상세·사유: `docs/guides/PERFORMANCE_GUARDRAILS.md`. 자동 강제: `tests/performance/test_perf_regression_guard.py`(`scripts/ops/pre_push_smoke.ps1`에 포함, exit 0 아니면 push 금지).
- **프론트 `<script>`는 기본 `defer`/`type=module`**. 렌더 차단 동기 스크립트·외부 CDN 동기 스크립트 신규 추가 금지(가드 G1/G2). 무거운 라이브러리는 사용 시점 lazy 로드, 공용 partial에 페이지 전용 무거운 JS 금지.
- **서비스워커 network-first fetch는 timeout+캐시 폴백 필수**(가드 G3). 무한 대기→탭 스피너 금지.
- **JSONB/text `cast(...).ilike` 인덱스 없이 hot path 금지**(부분일치=trigram, id=`@>`). **N+1 금지**(`in_(ids)` 배치), **매 요청 무거운 계산은 캐시**. 마이그레이션 CONCURRENTLY+다중 replica는 세션 레벨 advisory lock.
- **검증**: 대시보드/리스트/검색/액션 변경은 서버 TTFB 측정 + `EXPLAIN`로 Seq Scan 없음 확인. "느리다"는 서버 TTFB부터 분리 측정. SW는 실제 Chrome에서 검증.
- **점검 스킬(모든 도구 공통)**: 코드 수정 후 `python tools/perf/perf_scan.py --guard`(변경분 회귀 차단), 정기 점검은 `--audit`(전체 후보). 절차·체크리스트는 `docs/guides/PERFORMANCE_GUARDRAILS.md` §"점검 스킬 실행 절차". Claude=`/perf-guard`·`/perf-audit`, Cursor=`.cursor/commands/perf-*`, Codex=본 스크립트 직접 실행.

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

## 푸시 전 로컬 검증 (deploy/main)

`deploy` / `main` push **직전** 수동 실행: `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` (APP_OK, harness verify, SSOT lint, CI 자주 실패 pytest subset, ~2–5분). **UI/CSS/템플릿 변경 시** 기본 게이트는 PNG visual regression이 아니라 **`test_p1_mockup_*` 구조 테스트**(subset 포함). win32 PNG `--update-snapshots`·`-Visual`은 UI 안정기에만 선택. 머지 직전 전체 pytest: `-Full` (느림). **git push 시 자동 실행 아님** — GitHub Actions `test` job이 담당(PNG visual job 비활성). 상세: [`docs/guides/PRE_PUSH_SMOKE.md`](docs/guides/PRE_PUSH_SMOKE.md).
