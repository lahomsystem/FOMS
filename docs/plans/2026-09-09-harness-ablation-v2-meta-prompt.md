# 하네스·가이드라인 ablation v2 — 정밀 분석 지시 프롬프트 (2026-09-09)

> FOMS 총괄 개발자가 후임 분석 에이전트에게 건네는 지시서다. 이 파일만 읽고 시작한다. 세션 히스토리·개인 메모리는 붙이지 않는다. 경로는 저장소 루트 `C:/DEV/FOMS` 기준 상대 경로, 전역 경로는 `~/.claude/` 로 적는다.

## 0. 이 문서를 받는 에이전트에게

- 만들 것: "Fable 5.1 / Opus 5 세대에서는 하네스(훅·스킬·플러그인·메모리)와 CLAUDE.md 류 가이드라인을 걷어내는 쪽이 성능이 좋다" 는 **주장을 검증**하고, 항목 단위로 유지·압축·삭제·코드 이관을 판정한 **원장 1개 + 보고서 1개 + 제안 초안 묶음**. 주장은 전제가 아니라 가설이다(§3). 이 프롬프트가 품은 사실 카드(§2)와 사전 관측(§5)에서 출발해 검증·확장하지, 처음부터 탐색하지 않는다.
- 이 프롬프트의 경로: `docs/plans/2026-09-09-harness-ablation-v2-meta-prompt.md`.
- 결과물 경로(전부 신규 파일, 기존 파일은 한 글자도 바꾸지 않는다):
  - 원장 `docs/plans/2026-09-09-harness-ablation-v2-ledger.md` — 항목별 판정표(§9.1).
  - 보고서 `docs/plans/2026-09-09-harness-ablation-v2-report.md` — 결론·근거·실험 결과(§9.2).
  - 초안 폴더 `docs/plans/2026-09-09-harness-ablation-v2-drafts/` — 제안 `CLAUDE.md`·전역 `CLAUDE.md`·`settings.json`·삭제 목록·드리프트 가드 테스트 초안(§9.3).
- 기준 커밋: 사실 카드는 deploy `46bdac44d`(2026-09-09) 기준. 시작 전에 `git log --oneline -1` 로 HEAD 를 적고, 숫자가 어긋나면 "재측정: 값 — 명령" 으로 병기한다.
- 직전 ablation(2026-08-03)의 결정 기록은 `docs/harness/policy/DECISIONS.md:33` 부터다. 그때의 원칙 "전부 없다고 가정하고, 모델이 **같은 지점에서 반복 실패하는 것만** 되살린다" 는 이번에도 판정 기준이다. 다만 그때는 정적 감사만 했고 **실험(A/B)은 하지 않았다**. 이번의 차이는 §7 이다.

### 0.1 새 세션 시작 프롬프트(복붙용)

새 세션(같은 저장소 `C:/DEV/FOMS`, deploy 브랜치)의 첫 메시지로 아래를 그대로 붙인다.

```text
**B 하네스·가이드라인 ablation v2 정밀 분석을 실행해.
유일한 컨텍스트 = docs/plans/2026-09-09-harness-ablation-v2-meta-prompt.md — 먼저 전부 읽어. 세션 히스토리·메모리는 붙이지 마.
1단계 = 정적 감사(§6): 항목 전수를 §4 의 7층으로 분류하고 §4.2 판정 규칙으로 원장을 채워. 감사 차원 5개(§8)는 Agent 병렬로 돌리고 총괄이 원장을 합쳐.
2단계 = 실험(§7): §7.2 의 재현 과제 4개 × 팔 3개 = 12회를 claude -p 로 돌리고 §7.4 지표를 표로 내. 실험 기동 전에 §7.3 의 플래그 실존을 claude-code-guide 에이전트로 먼저 확인해.
결과물 = 원장 + 보고서 + 초안 폴더(§9). 완료 기준 = §9.4 전부(앵커 실존 0 오류 · 한자 0 · 항목 전수 판정 · 기존 파일 무변경 · 숫자마다 명령 병기).
규칙 = 읽기 전용 분석(기존 파일 수정·삭제·패키지 설치·git 변경·push 금지, 실험은 c:/tmp 워크트리와 별도 CLAUDE_CONFIG_DIR 에서만), 주장을 전제로 삼지 말고 검증, 운영 수치 추정 금지, 한글·한자 금지.
끝나면 총괄이 직접 §9.4 스니펫을 재실행하고, 판정 분포·절감 추정·실험 결과·열린 질문을 한글로 보고해. 실제 삭제·적용은 내가 결정한다.
```

### 0.2 적용 세션 시작 프롬프트(복붙용, 1·2단계 완료 뒤 2026-09-10 추가)

분석·실험이 끝난 뒤 판정을 실제로 반영하는 세션의 첫 메시지. 결정은 사용자가 하고, 세션은 물어본 뒤 단계별로 적용·검증·커밋한다.

