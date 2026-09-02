# Macro-Micro Migration Plan

- Generated at (UTC): 2026-08-31T07:00:35.245019+00:00
- Top tracks: ai_coding, integration, backend, tech_stack
- Focus-aligned signals (current stack fit): 45

## AI Coding Ecosystem Coverage

| Provider | Signals |
|----------|--------:|
| arxiv | 43 |
| github | 31 |
| openai | 15 |
| anthropic | 9 |
| google | 9 |
| meta | 6 |
| microsoft | 4 |
| other | 3 |

## Recommended Stack Combinations

### Option 1. Agent-Native Modular Platform
- Fit tracks: ai_coding, integration, backend
- Stack:
  - Model routing layer (OpenAI/Claude/Gemini)
  - MCP tool bus + policy guard
  - FastAPI service slices + existing Flask bridge
  - PostgreSQL + Redis + async workers
  - Eval/benchmark pipeline + experiment registry
- Short-term focus: 멀티 모델 실험과 안전한 도입 기준을 먼저 정립
- Mid-term focus: 핵심 도메인 서비스 모듈화를 병행하며 AI coding workflow 내재화
- Long-term focus: 자가 업그레이드 가능한 agentic delivery platform으로 고도화

### Option 2. Enterprise AI Engineering OS
- Fit tracks: ai_coding, tech_stack, integration
- Stack:
  - Organization-wide coding agent governance
  - Prompt/version/eval/policy lifecycle management
  - Rule/Skill/Hook/Agent continuous refinement
  - Risk-aware rollout and rollback automation
  - Cross-team engineering knowledge graph
- Short-term focus: 표준 운영 모델과 평가 지표를 수립
- Mid-term focus: 팀 단위 파일럿을 조직 표준으로 확장
- Long-term focus: 지속적 자가 진화형 개발 운영체계 확립

### Option 3. Systemic Frontend + UX Intelligence
- Fit tracks: frontend, uiux, ai_coding
- Stack:
  - TypeScript-first UI module architecture
  - Design token + component governance
  - Visual regression + interaction testing
  - AI-assisted UX telemetry analysis
  - Accessibility baseline enforcement
- Short-term focus: 템플릿 대형화/중복을 빠르게 줄이고 UI 일관성 확보
- Mid-term focus: 컴포넌트 단위 개발/검증 파이프라인 전환
- Long-term focus: 사용자 행동 기반 UX 최적화 자동 루프

## Macro Plan

### short_term_0_4_weeks - 멀티 AI 코딩 생태계 실험 기반 수용
- 모델/에이전트 비교 실험 트랙 수립 (OpenAI/Claude/Gemini/Copilot)
- 현재 코드베이스 영향도 분석 및 호환성 매트릭스 작성
- P1 액션 2~3개 스파이크 실행 + 회귀 테스트 자동화

### mid_term_1_3_months - 스택 전환 기반 구축 및 운영 표준화
- 상위 후보 스택 1개 선택 후 파일럿 마이그레이션
- 서비스 경계/인터페이스 계약/배포 롤백 표준 수립
- AI 코딩 툴링 평가 기준(속도/품질/비용) 운영

### long_term_3_12_months - 자가 업그레이드 가능한 AI-통합 개발 플랫폼 완성
- Rules/Skills/Hooks/Agents 자동 개선 루프 고도화
- MCP 도구 체계의 안전 정책/감사 추적 자동화
- 아키텍처 진화 의사결정을 KPI 기반으로 상시 운영

## Micro Execution Blueprint

| ID | Priority | Track | Owner | Title | Detail Design | DoD |
|----|----------|-------|-------|-------|---------------|-----|
| M-001 | P1 | ai_coding | coding-research-center | LLM-Augmented Causal Discovery: Probabilistic Fusion of Edge Existence and Orientation | Run controlled pilot for 'LLM-Augmented Causal Discovery: Probabilistic Fusion of Edge Existence and Orientation' in one workflow, compare dev-time and defect metrics. | 기능/테스트/롤백 경로 검증 완료 |
| M-002 | P1 | integration | devops-deploy | 0.151.0 | Review cross-stack impact of '0.151.0', then split work into backend/frontend/devops tasks. | 기능/테스트/롤백 경로 검증 완료 |
| M-003 | P0 | ai_coding | coding-research-center | v2.1.251 | Run controlled pilot for 'v2.1.251' in one workflow, compare dev-time and defect metrics. | 기능/테스트/롤백 경로 검증 완료 |
| M-004 | P0 | ai_coding | coding-research-center | langchain==1.4.0a1 | Run controlled pilot for 'langchain==1.4.0a1' in one workflow, compare dev-time and defect metrics. | 기능/테스트/롤백 경로 검증 완료 |
| M-005 | P0 | ai_coding | coding-research-center | v2.1.248 | Run controlled pilot for 'v2.1.248' in one workflow, compare dev-time and defect metrics. | 기능/테스트/롤백 경로 검증 완료 |
| M-006 | P0 | backend | python-backend | v3.4.0 | Create spike branch to validate backend impact of 'v3.4.0', then run API smoke tests. | 기능/테스트/롤백 경로 검증 완료 |
| M-007 | P0 | tech_stack | evolution-architect | Release: v5.16.0 | Build compatibility matrix for 'Release: v5.16.0' and execute dependency upgrade rehearsal. | 기능/테스트/롤백 경로 검증 완료 |
| M-008 | P0 | ai_coding | coding-research-center | Release v5.16.1 | Run controlled pilot for 'Release v5.16.1' in one workflow, compare dev-time and defect metrics. | 기능/테스트/롤백 경로 검증 완료 |
| M-009 | P0 | tech_stack | evolution-architect | v0.28.0 | Build compatibility matrix for 'v0.28.0' and execute dependency upgrade rehearsal. | 기능/테스트/롤백 경로 검증 완료 |
| M-010 | P1 | integration | devops-deploy | v2.1.246 | Review cross-stack impact of 'v2.1.246', then split work into backend/frontend/devops tasks. | 기능/테스트/롤백 경로 검증 완료 |
| M-011 | P1 | backend | python-backend | pg_statviz 1.2 released with PostgreSQL 19 support and new features | Create spike branch to validate backend impact of 'pg_statviz 1.2 released with PostgreSQL 19 support and new features', then run API smoke tests. | 기능/테스트/롤백 경로 검증 완료 |
| M-012 | P0 | ai_coding | coding-research-center | v2.1.0 | Run controlled pilot for 'v2.1.0' in one workflow, compare dev-time and defect metrics. | 기능/테스트/롤백 경로 검증 완료 |
