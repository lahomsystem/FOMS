# 푸시 전 로컬 검증 (deploy/main)

`deploy` 또는 `main`에 **push하기 전**에 로컬에서 빠르게 돌리는 스모크 검증입니다. GitHub Actions 전체 CI를 대체하지 않습니다.

## 언제 실행하나

- `deploy` / `main`으로 push 직전
- PR 머지 전 자신감 확인 (빠른 회귀 방지)
- CI에서 자주 깨지는 영역(배포 Dockerfile, import 계약, HTMX, visual asset) 변경 후

## 명령 (Win11 / PowerShell 5.x)

저장소 루트에서:

```powershell
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1
```

### 머지 직전 전체 pytest (느림)

```powershell
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Full
```

`-Full`은 CI `test` job과 유사하게 `tests/visual` 제외 전체 pytest를 실행합니다. 수 분 이상 걸릴 수 있습니다.

### 로컬 visual regression (win32 baseline)

```powershell
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Visual
```

`-Visual`은 Playwright 기반 `tests/visual` 전체(PNG regression 포함)를 로컬에서 실행합니다. 약 30초~수 분.

- **선행조건**: `pip install playwright; python -m playwright install chromium`. 미설치 시 `[SKIP]` 후 통과.
- **env**: `TEMP/TMP=C:\tmp`, `DATABASE_URL=sqlite:///tests/visual/visual_local.sqlite`(live-server fixture가 파일 DB 공유)를 스크립트가 자동 설정.
- **플랫폼 baseline**: 로컬은 `tests/visual/baseline/win32/`. CI는 `linux` baseline을 쓰므로 **Windows에서 linux baseline을 재생성하지 말 것**. CI는 `--ignore=tests/visual`이라 본 단계가 CI를 게이트하지 않습니다.
- **baseline 갱신(의도된 시각 변경 시만)**: `$env:TEMP='C:\tmp'; $env:DATABASE_URL='sqlite:///tests/visual/visual_local.sqlite'; python -m pytest tests/visual --update-snapshots` 후 PNG diff 검토하고 커밋.

`-Full -Visual`처럼 조합 가능합니다.

## 무엇을 검사하나

| 단계 | 설명 |
|------|------|
| 환경 | `DATABASE_URL=sqlite:///:memory:`, `SECRET_KEY=ci-secret-key`, `FLASK_ENV=testing` |
| APP import | `python -c "import app; print('APP_OK')"` |
| Harness | `tools/harness/verify_result.py --json` (있을 때) |
| Design SSOT | `tools/design/ssot_lint.py docs/design` (있을 때) |
| Pytest subset | Dockerfile 계약, namespace import, search overlay, HTMX fragment, staging mobile v2 / P1 mockup visual |

기본 subset 목표 시간: **약 2–5분**.

## 중요

- 이 스크립트는 **git push 시 자동 실행되지 않습니다.** 수동 실행입니다.
- Push 후 **GitHub Actions**가 전체 CI(visual regression 포함)를 계속 실행합니다.
- AI 에이전트에게 push마다 전체 테스트 suite 실행을 요청하지 마세요. **로컬에서 이 스크립트를 실행**하고, 실패 시에만 에이전트에게 수정을 요청하세요 (토큰·시간 절약).

## 실패 시

1. 스크립트 출력의 `[FAIL]` 단계 확인
2. 해당 pytest만 단독 실행: `python -m pytest -v tests/...`
3. 수정 후 스크립트 재실행 → exit 0 확인 후 push

## 관련

- CI 정의: `.github/workflows/ci.yml`
- 에이전트 요약: `AGENTS.md` § 푸시 전 로컬 검증
