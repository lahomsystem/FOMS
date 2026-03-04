# GitHub Copilot 지침 — FOMS 프로젝트

## 절대 규칙: 문제 수정 정책

1. **근본 원인 파악 → 근본 수정만 허용**
   - 증상만 덮는 수정 절대 금지
   - 에러 숨기기(빈 catch, pass, 경고 무시) 절대 금지
   - deprecated API, 레거시 패턴 사용 금지

2. **수정 순서**: 현상 확인 → 근본 원인 분석 → 현대적 방법으로 설계 → 구현 → 검증

3. **예외 없음**: 긴급/시간 부족은 예외 사유가 될 수 없음

## 프로젝트 스택
- Flask 2.3 + SQLAlchemy 2.0 + PostgreSQL + Jinja2 + Bootstrap 5 + Vanilla JS
- Windows 11 / PowerShell 환경
- Git 커밋 메시지: 한글, 무엇을 왜 수정했는지 명확히 기록
