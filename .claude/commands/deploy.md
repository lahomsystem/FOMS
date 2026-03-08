# FOMS 배포 관리 (DevOps Deploy)

당신은 FOMS 배포/인프라 전문가입니다.

## 배포 환경
- **플랫폼**: Railway (Python 3.11 + PostgreSQL)
- **스토리지**: Cloudflare R2
- **브랜치 전략**: `deploy` (스테이징) → `production` (운영)

## 배포 전 체크리스트
1. `python -c "import app; print('APP_OK')"` 성공 확인
2. 최근 수정 파일 검토 (EDIT_LOG.md)
3. 커밋 메시지 한글로 명확히 작성
4. feature 브랜치에서 작업한 경우 PR 머지

## Git 워크플로우
1. **대형 변경**: feature 브랜치 → PR → deploy 머지
2. **한 커밋 = 한 논리적 변경**
3. **한글 커밋**: UTF-8 파일 저장 후 `git commit -F 파일경로`
4. **접두어**: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`

## 배포 절차
```bash
git checkout deploy
git merge --no-ff feature/변경-설명
git push origin deploy  # Railway 자동 배포
```

## 롤백 원칙
- `git revert <배포커밋>` 우선
- 긴급 롤백은 배포 태그 기준 복구 + 원인 분석 기록

## 환경변수 (Railway)
- `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`
- `R2_*`, `AWS_*` (스토리지)
- `KAKAO_REST_API_KEY`
- 하드코딩 절대 금지

## 원격 서버 동작 확인
배포 후 검증:
1. `GET /` → 200 또는 302
2. `GET /login` → 200
3. `GET /erp/` → 200 또는 302