```text
**B 하네스 ablation v2 적용 세션 — 판정 결과를 실제로 반영해.
컨텍스트 = 이 순서로 읽어: docs/plans/2026-09-09-harness-ablation-v2-report.md(결론·⑤ 적용 순서·⑥ 열린 질문) → docs/plans/2026-09-09-harness-ablation-v2-drafts/DELETE_LIST.md(단계별 명령) → 같은 폴더 초안 4개 → 필요할 때만 원장 docs/plans/2026-09-09-harness-ablation-v2-ledger.md §0. 세션 히스토리·메모리는 붙이지 마.
0단계 = 보고서 ⑥ 열린 질문 8개를 AskUserQuestion 으로 하나씩 물어 답을 받고, DELETE_LIST 맨 위에 "결정" 표로 적어. 답 없이 추측으로 진행 금지.
1단계 = 문서 5묶음(meta-prompt·ledger·report·drafts/·experiment/)을 docs: 접두로 deploy 브랜치에 커밋(한글 메시지는 UTF-8 파일 + git commit -F, pathspec 지정). 기준선 확인: git tag harness-v2-baseline 과 C:/tmp/claude-home-baseline-20260909 존재.
2단계 = DELETE_LIST 를 §1 → §2 → §3 → §4 → §5 → §6 → §7 순으로 적용. 절마다: 변경 → 검증(python -c "import app; print('APP_OK')", pytest tests/harness -q, 드리프트 가드 테스트) → 커밋 1개 → 원장 §0 상태 열 갱신. §5(가드 인프라 결함 5종)·§6(인라인 스타일 ratchet·git add -f ask)은 코드 변경이니 테스트를 먼저 빨갛게 만든 뒤 고쳐. §8(인벤토리 키 재정의)은 이번 범위 밖 — 별도 **B 로 남겨.
3단계 = 실험 부산물 정리: docs/plans/2026-09-09-harness-ablation-v2-experiment/abl_cleanup.sh 를 사용자 확인 뒤 실행(워크트리 15·브랜치 6·사본). 다른 세션 워크트리(foms-s-*, promote/own-*)는 절대 건드리지 마.
규칙 = production push 금지. deploy push 는 마지막에 사용자 확인 → pre_push_smoke exit 0 → push → ci_watch --quick. 전역 ~/.claude 변경(플러그인 off·전역 CLAUDE.md·orca 훅·allow 정리)은 실행 전 한 번 더 확인하고 백업 경로를 보고에 적어. 한글·한자 금지.
완료 기준 = DELETE_LIST 각 절에 커밋 SHA 병기, 드리프트 가드 테스트 green, APP_OK, 원장 §0 상태 열 갱신, 새 세션 /context 출력(사용자가 붙여 줌)으로 보고서 ① 표에 "적용 후" 열 추가.
끝나면 적용 전후 비교(CLAUDE.md 줄 수·훅 수·플러그인·상시 토큰)를 한글 표로 보고하고 다음 단계를 물어.
```

## 1. 페르소나·임무·판정 질문

너는 **FOMS 총괄 개발자**다. 이 프로젝트는 사람 1명(nathan) + AI 에이전트가 5주에 1,482 커밋을 내는 속도로 굴러가고, 같은 워킹트리를 동시 2~3개 창이 공유하며, 스테이징(`deploy`)과 운영(`production`)이 브랜치로 갈린다. 하네스는 2026-04 부터 5차례 재설계됐고(`docs/harness/policy/DECISIONS.md:33-129`), 마지막 ablation 이 2026-08-03 이다.

임무는 다음 세 질문에 **항목 단위 근거**로 답하는 것이다.

1. **무엇이 모델 능력과 무관한가** — 코드로 강제되는 안전 가드, 저장소에서 유도할 수 없는 환경 사실, 사용자 취향은 모델이 아무리 좋아져도 필요하다. 이것들은 "걷어내기" 대상이 아니라 "한 곳으로 압축" 대상이다.
2. **무엇이 구형 모델 보정 장치인가** — 절차 강제, 매 턴 리마인더, 자기점검 체크리스트, 스킬 강제 호출 규칙은 모델이 그 지점에서 실패하지 않으면 순비용이다. 2026-08-03 이후 로그·커밋·변경 기록에 그 규칙이 막은 실패가 있는지로 판정한다.
3. **무엇이 서로 싸우는가** — 규칙끼리 상충하거나 같은 정책이 서너 벌 복제돼 있으면 모델이 좋을수록 더 해롭다(강한 모델은 지시를 더 문자 그대로 따르므로 상충하는 지시는 더 큰 흔들림을 만든다). 상충·중복은 실효와 무관하게 하나로 줄인다.

"성능이 좋아진다" 의 뜻을 §7.4 지표로 고정한다. 토큰 절감 하나로 판정하지 않는다 — 이 세션은 1M 컨텍스트 + 1시간 프롬프트 캐시라 상시 텍스트의 **금전 비용은 거의 0** 이고, 진짜 비용은 **주의 희석·지시 상충·턴 수·규칙 위반·지연** 이다.

## 2. 사실 카드 (총괄 실측, 2026-09-09)

다시 재지 말고 인용한다. 재측정 값이 다르면 "(재측정: 값 — 명령)" 으로 병기한다.

### 2.1 상시 로드 텍스트(세션마다 컨텍스트에 들어가는 것)
- 프로젝트 `CLAUDE.md` 108줄 6,801자(한글 1,797자), 전역 `~/.claude/CLAUDE.md` 42줄 1,610자, 메모리 색인 `~/.claude/projects/c--DEV-FOMS/memory/MEMORY.md` 12,308자(153개 항목 링크). 총괄 추정 합계 약 8,400토큰 — **추정치다. 정확한 값은 새 세션에서 `/context` 를 사용자가 실행해 붙여준 표로 대체한다**(시스템 프롬프트·도구·MCP·메모리·스킬 분해가 나온다).
- `AGENTS.md` 84줄 13,985자는 자동 로드되지 않는다(CLAUDE.md 가 포인터로 가리킨다). 그러나 CLAUDE.md 가 "요약" 이라며 다시 적은 분량이 원문의 절반을 넘는다(§5 항목 9).
- 플러그인 주입: superpowers `using-superpowers` 블록(`~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/hooks/hooks.json`, SessionStart `startup|clear|compact`) + caveman(SessionStart 1줄, UserPromptSubmit 마다 "CAVEMAN MODE ACTIVE" 1줄, 세션 시작에 규칙 본문 약 1,200토큰).
- 스킬 목록: 전역 `~/.claude/skills` 59개(gstack 56) + 프로젝트 `.claude/skills` 5개 + 플러그인 스킬(caveman 20여 개, superpowers 12개) + 내장. 세션마다 이름·설명 1줄씩 나열된다.
- MCP: `.mcp.json` 실제 정의는 postgres·context7·solapi. **youtube 는 `.mcp.json` 에 없는데** 프로젝트 `CLAUDE.md:39` 와 `.claude/settings.local.json` 허용목록이 정본이라 서술한다(유령 항목, 워커 ③ 발견). claude.ai 커넥터(Gmail·Calendar·Drive·Microsoft 365)는 전역. 도구 스키마는 지연 로드지만 이름 목록은 매 세션 나열된다(MCP 도구명 106개 + 커넥터 49개).
- 전역 설정: `~/.claude/settings.json` — `model: claude-fable-5-1[1m]`, `effortLevel: xhigh`, `enabledPlugins` caveman true · ponytail false · superpowers true, permissions.allow 약 130줄(채널톡 조사 시절 curl 1회성 항목 다수).

