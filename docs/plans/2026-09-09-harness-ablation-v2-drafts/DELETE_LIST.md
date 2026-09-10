# 삭제·비활성·정정 목록 (사용자가 실행, ablation v2 2026-09-09)

## 0. 결정 (2026-09-10 적용 세션, 보고서 ⑥ 열린 질문 8개 — 사용자 답변)

| # | 질문 | 결정 | 적용 방식 |
|---|---|---|---|
| 1 | orca 훅 10이벤트 | **유지** | §9 orca 항목 제외. 전역 hooks 무변경 |
| 2 | caveman 플러그인 | **유지 그대로** | §9 caveman 항목 제외. `CLAUDE.md:6` 후반(caveman 축약보다 한자 금지 우선) 문장 유지 |
| 3 | 브라우저 QA 정본 | **둘 다 쓴다** | 탐색·수동 재현 = Cursor browser MCP, 반복 QA·릴리스 스모크 = gstack browse. `AGENTS.md:13` 의 "setup 전 미도입" 조건 삭제, `CLAUDE.md` 는 AGENTS.md 포인터 1줄 |
| 4-가 | superpowers 벤더링 | **Opus 5 실측 뒤 결정** | `abl_run.py --model claude-opus-5` 로 T2·T4 팔 A/B 4회 실행 → 결과 보고 → 재질문. 그때까지 플러그인 on, 상쇄 문장(전역:33·프로젝트 brainstorming 예외) 유지, 드리프트 가드의 superpowers 테스트 보류 |
| 4-나 | gstack 스킬 57종 | **핵심만 남김** | 유지: `gstack`·`_gstack-command`(라우터)·browse·qa·qa-only·design-review·review·investigate·upgrade. 나머지 삭제(`gstack-upgrade` 로 재설치 가능) |
| 5 | 등급 마커 6줄 | **동의(1줄 + 포인터)** | `CLAUDE.md` 는 마커 선언 1줄 + `docs/guides/LONG_TASK_PROMPTS.md` 포인터 |
| 6 | 권한 ask 실측·allowlist 정정 | **둘 다 안 함** | §1 의 `settings.local.json` 행 제외(youtube 유지·solapi 미추가). ask 실측 안 함 |
| 7 | 메모리 약 107건 삭제 | **전수 확인** | 154건 각각 규칙(①유도 가능 ②참조 소멸 → 삭제, feedback·reference 유지) 판정표를 원장에 남기고 삭제. 삭제 전 `c:/tmp/memory-baseline-20260910` 백업 |
| 8 | 실험 부산물 | **전부 정리** | 3단계에서 `abl_cleanup.sh` 실행(Opus 5 실험 부산물 포함). 기준선 태그·백업은 유지 |

> 실행 전 기준선 보존: `git tag harness-v2-baseline` + `cp -r ~/.claude c:/tmp/claude-home-baseline-20260909`. 각 단계는 독립적으로 되돌릴 수 있다. 순서는 보고서 ⑤.

## 0.1 적용 결과 (2026-09-10, deploy 브랜치)

