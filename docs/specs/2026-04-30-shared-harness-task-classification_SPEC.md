# Shared Harness Task Classification Spec
> 작성일: 2026-04-30 | 상태: ✅ 완료

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
Cursor IDE 기본 에이전트, Cursor 안의 Codex/Claude 플러그인 운영 경로, Codex CLI 래퍼가 같은 결정적 분류 결과를 사용한다. 분류 결과는 사용자 프롬프트와 경로 힌트를 기준으로 `review / implement / qa / generic` 진입 유형, `low / medium / high / top` 작업 레벨, daily/harness 컨텍스트, 번들 경로, RPI 필요 여부, 사용자 방향 확인 필요 여부, 자원 힌트를 JSON으로 제공한다.

### 1.2 기능 요구사항
1. `tools/harness/task_classifier.py`를 공통 분류기로 추가한다.
2. 분류기는 기존 Cursor prompt router와 Codex Wave 3 레벨 판정의 핵심 규칙을 하나의 결정적 Python 구현으로 통합한다.
3. Cursor `beforeSubmitPrompt`는 공통 분류 결과를 사용해 기존 `agentMessage` 계약을 유지하면서 레벨·컨텍스트·RPI·사용자 확인 힌트를 포함한다.
4. `tools/harness/run_codex.ps1`는 공통 분류기의 JSON을 소비해 기존 출력 계약(`Level`, `AutoLevel`, `Override`, `RiskAck`)과 PowerShell 5 호환성을 유지한다.
5. Claude/Codex 플러그인 경로는 repo hook이 항상 보장되지 않으므로, 공통 분류 CLI를 공식 preflight로 문서화한다.
6. 고위험 downgrade는 기존처럼 대화형 확인 또는 `-AllowRiskyLevelOverride`를 요구한다.

### 1.3 예외/제약 조건
- 플러그인 채팅 내부에서 repo hook이 실행되지 않는 경우까지 숨은 자동 실행으로 보장하지 않는다.
- Cursor hook은 전체 bundle 본문을 자동 주입하지 않고, 짧은 `agentMessage`만 반환한다.
- 분류기는 LLM 선행 호출 없이 로컬 규칙으로 동작한다.
- DB 마이그레이션은 없다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `tools/harness/task_classifier.py` | 공통 분류기 및 `--json` CLI 추가 |
| `tools/harness/prompt_router.py` | 공통 분류기를 호출하도록 refactor |
| `tools/harness/run_codex.ps1` | 공통 분류 JSON을 소비하도록 refactor |
| `tests/harness/test_task_classifier.py` | 분류기 단위 테스트 추가 |
| `tests/harness/test_hooks_smoke.py` | Cursor hook 메시지 계약 갱신 |
| `tests/harness/test_run_codex_levels.py` | PowerShell 래퍼 출력 계약 유지 검증 |
| `docs/harness/policy/DECISIONS.md` | 단일 분류기 결정 기록 |
| `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md` | Cursor/Codex/Claude 공통 사용 경로 문서화 |
| `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/00-project-context.mdc` | runner별 공유 분류 정책 반영 |
| `docs/harness/bundles/HARNESS_BUNDLE_*.md` | source docs/rules 변경 후 재생성 |

### 2.2 아키텍처 방향
- 기존 `prompt_router.py`의 prompt/URL/path 추출 규칙과 `run_codex.ps1`의 Wave 3 레벨 규칙을 Python 공통 모듈로 수렴한다.
- PowerShell 래퍼는 파일 경로 resolve, Codex 실행, 콘솔 출력, 대화형 확인을 계속 담당한다.
- Cursor hook은 fail-open 정책을 유지한다.
- Claude/Codex 플러그인 창은 hook이 보장되지 않을 수 있으므로, 같은 분류 CLI를 수동 preflight로 사용하도록 안내한다.

### 2.3 의존성 및 영향 범위
- 직접 영향: Cursor hook, Codex wrapper, harness docs/rules, harness tests.
- 간접 영향: Claude/Codex 플러그인 운영 절차.
- 외부 의존성 추가 없음.

## 3. Steps — 실행 단계
- [x] Step 1: 공통 분류기 구현 및 CLI JSON 출력 추가.
- [x] Step 2: Cursor prompt router를 공통 분류기 기반으로 전환.
- [x] Step 3: Codex PowerShell 래퍼를 공통 분류기 JSON 소비 구조로 전환.
- [x] Step 4: 정책/운영 문서와 bundle source를 동기화하고 번들을 재생성.
- [x] Step 5: 단위/통합 테스트와 verify-result, APP_OK를 실행한다.

## 4. 검증 기준
- [x] `python -m pytest tests/harness/test_task_classifier.py tests/harness/test_hooks_smoke.py tests/harness/test_run_codex_levels.py -q` 통과
- [x] `python tools/harness/verify_result.py --json` 성공
- [x] `python -c "import app; print('APP_OK')"` 출력에 `APP_OK` 포함
- [x] `run_codex.ps1 -DryRun` 출력의 `Level`, `AutoLevel`, `Override`, `RiskAck` 계약 유지
- [x] Cursor `beforeSubmitPrompt`가 route kind와 task level을 포함한 `agentMessage`를 생성

## 5. 참고 자료
- 관련 결정: `docs/harness/policy/DECISIONS.md` — Prompt-side harness auto-entry routing, Wave 3 Codex auto level routing
- 관련 스펙: `docs/specs/2026-04-05-harness-auto-entry-routing_SPEC.md`
- 관련 스펙: `docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md`
