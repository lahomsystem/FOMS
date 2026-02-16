# Architecture Decisions Log

> 중요한 기술/아키텍처 결정을 기록합니다. AI가 이전 결정을 기억하도록 합니다.

## 결정 기록 형식
```
### [날짜] 결정 제목
- **컨텍스트**: 왜 이 결정이 필요했는가
- **결정**: 무엇을 결정했는가
- **이유**: 왜 이것을 선택했는가
- **영향**: 어떤 파일/시스템에 영향을 주는가
```

## 기록

### [2026-02-16] Flask 유지 + 점진 고도화 전략
- **컨텍스트**: SvelteKit 전면 마이그레이션 vs Flask 유지 검토
- **결정**: 기존 Flask 스택 유지, Strangler Fig 패턴으로 점진 개선
- **이유**: 전면 마이그레이션 리스크 과대, 기존 스택 충분히 유효
- **영향**: 전체 프로젝트 방향성, app.py Blueprint 분리 1순위

### [2026-02-16] MCP 22개 → 6개 최적화
- **컨텍스트**: 과다 MCP 설치로 리소스 낭비 및 에러 발생
- **결정**: 핵심 6개만 유지 (sequential-thinking, mcp-reasoner, context7, postgres, memory, markitdown)
- **이유**: 실제 사용 빈도와 안정성 기준으로 선별
- **영향**: mcp.json, cursor rules 업데이트

### [2026-02-16] 컨텍스트 엔지니어링 시스템 도입
- **컨텍스트**: AI 세션 간 기억 상실, 지시 미준수 문제
- **결정**: Hooks + Rules + Subagents + Memory MCP 통합 시스템
- **이유**: Hooks는 결정적(deterministic), Rules는 가이드라인, Memory는 영속 저장
- **영향**: .cursor/hooks.json, docs/context/, .cursor/rules/, .cursor/agents/

### [2026-02-16] services/ 폴더 도입 완료 (Phase 1)
- **컨텍스트**: 규칙(02-architecture)에 정의된 services/ 구조 미적용 상태
- **결정**: business_calendar, erp_policy, storage를 services/로 이전
- **이유**: 비즈니스 로직을 한 곳에 두고, app.py는 Blueprint 등록만 담당하도록 구조 정렬
- **영향**: services/ 신규, app.py·apps/erp.py·apps/api/files.py·erp_automation.py·erp_build_step_runner.py import 경로 변경, 루트 business_calendar.py·erp_policy.py·storage.py 삭제
