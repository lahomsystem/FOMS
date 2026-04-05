# FOMS Cursor·Claude·Codex Harness Engineering 마스터 플랜

> **작성일**: 2026-04-05  
> **작성자**: FOMS GDM / AI Development System  
> **Goal**: Cursor IDE 안에서 Cursor Agent, Claude, Codex CLI가 동일한 정책·컨텍스트·검증 루프를 공유하는 하네스 엔지니어링 체계를 구축한다.  
> **Architecture**: gstack의 강점(브라우저 QA/릴리즈/문서 동기화/운영 하네스)과 FOMS의 강점(Root Cause Fix, RPI, Hooks, Context Docs, GDM 오케스트레이션)을 혼합한 Hybrid 구조를 채택한다.  
> **Tech Stack**: Cursor IDE, Claude, Codex CLI, Python 3.12, PowerShell 5+/7, Git Bash(선택), Bun/Node(선택적 gstack 런타임), GitHub Actions  
> **상태**: Phase 1 완료 / Phase 2 진행중  
> **권장안**: Option C - Hybrid gstack + FOMS harness

---

## 0. 배경 및 목적

### 0.1 왜 이 작업이 필요한가

- 현재 사용 환경은 **Cursor IDE + Claude + Codex CLI**의 혼합 운용이다.
- FOMS는 이미 `.cursor/rules`, `.cursor/hooks`, `.cursor/agents`, `.agents/workflows`, `docs/context/*` 기반의 강한 운영정책을 가지고 있다.
- 그러나 현재 구조는 **Cursor 중심**으로 설계되어 있어, Claude나 Codex CLI가 같은 수준의 정책·기억·검증 시스템을 자동 재사용하기 어렵다.
- gstack은 하네스 엔지니어링 측면에서 매우 강력하지만, FOMS의 Windows 11 / PowerShell / Cursor 브라우저 MCP / 도메인 정책과 그대로 맞물리지는 않는다.

### 0.2 목표

1. Cursor, Claude, Codex가 **같은 정책 그래프**를 읽게 한다.
2. gstack과 FOMS의 장점을 합쳐 **중복 없는 하네스**를 만든다.
3. 브라우저 QA, 리뷰, 출하 전 검증, 문서/컨텍스트 동기화를 **재현 가능한 시스템**으로 만든다.
4. Windows 11 + PowerShell + Cursor 환경에서 실제로 유지 가능한 구조를 만든다.
5. 하네스 자체도 테스트와 CI로 검증 가능하게 만든다.

### 0.3 비목표

- Flask 앱 기능 변경을 동시에 진행하지 않는다.
- gstack의 모든 규칙을 FOMS 위에 그대로 덮어씌우지 않는다.
- Cursor용 정책, Claude용 정책, Codex용 정책을 손으로 따로 유지하지 않는다.

### 0.4 완료 정의 (Definition of Done)

- `AGENTS.md` / `CLAUDE.md` / `.cursor/rules/*.mdc`가 **정식 정책 원본**으로 정리된다.
- Codex CLI용 컨텍스트 번들이 **자동 생성**된다.
- gstack는 repo-local로 도입되되, **명확한 역할**만 가진다.
- Cursor 훅과 Codex/CLI용 대체 검증 루틴이 분리 설계된다.
- 사용자가 Cursor 안에서 Cursor Agent / Claude / Codex 각각을 **정해진 진입점**으로 바로 사용할 수 있다.

---

## 1. 현재 상태 (AS-IS)

### 1.1 이미 강한 부분

| 카테고리 | 현재 자산 | 핵심 파일 |
|------|------|------|
| 공통 정책 | Root Cause Fix, 금지 패턴, Git/Win11 규칙 | `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/*.mdc` |
| 에이전트 역할 | GDM + 역할별 서브에이전트 분리 | `.cursor/agents/*.md` |
| 훅 자동화 | 세션 시작/종료, 쉘 가드, 편집 로그, 품질 리마인더 | `.cursor/hooks.json`, `.cursor/hooks/*.py` |
| 컨텍스트 기억 | 상태/변경/세션/압축 로그 | `docs/AI_STATUS.md`, `docs/AI_CHANGELOG.md`, `docs/context/*` |
| 워크플로 | RPI, verify-result, auto-status-update | `.agents/workflows/*.md` |
| 테스트 기반 | 기본 pytest CI 존재 | `.github/workflows/ci.yml`, `tests/` |