### 2.2 훅(코드 실행 층)
- 프로젝트 `.claude/settings.json` 훅 7이벤트: SessionStart `session_start.py`(225줄) · UserPromptSubmit `ctx_gate.py`(187) · PreCompact `pre_compact.py`(60) · PreToolUse(Bash) `guard_shell.py`(131) · PostToolUse(Edit|Write) `track_edits.py`(300) · PostToolUse(Bash) `post_bash.py`(42, `record_commit_ledger`+`post_push_watch` 통합) · Stop `session_stop.py`(80)+`quality_check.py`(211). 합계 1,601줄. 정책 본체는 `tools/harness/guard_policy.py`.
- 전역 `~/.claude/settings.json` 훅: `~/.orca/agent-hooks/claude-hook.cmd` 가 **10개 이벤트**(UserPromptSubmit·Stop·StopFailure·SubagentStart·SubagentStop·TeammateIdle·PreToolUse `*`·PostToolUse `*`·PostToolUseFailure·PermissionRequest)에 걸려 있다. 내용은 `ORCA_*` 환경변수가 없으면 stdin 을 버리고 exit 0 — **현재 환경에서는 무동작**. Stop 에 gstack `timeline-stop-hook` 도 있다.
- 지연(총괄 실측, 더미 페이로드 3회): `guard_shell` 55ms · `post_bash` 52 · `track_edits` 54 · `ctx_gate` 53~84 · orca cmd 27 · 파이썬 빈 기동 30. **Bash 1회당 약 160ms**(guard+post_bash+orca 2회), **Edit 1회당 약 110ms**. 명령: `python - <<EOF` 로 `subprocess.run` 감싸 `time.perf_counter` 측정.
- deny 목록(permissions.deny): `git push origin production*`, `git push --force*`, `git push -f *`.

### 2.3 가드 실효 로그(`docs/harness/logs/SHELL_GUARD_LOG.md`) — **정정 2026-09-09 (워커 ⑤ 발견, 총괄 검증)**
- 이 로그는 `guard_shell.py:39` 의 `_LOG_CAP = 300` 롤링이라 **2026-09-07 12:02 ~ 09-09 사흘치만** 남아 있고 gitignore 대상이라 이전 기록은 복구 불가. 초판 사실 카드의 "2026-08-03 이후" 는 성립하지 않는다. 5주 실효 판정은 이 로그로 못 한다 — `docs/AI_CHANGELOG.md`·git log 의 재발 기록(§6 항목 3)이 대신한다.
- 오염: `tests/harness/test_guard_policy.py` 의 `CASES` 표가 `.claude/hooks/guard_shell.py` 와 `.cursor/hooks/guard_shell.py` 를 subprocess 로 실제 실행하고, 훅은 실 로그에 그대로 쓴다. 케이스 수 × 훅 2 × 실행 2회 산술이 로그와 정확히 맞는다: `production 푸시` 4×2×2=**16(전부 오염, 실제 시도 0)**, `Remove-Item` 5×2×2=20(실제 0), `pip install` 9×2×2=36(실제 0), `reset --hard` 오염 4 + 실제 5. 오염 총량 82행×2 = 164행, 300행 중 55%.
- 실제 deny 5건: `reset --hard`·`rm -rf` 전부 `c:/tmp` 워크트리 정리·rebase 중 발화(위험 시도 0, 오탐 성격). 실제 ask 중 `deploy 푸시 타 세션 커밋 포함` 은 명령에 `push` 문자열이 없는 행이 49건(`cat >>`, `git fetch`, `git rebase`, `python -c "import app"` 등) — **분류기 오탐**. 명령: `grep "타 세션 커밋 포함" docs/harness/logs/SHELL_GUARD_LOG.md | grep -vc push`.
- 함의: H2(코드 가드 필수)의 근거로 이 로그를 쓸 수 없다. 코드 가드 실효는 재발 기록 매핑(워커 ⑤ 절 2)으로만 판정하고, 가드 자체에는 오탐·로그 오염 결함 2건을 등재한다.

### 2.4 훅 fail-open 로그(`docs/harness/logs/CLAUDE_HOOK_LOG.md`, 300행)
- `[track_edits]` 258행이 전부 "트리밖 편집 스킵" 정보성, `[ctx_gate]` 11행(55% 임계 리마인더 발화). Stop 게이트(`quality_check`)가 턴을 **차단한 기록은 0건** — 차단이 없었던 것인지 기록을 안 남기는 것인지 확인 대상. `HOOK_RUNTIME_LOG.txt`(185KB)는 별도로 훅 실행 시각을 담는다.

### 2.5 유지 비용(커밋 기준)
- 2026-08-03 이후 커밋 1,482건 중 "인벤토리 재생성·줄밀림·줄번호 동기화" 커밋 **42건(2.8%)**, `chore(harness)` 접두 23건. 대상은 `docs/harness/foms_failopen_inventory.json` · `foms_order_mutation_writer_inventory.json` · 감사 커버리지 인벤토리 — 줄 번호 고정형이라 무관한 코드 변경마다 재생성이 필요했다. 메모리 기록으로는 "lineno-무관 게이트" 로 종결됐다고 하니 **그 뒤로 churn 이 실제로 멈췄는지** 날짜별로 확인한다. 명령: `git log --since=2026-08-03 --oneline | grep -ciE "인벤토리.*(재생성|동기화|정합)|줄밀림|줄번호"`.
- `tests/harness/` 25파일 — 하네스 자체를 검증하는 테스트. `docs/plans/` 에 2026-08-03 이후 103파일 — `**B`/`**C` 등급 프로토콜(플랜+원장)이 활발히 쓰였다는 뜻이다. 완주율은 미측정.
- 메모리 153파일(project 138 · feedback 13 · reference 1 · user 0), 그중 73개가 2026-08-03 이후 작성·수정(하루 2개꼴).

