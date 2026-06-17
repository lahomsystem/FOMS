# GDM Retirement Spec
> 작성일: 2026-06-17 | 상태: ✅ 완료

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
FOMS의 활성 AI 운영 모델에서 GDM(Grand Develop Master)과 repo-local bespoke specialist agent 계층을 퇴역시킨다. Cursor IDE, Cursor 내 Claude, Cursor 내 Codex 하네스 번들은 더 이상 `.cursor/agents/grand-develop-master.md`, `.cursor/agents/GDM_EXECUTION_PLAN.md`, `.cursor/agents/*.md`, `.claude/agents/*.md`, 또는 GDM slash command를 진입점으로 안내하지 않는다.

활성 운영 모델은 다음으로 단순화한다.
- 공통 정책: `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/*.mdc`
- 실행 절차: RPI, `verify-result`, 성능 가드
- 스킬 계층: gstack skills, caveman response style
- 역사 기록: `docs/evolution/*GDM*`, closed `docs/plans/*gdm*`는 archive evidence로 보존

### 1.2 기능 요구사항
1. Cursor IDE에서 repo-local GDM 및 bespoke specialist agent 파일이 discoverable하지 않아야 한다.
2. Claude in Cursor에서 `/gdm` 및 retired specialist commands가 discoverable하지 않아야 한다.
3. Codex용 `_HARNESS` bundle이 GDM 오케스트레이션을 active architecture로 광고하지 않아야 한다.
4. research-center self manifest가 삭제된 `.cursor/agents/*` 파일을 기본 에이전트로 참조하지 않아야 한다.
5. Railway local-to-remote sync 문서와 스크립트는 GDM 언어 없이 동일한 안전 제약을 유지해야 한다.

### 1.3 예외/제약 조건
- gstack/caveman skill tree는 수정하지 않는다.
- 역사 문서와 closed run record는 삭제하지 않는다.
- `AGENTS.md`, `CLAUDE.md`, task classifier, hooks는 이미 GDM-free이므로 불필요하게 재작성하지 않는다.
- 앱 런타임, DB schema, 배포 설정은 변경하지 않는다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `.cursor/agents/*.md` | GDM 및 bespoke specialist agent 파일 삭제 |
| `.claude/agents/*.md` | retired specialist agent 파일 삭제 |
| `.claude/commands/*.md` | GDM/specialist duplicate command 삭제, perf/status commands 유지 |
| `.cursor/rules/14-incident-rca.mdc` | GDM trigger 제거, incident template + gstack debug/investigate 기준으로 갱신 |
| `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md` | active architecture를 gstack/caveman + shared policy 기준으로 재서술 |
| `tools/research_center/self_upgrade_manifest.json` | `.cursor/agents/*` 기본 에이전트 참조 제거 |
| `tools/research_center/coding_research_center.py` | `default_self_manifest()` 에이전트 목록 제거 |
| `tools/research_center/README.md` | 상위 GDM 기준 문구 제거 |
| `docs/guides/RAILWAY_LOCAL_TO_REMOTE_SYNC.md` | GDM 지휘/더블체크 문구 제거 |
| `scripts/ops/sync_local_to_railway.ps1` | GDM 절차서 주석 제거 |
| `docs/harness/policy/DECISIONS.md` | GDM 퇴역 결정 추가 |
| `docs/ARCHIVE_INDEX.md` | GDM archive note 추가 |
| `docs/AI_STATUS.md` | 현재 상태 기록 갱신 |
| `docs/harness/bundles/*_HARNESS.md` | generator로 재생성 |

### 2.2 아키텍처 방향
- repo-local bespoke agent layer를 제거하고, 상위 정책과 gstack/caveman skills를 명확히 분리한다.
- RCA, review, QA, deploy 같은 역할은 gstack skills와 공통 FOMS 정책으로 처리한다.
- 과거 GDM 산출물은 운영 참고 기록으로 남기되, 현재 진입점으로 오해되지 않게 표시한다.

### 2.3 의존성 및 영향 범위
- DB 마이그레이션 없음.
- Flask 앱 런타임 변경 없음.
- Cursor/Claude/Codex 하네스 문서와 generated bundles가 주 영향 범위다.

## 3. Steps — 실행 단계
- [x] Step 1: GDM 퇴역 Spec과 Decision/Archive/AI status 기록 추가
- [x] Step 2: Cursor/Claude bespoke agent 및 GDM command 삭제
- [x] Step 3: active GDM 참조를 gstack/caveman/shared policy 기준으로 재작성
- [x] Step 4: harness bundles 재생성
- [x] Step 5: active-reference 검색, harness test, perf guard, APP_OK 검증

## 4. 검증 기준
- [x] `python tools/harness/build_context_bundle.py --all` 통과
- [x] `pytest tests/harness/test_context_bundle.py -q` 통과
- [x] `python tools/perf/perf_scan.py --guard` 통과
- [x] `python -c "import app; print('APP_OK')"` 통과
- [x] active surfaces에서 `grand-develop-master`, `GDM_EXECUTION_PLAN`, `GDM`, `개발 총괄`, `총괄 감독` 참조가 제거됨

## 5. 참고 자료
- 관련 결정: `docs/harness/policy/DECISIONS.md` — 2026-06-17 GDM retirement
- 관련 과거 기록: `docs/ARCHIVE_INDEX.md`의 GDM-named evolution/plans entries
- 현재 운영 모델: gstack + caveman + FOMS shared policy