### 1.2 현재 약한 부분

1. **Cursor 밖 runner**에 대한 정식 하네스 진입점이 없다.
2. Codex CLI가 읽어야 하는 정책 묶음이 **자동 생성되지 않는다**.
3. 브라우저 QA, canary, benchmark, release gate가 **문서/수동 절차** 중심이다.
4. 훅 구현 일부가 프로젝트 정책과 충돌한다.
5. 스킬/정책/워크플로의 **drift 검증**이 약하다.
6. `.cursor/skills`는 방대하지만, 실제 **하네스 코어**와 **보조 스킬**의 경계가 흐리다.

---

## 2. gstack 분석 요약

### 2.1 gstack에서 직접 가져올 가치

- 장수 브라우저 세션 기반 QA/Review 철학
- `/qa`, `/benchmark`, `/canary`, `/document-release` 같은 **릴리즈 트레인 사고방식**
- 스킬 문서와 명령 체계를 **자동 동기화**하려는 설계
- 운영 학습, 리뷰 준비도, 공통 프리앰블 같은 **하네스 일체화**

### 2.2 gstack를 그대로 도입하면 충돌하는 지점

- gstack는 기본적으로 `/browse` 중심 브라우저 사용을 강하게 권장하지만, FOMS는 이미 **Cursor 브라우저 MCP** 기반 운영 패턴이 있다.
- Windows에서는 Git Bash/WSL + Bun/Node 전제가 있어, PowerShell 중심 FOMS와 마찰이 있다.
- FOMS는 이미 `AGENTS.md`, `CLAUDE.md`, `.cursor/rules`, `.cursor/hooks`라는 **강한 상위 정책층**을 보유하고 있어, gstack 정책을 그대로 넣으면 중복된다.

### 2.3 채택 / 유지 / 제외 방침

| 분류 | 내용 |
|------|------|
| 채택 | repo-local skill/vendor 개념, QA/benchmark/canary/release flow, 문서 drift 방지 철학 |
| FOMS 유지 | Root Cause Fix, RPI, Hooks, Context Docs, GDM 오케스트레이션, Win11/PowerShell 규칙 |
| 수정 채택 | gstack 브라우저는 **반복 가능한 QA용**으로 한정하고, ad-hoc 탐색은 Cursor 브라우저 MCP 유지 |
| 제외 | "모든 브라우징을 gstack로 통일" 같은 전면 교체 정책 |

---

## 3. 아키텍처 선택지 비교

| 옵션 | 설명 | 장점 | 리스크 | 결론 |
|------|------|------|------|------|
| Option A | gstack 전격 도입, FOMS는 상단 규칙만 최소 유지 | 빠르게 강한 하네스 획득 | 정책 충돌, Windows/Git Bash 의존, FOMS 문맥 손실 | 비권장 |
| Option B | FOMS 자산만으로 하네스 재구현 | 완전한 자율성, Windows 친화 | 구현량 큼, 검증까지 오래 걸림 | 보조안 |
| Option C | gstack + FOMS 혼합, 역할 분리 | 현실적, 기존 자산 보존, 단계적 도입 가능 | 경계 설계가 중요 | **권장** |

### 최종 선택

**Option C - Hybrid gstack + FOMS harness**를 채택한다.

핵심 원칙은 다음과 같다.

1. **정책 원본은 FOMS가 가진다.**
2. **gstack는 런타임/QA/릴리즈 패턴 공급자**로 쓴다.
3. **Cursor / Claude / Codex는 진입점만 다르고 정책은 같아야 한다.**

---

## 4. 목표 아키텍처 (TO-BE)

```text
사용자 (Cursor IDE)
   │
   ├─ Cursor Agent
   ├─ Claude in Cursor
   └─ Codex CLI in Cursor Terminal
           │
           ▼
   Runner Profile Layer
   - cursor profile
   - claude profile
   - codex profile
           │
           ▼
   Harness Core
   - AGENTS.md
   - CLAUDE.md
   - .cursor/rules
   - .cursor/agents
   - .agents/workflows
   - docs/context
           │
           ├─ Cursor Hooks
           ├─ Bundle Generator
           ├─ Verification Scripts
           └─ gstack Runtime Adapters
                   │
                   ▼
   Outputs
   - generated context bundles
   - verify results
   - session/context logs
   - QA / benchmark / canary artifacts
```