### 2.6 이미 벌어진 드리프트
- 2026-08-03 ablation 은 superpowers SessionStart 훅을 `hooks.json={}` 로 무력화했고 "플러그인 업데이트 시 복원됨" 을 명시했다. 현재 캐시는 **6.3.0 이고 hooks.json 이 복원돼 있다** — `using-superpowers` 의 "1%라도 해당하면 스킬 강제" 블록이 매 세션 다시 들어온다. 전역 `CLAUDE.md` 에는 그 블록을 부정하는 문장("1%라도 해당하면 스킬 강제 류의 상시 규칙은 따르지 않는다")이 있다. 즉 지금 이 순간 **규칙 A 와 그것을 부정하는 규칙 B 가 함께 로드**된다.

## 3. 가설과 반가설 (검증 대상, 전제 아님)

- **H1(걷어내기 유리)**: 절차 지시·리마인더·스킬 강제·자기점검은 최신 모델에서 턴 수·규칙 위반·산만함을 늘리고 결과 품질을 올리지 못한다. 예측: §7 실험에서 팔 B(최소)가 팔 A(현행)와 성공률 동률이면서 턴·도구 호출·소요 시간이 적다.
- **H2(코드 가드 필수)**: 텍스트 규칙만으로는 위험 명령·규약 위반을 막지 못한다. 근거는 가드 로그가 아니라(§2.3 정정 — 로그는 사흘치이고 위험 명령 행은 전부 테스트 오염) **재발 기록**이다: 인라인 스타일 금지가 CLAUDE.md 두 곳에 있는데도 5주간 76행 추가(`git log --since=2026-08-03 -p -- templates static | grep -c '^+.*style="'`), 같은 파일 동시 편집분이 경로 지정 커밋에 실려 CI red(`c7c11b111`). 반대로 jQuery·bare except 위반은 0 — 규칙 덕인지 모델 기본인지는 §7 팔 C 로만 가른다.
- **H3(환경 사실은 삭제 불가)**: 브랜치 정책·공유 워킹트리·Windows cp949·Railway 서비스 구성·측정 계정 규칙은 저장소를 읽어도 유도되지 않는다. 예측: 팔 C(무규칙)는 이 지점에서 실패한다(예: 한글 커밋 `-m` 깨짐, production 대상 혼동).
- **H4(상충이 진짜 비용)**: 같은 정책의 복제본과 상충 규칙이 실효 규칙보다 더 해롭다. 예측: 팔 A 에서 관측되는 이상 행동(스킬 과호출·보고 형식 흔들림·한자 유출)의 대부분이 §5 의 상충 항목에 귀속된다.
- **반가설 R1**: "성능이 좋다" 는 체감은 컨텍스트가 짧아 **캐시 히트·응답 지연**이 줄어든 효과일 수 있다 — 결과 품질과 분리해 측정한다(§7.4 에서 지연과 성공률을 따로 적는다).
- **반가설 R2**: 규칙 제거 뒤 회귀는 **지연 발현**한다(제거 직후 몇 세션은 괜찮다가 드문 상황에서 터진다). 그래서 삭제 판정에는 반드시 "복원 트리거"(어떤 실패가 다시 보이면 되살릴지)를 붙인다.

## 4. 분류 체계와 판정 규칙

### 4.1 7층 분류 — 모든 항목은 정확히 한 층에 넣는다

| 층 | 뜻 | 모델 능력 의존 | 예 |
|---|---|---|---|
| L1 코드 강제 | 훅 deny/ask, permissions.deny, 테스트 게이트, CI, branch protection | 무관 | `guard_policy.py` 강제 푸시 차단, Stop `import app` 게이트, pre_push_smoke |
| L2 환경 사실 | 저장소·코드에서 유도 불가능한 사실 | 무관 | deploy→production 흐름, 공유 워킹트리, cp949, `claude_master` 계정, Railway 서비스 4종 |
| L3 사용자 취향 | 형식·언어·종료 방식 | 무관 | 한글 완료 보고, 한자 금지, 마지막 AskUserQuestion, 커밋 한글 `-F` |
| L4 절차 지시 | 작업 순서·게이트·위임 기준·등급 마커 | **강함** | RPI, `**A~**D`, 위임 기준, 새 세션 시작 프로토콜, "대화 길어지면 새 세션" |
| L5 행동 교정·코딩 규약 | 모델이 기본으로 안 하는 프로젝트 규약과, 기본으로 하는데 다시 적은 잔소리 | 반반 | JSONB `flag_modified` 패턴(규약, 유지) vs "bare except 금지"(모델 기본, 잔소리) |
| L6 재주입·리마인더 | 훅이 세션·턴마다 넣는 텍스트 | **강함** | session_start 안내, ctx_gate 55%, caveman 매 턴 1줄, CONCURRENT-EDIT 알림, CI-GATE 안내 |
| L7 상충·중복 | 같은 정책의 복제본, 서로 부정하는 규칙 | 무관(항상 비용) | superpowers 1% 블록 vs 전역 CLAUDE.md, AGENTS.md↔CLAUDE.md 정책 3벌 |

내장 시스템 프롬프트(Claude Code 가 Fable 5.1 세션에 기본 주입하는 것)가 이미 담는 내용은 **L7 로 분류**한다. 내장에 있는 것으로 확인된 주제: 위임 기준(독립 작업·파일 10개 이상 탐색), 서브에이전트 결과 검증 후 인용, 결과 정직 보고, 파괴 명령 전 대상 확인, 임의 축소 금지·전체 완주, 메모리 저장 규칙, 한글 응답 형식 일반. 확인 방법: 분석 세션의 시스템 프롬프트를 읽을 수는 없으므로 `claude-code-guide` 에이전트에게 "Claude Code 기본 시스템 프롬프트가 다루는 주제 목록" 을 물어 교차한다.

### 4.2 판정 규칙 (원장의 판정 열은 이 값만 쓴다)