| 절 | 커밋 | 상태 | 비고 |
|---|---|---|---|
| 1단계 문서 5묶음 | `168828c81` | 완료 | 지시서·원장·보고서·초안·실험(러너·원시 결과 12건) |
| §1 사실 오류 정정 | `7eecbb4d2` | 완료 | :26·:39·:48-50 정정 + 경로 실존·MCP 일치 가드. `settings.local.json` 행은 결정 ⑥-6 로 제외 |
| §2 플러그인 | `9c44d7653` | 완료(Opus 5 실측 뒤) | superpowers off·벤더링 0·가드 테스트·상쇄 문장 정리. 전역 settings.json 백업 `C:/tmp/claude-global-settings.json.bak-20260910` |
| §3 규칙 파일 교체 | `08279d7da` | 완료 | CLAUDE.md 35줄 2,897자 · AGENTS.md 본체 압축 · 마커 정본 LONG_TASK_PROMPTS.md · 전역 CLAUDE.md 5줄(백업 `C:/tmp/claude-global-CLAUDE.md.bak-20260910`). `# Compact instructions` 2줄은 Claude 전용 압축 메커니즘이라 유지(초안과 다른 점) |
| §4 프로젝트 훅 | `af5ba2743` | 완료 | ctx_gate 삭제·MEMORY-GATE/CONCURRENT-EDIT 제거·트리밖 스킵 무기록·Stop 차단 로깅(빨강→초록). session_stop 은 SESSION_LOG 마감·임시파일 정리라 유지 |
| §5 가드 인프라 5종 | `f758490b7` | 완료 | 로그 env 격리(conftest autouse)·캡 3,000+월별 보관(공용 writer)·`/c/tmp` 정규화 + rm/reset/checkout 면제·heredoc 본문 제외(타세션 ask 오탐의 진범)·라벨 세분. 2주 재관측 뒤 H-11·12·17~20·22·23 재판정 |
| §6 MOVE-TO-CODE | `8451b64cc` | 완료(3/4) | 인라인 스타일 ratchet 828·`git add -f` ask·승격 PR 범위 대조. 파일 단위 세션 귀속은 설계 필요 → 별도 작업 |
| §7 메모리 | `87773fe95` | 완료 | 154건 전수 판정(`docs/plans/2026-09-09-harness-ablation-v2-memory-judgment.md`): DELETE 108 · 유지 46. MEMORY.md 54줄. 백업 `C:/tmp/memory-baseline-20260910`, 이동 `C:/tmp/memory-deleted-20260910`. 상한 60줄·전역 8줄 가드 |
| §8 인벤토리 키 | — | 범위 밖 | 별도 `**B` |
| §9 사용자 결정 뒤 | (전역 파일, 커밋 없음) | 부분 완료 | gstack 57 → 9종(이동 백업 `C:/tmp/claude-skills-gstack-removed-20260910-111549`). orca·caveman 유지(⑥-1·2). 전역 `permissions.allow` 정리는 미결 — 다음 단계 후보 |
| 3단계 부산물 | `5828c02b0`(스크립트 보강) | 완료 | `abl_cleanup.sh` 실행: 워크트리 15+1·브랜치 6+2·설정/훅/메모리 사본·`extensions.worktreeConfig` 정리. 타 세션 워크트리 22개 무접촉 |
| Opus 5 재실험 | `5828c02b0` | 완료 | T2·T4 팔 A/B 4회, `experiment/runs-opus5/` |

## 1. 사실 오류 정정 (즉시, 위험 0)

| 파일:행 | 지금 | 바꿀 것 |
|---|---|---|
| `CLAUDE.md:39` | MCP 정본 (postgres, context7, youtube) + youtube 설명 | `.mcp.json`(postgres·context7·solapi) |
| `CLAUDE.md:48-50` | `apps/api/`·`services/`·`constants.py` | `foms/api`·`foms/services`, `constants.py` 문구 삭제 |
| `CLAUDE.md:26` | 대화 길어지면 새 세션 권유 | 삭제(내장 컨텍스트 관리와 상충) |
| `.claude/settings.local.json:14-18` | `enabledMcpjsonServers` youtube | youtube 제거, solapi 추가 |

## 2. 플러그인 (전역 `~/.claude/settings.json`)

```json
"enabledPlugins": {
  "caveman@caveman": "<사용자 결정 — 보고서 ⑥-2>",
  "ponytail@ponytail": false,
  "superpowers@claude-plugins-official": false
}
```
- superpowers 를 끄면 전역 CLAUDE.md:33 후반·프로젝트 CLAUDE.md:6 후반(caveman 은 별도)·:25·:44 후반의 상쇄 문장 4개가 함께 불필요해진다.
- 실제 쓰는 superpowers 스킬이 있으면 `~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/<이름>` 을 `~/.claude/skills/<이름>` 으로 복사(벤더링). 후보: brainstorming·writing-plans·systematic-debugging(사용자 지목).
- 드리프트 가드: `tests_harness_drift_guard.py.proposed` 를 tests/harness/test_harness_drift_guard.py (신규) 로.

## 3. 규칙 파일 교체

- `CLAUDE.md` ← `CLAUDE.md.proposed` (108 → 약 32줄). 이관 필수: JSONB 코드블록(현 :57-66)을 `AGENTS.md` 코딩 규약 절에 붙인다. 현 :28-33 등급 마커 상세는 `docs/guides/LONG_TASK_PROMPTS.md` 에 이미 있다.
- `~/.claude/CLAUDE.md` ← `CLAUDE.global.md.proposed` (42 → 3줄). 프로젝트 고유 1줄(서브에이전트 보고 직접 검증)은 초안 CLAUDE.md 에 이미 들어 있다.
- `AGENTS.md`: 원장 조각 ① A-* 판정대로 — RPI 절(:15,19-23)은 CLAUDE.md 와 순환 참조 제거, 문제 수정 정책 5단계(:49-53)는 `diagnosing-bugs` 스킬 포인터로, 성능 가드 G1~G4 산문(:27-29)은 가드 테스트 이름 1줄로, 세션 worktree 10문장(:83)은 함정 목록형으로 압축. APP_OK·claude_master 는 CLAUDE.md 와 자구 동일 유지(가드 테스트).