### 4.1 단일 정책 그래프 (Single Source of Truth)

- `AGENTS.md`: 전 도구 공통 최상위 원칙
- `CLAUDE.md`: Claude 중심 세션 프로토콜
- `.cursor/rules/*.mdc`: Cursor 강제 규칙
- `.cursor/agents/*.md`: 역할별 지능 분리
- `.agents/workflows/*.md`: 실행 절차
- `docs/context/*`: 운영 메모리와 결정 로그

### 4.2 Runner Profile 계층 (신규)

Runner별로 “무슨 파일을 읽고, 무슨 절차를 강제하며, 무엇을 생략할지”를 선언형으로 관리한다.

예상 파일:

- `tools/harness/profiles/cursor.yaml`
- `tools/harness/profiles/claude.yaml`
- `tools/harness/profiles/codex.yaml`

### 4.3 gstack Vendor Zone (신규)

repo-local로 gstack를 도입하되, FOMS 하네스 바깥이 아닌 **관리 가능한 vendor zone**으로 둔다.

예상 위치:

- `.agents/skills/gstack/`

원칙:

- upstream 원본은 vendored 상태로 보존
- FOMS 전용 정책은 gstack 내부를 수정하지 않고 **브리지 레이어**에서 덮는다
- 필요 시 subtree 또는 copy-vendor 방식 중 하나를 선택한다

### 4.4 브라우저 역할 분리

| 용도 | 주 도구 |
|------|------|
| 빠른 탐색 / 화면 확인 / 디버그 | Cursor 브라우저 MCP |
| 반복 QA / release smoke / canary / benchmark | gstack 기반 브라우저 런타임 |

이 분리를 문서와 규칙에 명시하여, 브라우저 하네스 충돌을 방지한다.

---

## 5. 생성/수정 대상 파일 설계도

### 5.1 신규 생성 예정