| 판정 | 조건 | 결과 |
|---|---|---|
| KEEP-CODE | L1 이고 2026-08-03 이후 **실제** deny/ask 또는 게이트 실패 1건 이상(테스트 오염 제외) | 코드 유지. 같은 내용의 산문은 1줄 포인터로 압축하거나 삭제 |
| DOWNGRADE | L1 인데 실제 발화 0건이거나 발화의 과반이 오탐 | 로그 전용으로 낮추거나 삭제. 지연 비용 병기 |
| KEEP-FACT | L2 | 한 곳(프로젝트 CLAUDE.md)에 1줄. AGENTS.md·메모리의 복제본은 DELETE 또는 포인터 |
| KEEP-PREF | L3 | 유지. 단 caveman 등 다른 규칙과 싸우면 상대를 RESOLVE |
| DELETE | L4·L5·L6 중 2026-08-03 이후 그 규칙이 막은 실패 기록이 없고 내장 프롬프트나 코드 가드가 같은 일을 함 | 삭제 + **복원 트리거** 1줄(어떤 재발이 보이면 되살릴지) |
| MOVE-TO-CODE | L4·L5 인데 위반이 반복 기록됨(텍스트가 못 막았다) | 훅·테스트·permissions 로 이관, 산문 삭제 |
| COMPRESS | L5 규약 중 유지 대상, L6 중 조건부 유지 | 줄 수 절반 이하로, 발화 조건 명시 |
| RESOLVE | L7 | 한 벌만 남기고 나머지 삭제. 드리프트 재발 가능하면 가드 테스트 초안 첨부 |

판정마다 근거 열에 **경로:행 또는 로그 수치 + 명령** 을 적는다. "모델이 알아서 한다" 는 근거가 아니다. "내장 프롬프트에 있다" 는 §4.1 의 교차 확인 결과를 인용할 때만 근거다.

## 5. 사전 관측 (총괄이 이미 본 것 — 검증하고 확장할 것)

태그: `[층 · 판정 후보 · 확신]`. 확신 = 확정(측정함)/유력(근거 있음)/의문(확인 필요).

1. `[L7 · RESOLVE · 확정]` superpowers 6.3.0 hooks.json 복원으로 "1% 규칙" 블록이 매 세션 재주입되고, 전역 `~/.claude/CLAUDE.md` §4 가 그것을 부정한다(§2.6). 해법 후보: 플러그인 비활성화 후 실제 쓰는 스킬(brainstorming·writing-plans·systematic-debugging 정도)만 `~/.claude/skills` 로 벤더링, 또는 `tests/harness` 에 "플러그인 훅 비활성 상태" 가드 추가. 어느 쪽이든 **재발 방지가 코드여야** 한다.
2. `[L7 · RESOLVE · 확정]` caveman 과 다른 규칙의 충돌 3종: ① 프로젝트 CLAUDE.md "한자 금지 … 압축 스킬(caveman 등)의 축약 지시보다 본 규칙이 우선" 은 caveman 을 상쇄하려고만 존재하는 규칙이다. ② caveman "장식 표 금지" vs 내장 형식 규칙 "숫자는 표로". ③ caveman "도구 호출 전 서술 금지" vs 내장 "시작 전에 한 줄 알림". 판정: caveman 을 끄면 규칙 3개가 같이 사라진다. 끄지 않으려면 상쇄 규칙을 caveman 설정으로 옮긴다. **사용자 취향(L3)이므로 유지 여부는 사용자 결정** — 원장에는 비용만 적는다.
3. `[L6 · DELETE 후보 · 확정]` `~/.orca` 훅이 10개 이벤트에 걸려 있고 현재 환경에서 무동작이다(§2.2). 도구 호출마다 cmd.exe 2회 약 55ms. 기원(orca 도구)이 아직 쓰이는지 사용자에게 확인 후 삭제.
4. `[L1 · 판정 보류 · 정정]` 초판은 "`production 푸시` ask 16회" 를 코드 가드 근거로 들었으나 **16회 전부 테스트 오염**이다(§2.3 정정). 가드 실효는 재발 기록(§6 항목 3)으로만 판정한다. 워커 ⑤ 결과: "규칙 있어도 발생" 6건, "코드가 막음" 5건, "아무것도 없어 발생" 8건. KEEP-CODE 가 확실한 것은 AI_STATUS 예산 게이트(`tests/harness/test_hook_log_hygiene.py:184`, 5주간 red 18회·매번 복구 커밋).
5. `[L1 · 결함 · 확정]` 가드 테스트가 실 로그(`SHELL_GUARD_LOG.md`)를 오염시킨다(82행×2 = 164행, 55%). 또 `deploy 푸시 타 세션 커밋 포함` 분류기가 push 아닌 명령 49건에 ask 를 냈다. 둘 다 이 분석 세션에서 고치지 않는다 — 원장에 결함으로 등재.
6. `[L6 · DOWNGRADE 후보 · 의문]` Stop 게이트 `quality_check` 차단 기록 0건. `HOOK_RUNTIME_LOG.txt` 와 `quality_check.py` 의 로그 경로를 읽어 "차단이 없었다" 와 "기록을 안 한다" 를 가른다. 없었다면 55ms 짜리 보험이라 코드는 유지하되 CLAUDE.md 의 "Stop 게이트" 설명 문단은 DELETE.
7. `[L6 · COMPRESS · 확정]` `CLAUDE_HOOK_LOG.md` 300행 중 258행이 track_edits 정보성 — fail-open 실패 로그가 86% 소음이라 진짜 실패를 덮는다. 정보성은 별도 파일이나 디버그 레벨로.
8. `[L1 · 비용 · 확정(반증됨)]` 인벤토리 churn 은 **종결되지 않았다** — 42커밋 중 최신이 2026-09-09 이고 기준 HEAD `46bdac44d` 자체가 "인벤토리를 커밋 트리 기준으로 재생성" 커밋이다. 메모리의 "lineno-무관 게이트로 종결" 기록은 틀렸거나 일부 인벤토리에만 적용됐다. 인벤토리 3종과 스캐너(`tools/harness/*_scan.py`)는 DOWNGRADE 후보(줄 번호 대신 심볼·해시 키로 바꾸거나, 인벤토리 파일을 커밋하지 않고 CI 에서 생성).
9. `[L7 · RESOLVE · 확정]` AGENTS.md 와 CLAUDE.md 에 같은 정책이 두 벌: 문제 수정 정책(AGENTS.md "절대 규칙: 문제 수정 정책" 전문 vs CLAUDE.md "문제 수정 정책" 요약), 성능 가드(둘 다 G1~G4 나열), git 승격 절차(둘 다 cherry-pick 원칙·헬퍼 이름), `APP_OK`, `claude_master`, 훅 fail-open. AGENTS.md 는 "SSOT" 라 선언돼 있고 자동 로드되지 않는다. 판정 후보: CLAUDE.md 는 각 정책을 **제목 1줄 + 경로** 로만 남긴다.
10. `[L7 · RESOLVE · 유력]` 전역 CLAUDE.md §1~§3(위임 기준·위임 규율·검증 무신뢰)과 프로젝트 CLAUDE.md 의 "작업 등급 마커" 가 내장 프롬프트의 위임·검증 지침과 겹친다(§4.1). 겹치는 문장은 삭제, 프로젝트 고유값(예: "서브에이전트 보고는 diff·테스트 직접 확인 후 승인")만 남긴다.
11. `[L6 · 측정 · 확정]` 상시 텍스트 추정 8,400토큰 + 플러그인 블록 + 스킬·MCP 이름 목록. `/context` 실측으로 대체하고, 팔별(§7.1) `/context` 를 세 번 찍어 표로 낸다.
12. `[L2/L7 · 감사 · 유력]` 메모리 153개 중 project 138개. 메모리 규칙은 "저장소가 기록하는 것은 저장하지 않는다" 인데 제목만 봐도 코드·문서에서 유도 가능한 항목이 섞여 있다(예: 컬럼 NULL 사실, CSS SSOT 경로, 상수 의미). 표본 30개를 무작위로 열어 ① 저장소에서 유도 가능 ② 유효 기간 지남 ③ 진짜 비유도 사실 로 분류하고 비율을 낸다. 전수는 하지 않는다(시간 대비 이득 낮음).
13. `[L4 · 효과 미상 · 의문]` `**A~**D` 등급 + `docs/guides/LONG_TASK_PROMPTS.md`(135줄)+`_EASY.md`(168줄). `docs/plans/` 103파일의 완주율을 원장(ledger) 파일의 마지막 상태로 세라(DONE/PENDING/BLOCKED 비율). 완주율이 높고 사용자가 직접 마커를 쓴다면 L3(취향)로 재분류해 KEEP-PREF.
14. `[L4 · DELETE 후보 · 유력]` "새 세션 시작 프로토콜 1: AI_STATUS 상단 40줄 읽기" — `session_start.py` 가 이미 SessionStart 에 안내를 주입한다. 둘 중 하나. 또 "대화가 길어지면 새 세션 권유" 는 1M 컨텍스트·자동 컴팩트 환경에서 근거가 약하다.
15. `[L5 · 분리 · 유력]` 코딩 규칙 절 안에 프로젝트 규약(JSONB 패턴, `data-*` + `safeJsonParse`, 인라인 스타일 금지·erp-pro.css, jQuery 금지, 새 API 는 `apps/api/` Blueprint)과 모델 기본 행동(bare except 금지, 타입 힌트, docstring, 함수 50줄)이 섞여 있다. 전자 KEEP-FACT, 후자 DELETE 후보. 단 후자도 "기본 행동인가" 는 §7 팔 C 에서 위반이 나오는지로 확인한다.
16. `[L2 · KEEP-FACT · 확정]` 삭제 불가 사실 목록(초안): `production` push 는 사용자 명시 요청 시에만·기본 `deploy`, 승격 = 자기 커밋 cherry-pick, 공유 워킹트리·세션 격리 도구 경로, 커밋 메시지 한글은 파일 `-F`, `APP_OK` 문자열, pre_push_smoke 위치, `claude_master` 규칙, Windows cp949 전제, Railway 서비스에 SIDEFX 가 따로 있음, `.mcp.json` 정본. 각 1줄로 압축 가능한지 초안에서 시험한다.
17. `[L3 · KEEP-PREF · 확정]` 한글 완료 보고, 한자 금지, 종료 시 AskUserQuestion, 초등학생 표현. 유지. 단 "한자 금지" 는 caveman 을 끄면 짧아진다(항목 2).
18. `[L6 · 조건부 · 의문]` `ctx_gate` 55% 리마인더 11회 발화 — 발화 뒤 실제로 원장·AI_STATUS 갱신이 이어졌는지 `git log` 시각과 대조. 이어진 적이 없다면 DELETE, 있었다면 COMPRESS(문구 절반).

