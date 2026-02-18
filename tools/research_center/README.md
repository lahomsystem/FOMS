# Coding Research Center

엔터프라이즈급 코딩/AI 코딩 웹 리서치 센터 운영 도구입니다.

## 목표
- 주 1회 자동 웹 리서치
- 최신 코딩/AI 코딩 신기술 신호 수집 (OpenAI/Claude/Gemini/Copilot 등)
- 기술 스택/라이브러리/보안/테스트/관측/인프라까지 광범위 커버
- 즉시 적용 가능한 액션 큐 생성
- 매크로/마이크로 마이그레이션 설계 자동 생성
- agents/rules/skills/mcp 자가 업그레이드 감사 자동 생성
- 현재 FOMS 스택 적합도(program focus) 기반 우선순위 보정
- 진화 문서(`docs/evolution/*`)와 연결
- 상위 마스터 에이전트(`.cursor/agents/grand-develop-master.md`) 기준으로 실행/보고

## 실행
```bash
python tools/research_center/coding_research_center.py --days 9 --apply-limit 12 --sync-radar --sync-backlog
```

주간 실행(스케줄 등록):
```powershell
powershell -ExecutionPolicy Bypass -File tools/research_center/register_weekly_task.ps1 `
  -TaskName "FOMS-Coding-Research-Center" `
  -DayOfWeek MON `
  -StartTime "09:00" `
  -SelfUpgradeCreateStubs `
  -SelfUpgradeSyncMcp
```

## 주요 출력
- `docs/evolution/research/LATEST.md`
- `docs/evolution/research/apply_now_queue.json`
- `docs/evolution/research/reports/YYYY/YYYY-MM-DD-Wxx-coding-research.md`
- `docs/evolution/research/MACRO_MICRO_MIGRATION_PLAN.md`
- `docs/evolution/research/macro_micro_migration_plan.json`
- `docs/evolution/research/SELF_UPGRADE_PLAN.md`
- `docs/evolution/research/self_upgrade_audit.json`

## 옵션
- `--config`: 소스 설정 파일 경로
- `--days`: 리서치 기간(일)
- `--max-per-source`: 소스당 최대 수집 건수
- `--apply-limit`: 즉시 적용 큐 최대 건수
- `--sync-radar`: `docs/evolution/RADAR.md` 자동 반영
- `--sync-backlog`: `docs/evolution/HYPOTHESIS_BACKLOG.md` 자동 반영
- `--self-manifest`: 자가 업그레이드 매니페스트 경로
- `--self-upgrade-create-stubs`: 누락된 agent/rule 스텁 자동 생성
- `--self-upgrade-install-skills`: 누락된 skill 자동 설치 시도
- `--self-upgrade-sync-mcp`: 누락된 mcp 동기화 시도
- `--mcp-config`: mcp.json 경로 지정

## MCP 검색/설치/업그레이드
- MCP 신호는 `sources.json`의 MCP 공식 소스(`modelcontextprotocol/*`)에서 주기적으로 수집합니다.
- 신규 MCP 반영은 `self_upgrade_manifest.json`의 `mcps`에 등록 후 동기화합니다.
- `run_research_center.ps1`와 `register_weekly_task.ps1`는 기본값으로 MCP 동기화를 수행합니다.
- 권장 실행:
```bash
python tools/research_center/coding_research_center.py \
  --days 9 \
  --apply-limit 12 \
  --sync-radar \
  --sync-backlog \
  --self-upgrade-sync-mcp
```

## program_focus
- `tools/research_center/sources.json`의 `program_focus`는 "현재 프로그램에 적용 가능/업그레이드 가능" 신호를 점수로 보정합니다.
- 기본 키워드: Flask/SQLAlchemy/PostgreSQL/Redis/Jinja/Bootstrap/Pytest/Playwright/OpenTelemetry 등.
- `critical_keywords`(예: `security`, `breaking`, `migration`, `cve`)는 높은 가중치를 부여합니다.

## 소스 정책
- 1차 출처(공식 릴리즈/공식 블로그) 우선
- 점수 기반 우선순위(신뢰도 + 최신성 + 도메인 적합성)
- 실패 소스는 보고서에 자동 기록

## 운영 권장
1. 매주 리포트의 P0/P1 액션을 우선 검토
2. 스프린트에 1~3개만 선택 적용
3. 적용 후 smoke/regression 테스트 실행
4. `MACRO_MICRO_MIGRATION_PLAN.md`에서 실행 태스크를 분해
5. `SELF_UPGRADE_PLAN.md`에서 자가 업그레이드 항목 검토
6. 실험 결과를 `docs/evolution/EXPERIMENT_LOG.md`에 기록