- `.agents/skills/gstack/`
- `tools/harness/manifest.yaml`
- `tools/harness/build_context_bundle.py`
- `tools/harness/setup_gstack.ps1`
- `tools/harness/run_codex.ps1`
- `tools/harness/run_gstack_qa.ps1`
- `tools/harness/profiles/cursor.yaml`
- `tools/harness/profiles/claude.yaml`
- `tools/harness/profiles/codex.yaml`
- `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
- `docs/context/HARNESS_BUNDLE_CURSOR.md` (generated)
- `docs/context/HARNESS_BUNDLE_CLAUDE.md` (generated)
- `docs/context/HARNESS_BUNDLE_CODEX.md` (generated)
- `tests/harness/test_context_bundle.py`
- `.github/workflows/harness-ci.yml`

### 5.2 수정 예정

- `AGENTS.md`
- `CLAUDE.md`
- `.cursor/rules/00-project-context.mdc`
- `.cursor/rules/50-win11-shell.mdc`
- `.cursor/hooks.json`
- `.cursor/hooks/session_stop.py`
- `.cursor/hooks/auto_memory.py`
- `.cursor/hooks/post_task_quality_check.py`
- `.cursor/hooks/hook_payload_debug.py`
- `.cursor/agents/grand-develop-master.md`
- `.agents/workflows/verify-result.md`
- `docs/context/DECISIONS.md` (승인 후 결정 기록)
- `docs/ARCHIVE_INDEX.md`

### 5.3 유지하되 역할 명확화

- `.cursor/skills/` 전체
- `docs/AI_STATUS.md`
- `docs/AI_CHANGELOG.md`
- `docs/context/SESSION_LOG.md`
- `docs/context/EDIT_LOG.md`

---

## 6. 구현 Phase 설계

## Phase 0 — 정책 정합성 정리

**목표**: FOMS 내부 정책 충돌을 먼저 정리한다.

**핵심 작업**

- [x] 훅 예외 처리 정책과 `Root Cause Fix` 정책의 충돌 정리
- [x] `sessionEnd` / `stop` 이중 실행 가능성 정리
- [x] Cursor / Claude / Codex의 역할과 진입점 문서화
- [x] 브라우저 소유권 정책 확정
- [x] `OK` / `APP_OK` / 기타 성공 문자열을 단일 canonical 출력으로 통일
- [x] PowerShell 5.x 기준과 `pwsh` 선택 사용 기준을 문서로 고정

**대상 파일**

- `AGENTS.md`
- `CLAUDE.md`
- `.cursor/rules/00-project-context.mdc`
- `.cursor/rules/50-win11-shell.mdc`
- `.cursor/hooks.json`
- `.cursor/hooks/*.py`
- `.agents/workflows/verify-result.md`

**검증**

- `python -m compileall .cursor/hooks`
- `python -c "import app; print('APP_OK')"`
- 동일 세션 종료 조건에서 `session_stop.py`가 2회 호출되어도 `SESSION_LOG.md`와 `AI_CHANGELOG.md`가 중복 오염되지 않는지 확인
- Hook 실패 시 조용히 삼키지 않고 최소한의 운영 로그 또는 컨텍스트 로그가 남는지 확인
- PowerShell 5.x 기준 명령 예시와 `pwsh` 예시가 문서상 충돌하지 않는지 확인

## Phase 1 — Harness Core Manifest + Bundle Generator

**목표**: Codex/Claude/Cursor가 읽을 공통 컨텍스트 번들을 자동 생성한다.

**핵심 작업**

- [x] `manifest.yaml`로 정책 원본과 생성 규칙 정의
- [x] `build_context_bundle.py` 작성
- [x] runner profile 3종 정의
- [x] generated bundle test 추가

**대상 파일**

- `tools/harness/manifest.yaml`
- `tools/harness/build_context_bundle.py`
- `tools/harness/profiles/*.yaml`
- `tests/harness/test_context_bundle.py`

**검증**

- `python tools/harness/build_context_bundle.py --all`
- `pytest tests/harness -q`

## Phase 2 — gstack Vendor + Adapter Layer

**목표**: gstack를 전격 도입하되 FOMS 하네스와 충돌 없이 붙인다.

**핵심 작업**

- [ ] `.agents/skills/gstack/` repo-local vendor 도입
- [ ] PowerShell에서 Git Bash/WSL을 안전하게 호출하는 `setup_gstack.ps1` 작성
- [ ] gstack QA/benchmark/canary 전용 래퍼 스크립트 작성
- [ ] FOMS overlay 정책 문서화

**대상 파일**

- `.agents/skills/gstack/`
- `tools/harness/setup_gstack.ps1`
- `tools/harness/run_gstack_qa.ps1`
- `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`

**검증**

- `powershell -NoProfile -File tools/harness/setup_gstack.ps1 -WhatIf`
- `powershell -NoProfile -File tools/harness/run_gstack_qa.ps1 -DryRun`
- `pwsh`가 설치된 환경에서는 동일 명령이 호환되는지 추가 확인

## Phase 3 — Cursor / Claude / Codex Runner Experience

**목표**: 사용자가 어떤 runner를 써도 동일한 하네스를 체감하게 만든다.

**핵심 작업**

- [ ] Cursor profile 적용 규칙 작성
- [ ] Claude in Cursor 전용 운영 섹션 정리
- [ ] Codex CLI wrapper와 generated context 연결
- [ ] GDM에서 runner별 실행 트랙 설명 가능하도록 보강

**대상 파일**

- `CLAUDE.md`
- `.cursor/rules/*.mdc`
- `.cursor/agents/grand-develop-master.md`
- `tools/harness/run_codex.ps1`
- `docs/context/HARNESS_BUNDLE_*.md`

**검증**

- Cursor chat dry run 1회
- Claude dry run 1회
- Codex CLI dry run 1회

## Phase 4 — Verification / CI / Drift Control

**목표**: 하네스 자체가 깨지지 않게 만든다.

**핵심 작업**

- [ ] harness 전용 CI workflow 추가
- [ ] generated bundle drift check 추가
- [ ] 훅 단위 테스트 또는 smoke test 추가
- [ ] verify-result를 스크립트화할지 결정

**대상 파일**

- `.github/workflows/harness-ci.yml`
- `tests/harness/*`
- `.agents/workflows/verify-result.md`

**검증**

- GitHub Actions green
- bundle regenerate diff clean

## Phase 5 — 운영 문서 / 팀 사용법 정착

**목표**: 사용자가 실제로 매일 쓸 수 있게 정리한다.

**핵심 작업**

- [ ] 운영자 가이드 작성
- [ ] runner별 시작 예시 추가
- [ ] 장애 시 fallback 경로 정리
- [ ] 새 계획/결정 파일 인덱싱 절차 반영

---

## 7. 병렬 에이전트 실행 구조

이 작업은 다음 4개 트랙으로 병렬화한다.

| 트랙 | 담당 에이전트 후보 | 범위 |
|------|------|------|
| Track A | `devops-deploy` | gstack vendor, PowerShell/Git Bash bridge, setup scripts |
| Track B | `python-backend` | hooks 정합성 수정, bundle generator, verify 스크립트 |
| Track C | `evolution-architect` | 정책 통합, runner profile 설계, hybrid 원칙 고도화 |
| Track D | `code-reviewer` | 하네스 자체 품질 게이트, drift/리스크 검토 |

원칙:

1. 같은 파일을 동시에 수정하는 병렬 작업은 금지한다.
2. Phase 0 완료 전에는 vendor 도입이나 runner wrapper 구현을 merge하지 않는다.
3. 각 Track는 결과를 `docs/context/DECISIONS.md` 또는 계획 문서에 반영 가능한 형태로 반환해야 한다.

---

## 8. 구현 후 사용 방법 (예정 운영 UX)

### 8.1 Cursor Agent in Cursor Chat

예정 사용 방식:

1. 계획서 또는 Spec를 열고 Cursor Chat에 참조한다.
2. 다음처럼 요청한다.

```text
GDM 방향 제시: @docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md
Phase 1부터 subagent-driven으로 실행해 줘
```

### 8.2 Claude in Cursor

예정 사용 방식:

1. `CLAUDE.md`와 generated bundle을 기준으로 세션을 시작한다.
2. 다음처럼 요청한다.

```text
@docs/context/HARNESS_BUNDLE_CLAUDE.md 를 기준으로
현재 브랜치 하네스 변경안 리뷰 후 Phase 2 작업 착수
```

### 8.3 Codex CLI in Cursor Terminal

예정 사용 방식:

```powershell
powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "AGENTS.md"
powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile implement -Plan "docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md"
powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" -Url "https://staging.example.com" -Scenario "erp-smoke"
```

`pwsh`가 설치된 환경에서는 `pwsh -File ...` 사용도 허용하되, 문서 기본값은 **Windows 기본 PowerShell 5.x 호환 예시**로 유지한다.

### 8.4 브라우저 사용 원칙

- 빠른 탐색 / 구조 확인: Cursor 브라우저 MCP
- 반복 회귀 / release smoke / canary / benchmark: gstack runtime

---

## 9. 리스크와 대응

| 리스크 | 설명 | 대응 |
|------|------|------|
| 정책 drift | Cursor/Claude/Codex 설명이 서로 달라짐 | generated bundle + manifest + CI diff check |
| Windows 마찰 | PowerShell, Git Bash, Bun/Node 혼합 | wrapper 스크립트로 표준화 |
| 훅 의존성 | Cursor 훅은 Codex CLI에서 자동 실행되지 않음 | Codex wrapper에 preflight/postflight 추가 |
| 브라우저 충돌 | Cursor MCP와 gstack browse가 서로 역할을 침범 | 사용 목적을 문서로 고정 |
| 하네스 비대화 | `.cursor/skills`와 gstack가 함께 비대해짐 | harness core vs optional skills 분리 |

---

## 10. 최종 권고

지금 단계에서 가장 현실적인 구현 순서는 다음과 같다.

1. **Phase 0**: 정책 충돌 제거
2. **Phase 1**: bundle generator + runner profile 구축
3. **Phase 2**: gstack vendor + adapter 도입
4. **Phase 3~4**: Codex/Claude/Cursor runner UX와 CI 고도화

즉, **gstack를 먼저 넣고 나중에 맞추는 방식**이 아니라,  
**FOMS 하네스 코어를 먼저 정리한 뒤 gstack를 연결하는 방식**이 정답이다.

이 순서를 지켜야 Cursor, Claude, Codex가 동시에 쓰여도 정책이 흐트러지지 않는다.