### 5.1 1단계 결과로 정정된 사전 관측 (2026-09-09, 원장 §0·보고서 참조)

- 항목 2: caveman ↔ 내장 상충 2쌍은 **확정 유지** — 총괄이 내장 원문("숫자는 짧은 표로", "시작 전에 한 줄")을 직접 확인. 워커 ③ 의 "문서 미기재" 는 공식 문서 기준이지 로드된 텍스트 기준이 아니다.
- 항목 4·5: §2.3 정정대로. production 16건은 전부 오염, 오염 규모 164행.
- 항목 6: Stop 게이트는 차단 시 **로그를 남기지 않는다**(`quality_check.py:166-172`) — "차단 0" 은 "기록 안 함". 코드 KEEP-CODE, 로깅 추가 MOVE-TO-CODE, 산문 DELETE.
- 항목 8: churn 종결되지 않음(반증). HEAD 자체가 churn 커밋.
- 항목 12: 표본 30 → DELETE 21(70%)·KEEP-FACT 6·KEEP-PREF 3. 외삽 잔존 약 46, MEMORY.md 상한 60줄.
- 항목 13: ledger 58개 완주율 51.7%, 실사용 마커 9줄(전부 세션 인계 프롬프트) → L4 COMPRESS.
- 항목 14: **전제 틀림** — `session_start.py:177-192` 는 compact 재개 때만 주입하고 정적 안내는 2026-08-03 에 이미 제거됐다. "AI_STATUS 상단 40줄" 산문은 유일 경로라 KEEP-FACT. "대화 길어지면 새 세션" 은 내장과 상충이라 DELETE 유지.
- 항목 18: 로그 11행은 발화가 아니라 세션 첫 프롬프트 스킵. 실제 발화 1건(상태 파일), 30분 내 원장 커밋 0 → DELETE.
- 신규: `CLAUDE.md:48-50` 이 없는 경로(`apps/api/`·`services/`·`constants.py`)를 가리킨다. `CLAUDE.md:39` youtube MCP 는 `.mcp.json` 에 없다. 타세션 push 분류기 오탐 49~73건. 동시편집 경고는 2026-08-31 이후 발화 0. MEMORY-GATE 는 159/160 줄로 발화 직전. orca 는 2026-09-08 까지 사용됨.

