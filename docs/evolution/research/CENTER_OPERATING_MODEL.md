# Coding Research Center Operating Model

## 목표
- 최신 코딩/AI 코딩 기술을 주 1회 탐색
- 딥리서치 결과를 즉시 실행 가능한 액션으로 변환
- 실행 결과를 다시 학습 데이터로 축적하여 진화
- Macro(장기)-Micro(단기) 마이그레이션 설계도를 자동 생성
- agents/rules/skills/mcp 자가 업그레이드 루프를 상시 운영

## 주간 운영 사이클
1. **Scan**: 공식 릴리즈/공식 블로그/RSS 수집
2. **Score**: 신뢰도/최신성/적합성 점수화
3. **Select**: P0/P1/P2 액션 큐 생성
4. **Ship**: 적용 후보를 스프린트에 투입
5. **Study**: 적용 후 지표/회귀/교훈 기록
6. **Scale**: 반복 성공 패턴을 Rule/Skill/Hook으로 승격

## 엔터프라이즈 거버넌스
- **Source Policy**: 1차 출처 우선, 비공식 정보는 보조 근거로만 사용
- **Risk Policy**:
  - P0: 보안/중대 호환성/운영 중단 리스크
  - P1: 생산성/품질 개선 신호(검증 후 도입)
  - P2: 중장기 투자 항목
- **Change Policy**:
  - 메이저 업그레이드는 호환성 매트릭스 + 롤백 리허설 필수
  - 트렌드성 기술은 파일럿 없이는 본 적용 금지

## KPI (권장)
- 리서치 생산성:
  - 주간 신호 수집 수
  - actionable 변환률(`actions/signals`)
- 적용 품질:
  - P1 이상 액션의 실제 반영률
  - 반영 후 회귀율
- 개발 효율:
  - 리드타임 변화
  - defect escape 변화
- 진화 품질:
  - 승격된 Rule/Skill/Hook 수
  - 동일 유형 재발률 감소

## 즉시 적용 파이프라인
1. `docs/evolution/research/apply_now_queue.json`에서 상위 P1 항목 선택
2. `evolution-architect`가 실험 범위 정의(DoD/Abort/Rollback)
3. `docs/evolution/research/MACRO_MICRO_MIGRATION_PLAN.md`에서 전체/부분/상세 설계 태스크 확정
3. 영역별 구현:
   - Backend: `python-backend`
   - Frontend/UIUX: `frontend-ui`
   - DB: `database-specialist`
4. 실행 전담: `migration-executor`
5. 배포 안전성 검증: `devops-deploy`
6. 결과 기록:
   - `docs/evolution/EXPERIMENT_LOG.md`
   - `docs/evolution/EVOLUTION_DECISIONS.md`

## 자가 업그레이드 파이프라인
1. `docs/evolution/research/SELF_UPGRADE_PLAN.md` 감사 결과 확인
2. 누락 자산(Agent/Rule/Skill/MCP) 우선순위 선정
3. 자동 생성/설치 가능한 항목 실행
4. 변경 영향 검증 후 운영 정책에 반영

## MCP 검색/업그레이드 파이프라인
1. MCP 공식 소스(`modelcontextprotocol/*`) 릴리즈 신호 수집
2. 후보 MCP에 대해 권한/보안/유지보수 상태 평가
3. `tools/research_center/self_upgrade_manifest.json`에 후보 등록
4. `--self-upgrade-sync-mcp`로 `~/.cursor/mcp.json` 동기화
5. 실패/충돌 시 `SELF_UPGRADE_PLAN.md`에 원인과 대체안 기록

## 실패 대응
- 소스 수집 실패:
  - 실패 소스를 리포트에 기록
  - 다음 주기 자동 재시도
- 적용 실패:
  - 즉시 롤백
  - 원인 분류(설계/호환성/테스트 누락)
  - 재시도 조건 명시 후 backlog로 환류

## 실행 명령
```bash
python tools/research_center/coding_research_center.py --days 9 --apply-limit 12 --sync-radar --sync-backlog --self-upgrade-sync-mcp
```

## 자동 실행
- GitHub Actions: `.github/workflows/coding-research-center-weekly.yml`
- 로컬 Windows Task Scheduler:
  - 등록: `tools/research_center/register_weekly_task.ps1`
  - 수동 실행: `tools/research_center/run_research_center.ps1`