## 4. 프로젝트 훅 (`.claude/settings.json` ← `settings.json.proposed`)

| 대상 | 조치 | 근거(원장) |
|---|---|---|
| UserPromptSubmit `ctx_gate.py` | 배선 해제, 파일 삭제, `session_start.py` 의 `record_compact_baseline` 호출 제거 | H-05~H-08 |
| `track_edits.py` 동시편집 경고 2기능(`:152-169,206-213`) | 코드 제거, pending 기록·EDIT_LOG 는 유지 | H-28·H-29 |
| `session_start.py` MEMORY-GATE(`:39-69`)·CONCURRENT-EDIT(`:111-154`) | 코드 제거, compact 포인터만 유지, matcher 를 `compact` 로 | H-03·H-04 |
| `track_edits.py:267-270` 트리밖 스킵 로그 | `CLAUDE_HOOK_LOG` 대신 디버그 파일 또는 무기록 | H-30 |
| `quality_check.py:166-172` | 차단 시 `_log_hook_error` 호출 추가 | H-37 |

## 5. 가드 인프라 결함 (판정 확정 전 필수)

| 결함 | 수정 | 파일 |
|---|---|---|
| 테스트가 실 로그에 씀 | `harness_log_path` 를 env(`FOMS_HARNESS_LOG_DIR`)로 주입, 테스트는 `tmp_path` | `.claude/hooks/shared_utils.py:67-89`, `tests/harness/test_guard_policy.py:121-175`, `tools/harness/hook_log_utils.py:49` |
| 로그 캡 300 = 사흘 | `_LOG_CAP` 3,000 + 월별 로테이션 | `.claude/hooks/guard_shell.py:39` |
| 임시경로 면제가 Remove-Item 에만 | `_is_temp_path` 를 `_classify_rm`·`_classify_git_reset`·checkout 에 적용 | `tools/harness/guard_policy.py:351,412,469,530` |
| 타세션 분류기가 push 아닌 명령에 발화 | `git push` 토큰이 있을 때만 판정 | `tools/harness/guard_policy.py:260-278` |
| deny 라벨 불일치 | 라벨을 실제 매치 규칙으로 | `guard_policy.py` 분류 함수 반환값 |

수정 뒤 **2주 재관측** 후 H-11·H-12·H-17~H-20·H-22·H-23 재판정.

## 6. MOVE-TO-CODE

- 인라인 스타일 ratchet: `tests_harness_drift_guard.py.proposed::test_inline_style_ratchet` (기준값은 도입 시점 count 로 고정, 줄어들기만 허용 — 2026-09-09 실측 828).
- `git add -f` / `git add --force` → `guard_policy.py` ask 규칙 추가.
- 승격 PR 커밋 범위 ↔ 세션 레저 대조: `tools/harness/promote_own_to_production.py` 산출 직전 검사.
- 파일 단위 세션 귀속(같은 파일 안 타 세션 편집 혼입): EDIT_LOG 세션 태그와 `git diff --stat` 대조 — 설계 필요, 별도 작업.

## 7. 메모리 (`~/.claude/projects/c--DEV-FOMS/memory/`)

- 원장 조각 ④ A.3 표본 판정(DELETE 21/30)을 기준으로 전수 확인. 규칙: ①저장소에서 유도 가능 → 삭제, ②참조 대상 소멸 → 삭제, feedback/reference 타입 → 유지.
- 정리 뒤 `MEMORY.md` 60줄 상한을 가드 테스트로.
- 삭제 전 `cp -r memory c:/tmp/memory-baseline-20260909`.

## 8. 인벤토리 (별도 `**B` 작업)

- `docs/harness/foms_{failopen,order_mutation_writer,state_writer}_inventory.json` 키를 `(path, symbol, kind)` 로 재정의하거나, 커밋하지 않고 CI 에서 생성. 스캐너 `tools/harness/*_scan.py` 3종 동반.

## 9. 사용자 결정 뒤

- orca: `~/.claude/settings.json` hooks 에서 `claude-hook.cmd` 10이벤트 제거(orca 앱을 다시 쓰면 앱이 재설치한다).
- caveman: 끄면 `CLAUDE.md:6` 후반 문장 삭제. 유지하면 상쇄 규칙을 `~/.claude/.caveman-active` 강도 조정으로 대체.
- gstack: `~/.claude/skills/gstack-*` 57종 중 미사용 삭제(`gstack-upgrade` 로 재설치 가능).
- 전역 `permissions.allow` 약 130줄 중 채널톡 curl·designer pytest·railway 1회성 항목 삭제.