## 6. 정적 감사 절차 (1단계)

1. **항목 전수 추출**: 프로젝트 CLAUDE.md 의 모든 불릿(108줄), 전역 CLAUDE.md 의 모든 불릿, AGENTS.md 의 모든 불릿, 훅 8스크립트 + 전역 훅 2종, 플러그인 3종, 프로젝트 스킬 5종 + `.claude/commands` 4종, 메모리는 type 별 표본(§5 항목 12), MCP 서버 목록. 각 항목에 ID(`P-01`, `G-01`, `A-01`, `H-01`, `K-01`, `M-01`, `C-01`)를 붙인다.
2. **층 분류**(§4.1) → **증거 수집**(아래 원천) → **판정**(§4.2) → 원장 행 작성.
3. 증거 원천과 명령:
   - 가드 발화: `docs/harness/logs/SHELL_GUARD_LOG.md`(테스트 오염 행은 같은 초 20행 이상 묶음으로 식별해 제외).
   - 훅 실패·발화: `docs/harness/logs/CLAUDE_HOOK_LOG.md`, `HOOK_RUNTIME_LOG.txt`.
   - 규칙 위반 재발: `docs/AI_CHANGELOG.md` 와 `git log --since=2026-08-03` 에서 "잘못", "재발", "혼입", "한자", "production" 검색. 각 재발이 어느 규칙과 대응하는지 적는다.
   - 절차 효과: `docs/plans/*ledger*.md` 의 최종 상태 집계.
   - 내장 프롬프트 중복: `claude-code-guide` 에이전트 질의 결과.
   - 지연: §2.2 의 측정 스크립트 재실행(값이 ±20% 넘게 다르면 재측정 표기).
4. 원장을 채운 뒤 **판정 분포**(층×판정 교차표)와 **절감 추정**(줄 수·토큰 추정·도구 호출당 ms)을 보고서 ①에 낸다.

## 7. 실험 설계 (2단계 — 이번 ablation 이 지난번과 다른 이유)

### 7.1 팔(arm) 3개
- **A 현행**: 지금 그대로(플러그인·훅·CLAUDE.md·메모리 전부).
- **B 최소**: 프로젝트 CLAUDE.md 를 §5 항목 16·17 의 L2·L3 만 담은 **40줄 이하 초안**으로 교체, 전역 CLAUDE.md 는 빈 파일, 플러그인 전부 off, 전역 orca 훅 제거, 프로젝트 훅은 L1 만(guard_shell·quality_check·track_edits 의 동시편집 감지, post_push_watch), 메모리 없음.
- **C 무규칙**: CLAUDE.md 없음, 훅 없음(permissions.deny 3줄만), 플러그인 off, 메모리 없음. H3 의 실패 지점을 드러내는 대조군이다.

### 7.2 재현 과제 4개(객관 성공 기준이 있는 것만)
2026-08-03 이후 `fix:` 커밋 중 **테스트 파일을 함께 추가했고 변경 파일 5개 이하**인 것에서 고른다. 후보 추출: `git log --since=2026-08-03 --diff-filter=A --name-only --format="%h %s" -- tests | grep -B1 -E "^tests/"`. 과제 유형을 섞는다: 버그 수정(RCA 필요) 2, 소형 기능 1, 승격 절차 1(cherry-pick 시나리오는 실제 push 대신 `--dry-run`·PR 생성 직전까지).
- 각 과제: 수정 커밋의 **부모** 커밋으로 `c:/tmp/abl-<과제>-<팔>` 워크트리를 만든다. 과제 프롬프트는 그 커밋의 메시지·AI_CHANGELOG 행에서 **증상만** 추려 쓴다(해법 힌트 금지).
- 성공 판정: 에이전트 작업 뒤 실제 수정 커밋의 테스트 파일을 복사해 넣고 실행. 통과 = 성공. `import app` 도 통과해야 한다.
- 승격 과제의 성공 = 자기 커밋만 cherry-pick 한 워크트리 + `gh pr create --dry-run` 상당 산출, `production` 직접 push 시도 0회.

### 7.3 기동 방법(실행 전 `claude-code-guide` 로 플래그 실존 확인 필수)
- 비대화 실행: `claude -p "<과제 프롬프트>" --output-format json --permission-mode bypassPermissions` — 결과 JSON 의 사용량(입력·출력 토큰, 턴 수, 소요 시간, 비용)을 지표로 쓴다.
- 팔별 전역 격리: `CLAUDE_CONFIG_DIR=c:/tmp/abl-cfg-<팔>` 에 전역 `settings.json`·`CLAUDE.md`·플러그인 상태를 팔대로 구성한 사본을 둔다(메모리 디렉토리는 비워 둔다).
- 팔별 프로젝트 격리: 워크트리 안의 `CLAUDE.md`·`.claude/settings.json` 을 팔대로 편집한다(추적 파일이지만 워크트리 안에서만 바꾸고 커밋하지 않는다). 훅이 실 로그(`docs/harness/logs`)에 쓰는 것을 막기 위해 워크트리의 로그 경로가 워크트리 내부인지 `shared_utils.harness_runtime_path` 로 확인한다.
- 모델·effort 는 세 팔 동일(`claude-fable-5-1`, xhigh). 과제당 팔당 1회, 총 12회. 비용이 과하면 팔 C 는 과제 2개만.

### 7.4 지표(과제×팔 표, 빈칸 금지)
| 지표 | 측정 |
|---|---|
| 성공 | 7.2 기준 통과/실패 |
| 턴 수·도구 호출 수 | JSON `num_turns`, 트랜스크립트의 tool_use 수 |
| 토큰(입력·출력·캐시) | JSON 사용량 |
| 소요 시간 | JSON `duration_ms` |
| 규칙 위반 | production push 시도(가드 로그), 한자 유출(§9.4 스니펫), 마지막 AskUserQuestion 유무, 인라인 스타일 추가, `-m "한글"` 커밋, bare except 추가 — 각 0/1 |
| 스킬 호출 수 | 트랜스크립트의 Skill 도구 호출 수(팔 A 에서 과호출 여부) |
| 사용자 개입 필요 | 질문으로 멈춘 횟수 |

해석 규칙: B 가 A 와 성공 동률이고 턴·시간이 적으면 H1 지지. C 가 규칙 위반을 내면 그 위반이 걸린 규칙은 L2 로 확정(KEEP-FACT). A 에서만 나타나는 이상(스킬 과호출·형식 흔들림)은 §5 항목 1·2 에 귀속시켜 H4 근거로 쓴다. 표본이 작으므로 **"경향" 이상으로 단정하지 않는다** — 보고서 ⑥ 열린 질문에 추가 실험 제안을 적는다.

## 8. 실행 방식

- 총괄 1(이 세션) + 정적 감사 워커 5 병렬(Agent 도구, 각각 원장 조각 파일을 씀): ① CLAUDE.md 2종+AGENTS.md 항목 분류·중복 매트릭스 ② 훅·전역 훅·지연·로그 실효 ③ 플러그인·스킬·MCP·`/context` 분해 ④ 메모리 표본 30 감사 + `docs/plans` 완주율 ⑤ 재발 기록 대조(AI_CHANGELOG·git log ↔ 규칙 매핑). 워커에게는 이 프롬프트 경로와 담당 §만 준다. 워커 보고는 주장일 뿐이다 — 총괄이 원장에 합칠 때 표본 앵커를 직접 연다.
- 실험(§7)은 총괄이 순차로 돌린다(워크트리·설정 사본이 겹치면 오염).
- 리뷰: 원장 완성 뒤 리뷰어 1(편집 금지)이 "판정 규칙 §4.2 를 문자 그대로 적용했는가" 만 본다. 품질 취향 리뷰는 하지 않는다.
- Workflow 도구를 사용자가 명시하지 않았으므로 스크립트는 만들지 않는다. 필요하면 §8 을 그대로 옮기면 된다.

## 9. 결과물과 완료 기준

### 9.1 원장 열 (한 항목 한 행)
`ID | 원천 파일:행 | 항목 요약(20자) | 층 | 근거(수치·경로·명령) | 판정 | 절감(줄/토큰/ms) | 위험 | 복원 트리거 | 상태`

### 9.2 보고서 절
① 판정 분포와 절감 합계(팔별 `/context` 실측 포함) ② 상충·중복 매트릭스(어느 파일의 어느 줄이 어느 줄과 겹치는가) ③ 코드 가드 실효 판정(실제 발화 vs 오염 vs 오탐) ④ 실험 결과 표와 가설별 지지/기각 ⑤ 제안 적용 순서(위험 낮은 것부터, 각 단계의 롤백 한 줄) ⑥ 열린 질문(사용자 결정 필요: caveman 유지, orca 기원, 등급 마커 유지, 메모리 상한) ⑦ 부록: 사소한 발견.

### 9.3 초안 폴더
- `CLAUDE.md.proposed` — 40줄 이하 목표. L2·L3 + L1 포인터만.
- `CLAUDE.global.md.proposed` — 프로젝트 무관 취향만(비어 있어도 된다).
- `settings.json.proposed` — 유지할 훅만.
- `DELETE_LIST.md` — 삭제·비활성 대상 경로와 명령(사용자가 실행).
- `tests_harness_drift_guard.py.proposed` — 플러그인 훅 비활성 상태, CLAUDE.md 줄 수 상한, MEMORY.md 줄 수 상한, CLAUDE.md↔AGENTS.md 중복 문단 0 을 단언하는 테스트 초안.

### 9.4 완료 기준(총괄이 직접 재실행)
- 원장 항목 전수 판정(빈 판정 0), 모든 근거에 명령 또는 경로:행.
- 실험 표 12칸(또는 축소 시 사유 명기) 빈칸 0.
- 앵커 실존·한자 검사 스니펫 통과(ANCHOR_BAD 0 · HANJA 0):
```python
import re, pathlib
docs = ["docs/plans/2026-09-09-harness-ablation-v2-report.md", "docs/plans/2026-09-09-harness-ablation-v2-ledger.md"]
bad = 0; hanja = 0
for d in docs:
    t = pathlib.Path(d).read_text(encoding="utf-8")
    hanja += len(re.findall(r"[\u4e00-\u9fff]", t))
    # 디렉토리가 붙은 경로만 검사한다(문장 안에서 디렉토리를 앞서 말한 뒤 쓰는 맨 파일명은 앵커가 아니다)
    for m in re.finditer(r"`((?:~|[A-Za-z]:)?[\w.\\-]*/[\w./\\-]+\.(?:py|md|json|js|css|html|ps1|yml))(?::(\d+))?`", t):
        raw = m.group(1)
        if raw.startswith(("c:/tmp", "C:/tmp")) or raw.endswith(".proposed"): continue
        p = pathlib.Path(raw.replace("~", str(pathlib.Path.home()), 1) if raw.startswith("~") else raw)
        if not p.exists(): bad += 1; print("ANCHOR_BAD", m.group(0))
print("ANCHOR_BAD", bad, "HANJA", hanja)
```
- `git status --porcelain` 에 신규 `docs/plans/2026-09-09-harness-ablation-v2-*` 외 변경 0. `c:/tmp/abl-*` 워크트리는 `git worktree list` 로 나열하고 사용자에게 정리 여부를 묻는다(자동 삭제 금지).

## 10. 금지·경계

- 이 세션은 **판정만** 한다. CLAUDE.md·훅·플러그인·메모리를 실제로 지우거나 끄지 않는다(실험용 사본·워크트리 제외). 적용은 사용자가 DELETE_LIST 를 보고 결정한다.
- 실험 워크트리에서 `git push`·`gh pr create`(dry-run 제외)·패키지 설치·운영 DB 접속 금지. 승격 과제는 push 직전에서 멈춘다.
- "모델이 좋아졌으니" 는 근거가 아니다. 근거는 로그 수치·재발 기록·실험 표·내장 프롬프트 교차 확인 넷뿐이다.
- 삭제 판정에는 반드시 복원 트리거를 붙인다(R2). 트리거 없는 DELETE 는 리뷰어가 반려한다.
- 한글로 쓰고 한자를 쓰지 않는다. 코드·경로·명령·에러 문자열은 원문 그대로.
