# 푸시 전 로컬 검증 (deploy/main)

`deploy` 또는 `main`에 **push하기 전**에 로컬에서 빠르게 돌리는 스모크 검증입니다. GitHub Actions 전체 CI를 대체하지 않습니다.

## Visual regression 정본 워크플로 (SSOT)

UI/CSS/레이아웃이 바뀌면 아래 순서를 **반드시** 따릅니다.

1. **CSS/JS/템플릿 구현** — `static/css/`, `static/js/`, `templates/` 등
2. **win32 baseline 재생성 (Windows 로컬)** — Playwright `--update-snapshots` → `tests/visual/baseline/win32/*.png`
3. **win32 PNG 커밋** — 같은 PR 또는 직후 커밋
4. **푸시 전 `-Visual` 스모크 통과** — `pre_push_smoke.ps1 -Visual` (exit 0)
5. **CI가 linux SSOT 자동 refresh** — `ci.yml` visual job이 win32보다 오래된 `baseline/linux/` ERP PNG를 `--update-snapshots` 후 bot 커밋

> **주의:** Windows에서 `baseline/linux/` PNG를 재생성·커밋하지 마세요. Linux baseline은 CI SSOT입니다.

### win32 baseline 갱신 명령 (Win11)

```powershell
cd "C:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"
$env:TEMP = "C:\tmp"
$env:TMP = "C:\tmp"
$env:DATABASE_URL = "sqlite:///tests/visual/visual_local.sqlite"
python -m pytest tests/visual --update-snapshots -q
git add tests/visual/baseline/win32/*.png
```

갱신 후 diff PNG를 눈으로 확인한 뒤 커밋합니다.

### stale 감지 (근본 수정)

| 검사 | 스크립트 | 의미 |
|------|----------|------|
| win32 vs CSS 소스 | `python scripts/ops/visual_baseline_stale.py --check-win32-vs-sources` | visual 소스(`static/css/`, `static/js/`, `templates/`) 최신 커밋이 win32 PNG 커밋보다 **새로우면** stale — CSS만 바꾸고 PNG를 안 갱신한 경우를 잡음 |
| linux vs win32 (CI seed) | `python scripts/ops/visual_erp_linux_stale.py` | win32 ERP PNG를 커밋한 뒤 linux가 뒤처지면 CI seed 단계 실행 |
| pre-push 게이트 | `pre_push_smoke.ps1` (기본) | visual 경로 변경 또는 win32 stale 시 **`-Visual` 없으면 FAIL** |

## 언제 실행하나

- `deploy` / `main`으로 push 직전
- PR 머지 전 자신감 확인 (빠른 회귀 방지)
- CI에서 자주 깨지는 영역(배포 Dockerfile, import 계약, HTMX, visual asset) 변경 후
- **UI/CSS/레이아웃 변경 후**: 기본 subset + **`-Visual` 필수** (win32 baseline 갱신·커밋 후)

## 명령 (Win11 / PowerShell 5.x)

저장소 루트에서:

```powershell
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1
```

CSS/템플릿을 건드렸다면:

```powershell
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Visual
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

- **선행조건**: `pip install playwright; python -m playwright install chromium`. 미설치 시 visual **FAIL**(silent skip 없음 — CSS 변경 게이트와 함께 사용 시).
- **env**: `TEMP/TMP=C:\tmp`, `DATABASE_URL=sqlite:///tests/visual/visual_local.sqlite`(live-server fixture가 파일 DB 공유)를 스크립트가 자동 설정.
- **플랫폼 baseline**: 로컬은 `tests/visual/baseline/win32/`. CI는 `linux` baseline을 쓰므로 **Windows에서 linux baseline을 재생성하지 말 것**. CI `test` job은 `--ignore=tests/visual`; visual job이 linux SSOT를 refresh합니다.

`-Full -Visual`처럼 조합 가능합니다.

## 무엇을 검사하나

| 단계 | 설명 |
|------|------|
| Visual 게이트 | visual 경로 변경 감지 + win32 stale vs CSS 소스 → `-Visual` 필수 |
| 환경 | `DATABASE_URL=sqlite:///:memory:`, `SECRET_KEY=ci-secret-key`, `FLASK_ENV=testing` |
| APP import | `python -c "import app; print('APP_OK')"` |
| Harness | `tools/harness/verify_result.py --json` (있을 때) |
| Design SSOT | `tools/design/ssot_lint.py docs/design` (있을 때) |
| Harness 번들 drift | `build_context_bundle.py --all` 재생성 후 `docs/harness/bundles/HARNESS_BUNDLE_*.md` drift 검사 (Harness CI와 동일). 드리프트면 FAIL — 재생성본을 커밋하면 해소 |
| Pytest subset | Dockerfile 계약, namespace import, search overlay, HTMX fragment, staging mobile v2 / P1 mockup visual / P1 chrome parity (CSS 계약) |
| Visual regression (`-Visual`) | `tests/visual` Playwright PNG compare (win32 baseline) |

> **Harness 번들 드리프트가 자주 CI를 깨뜨립니다.** `AGENTS.md`·`CLAUDE.md`·`tools/harness/*.yaml` 등 번들 소스를 수정하면 `python tools/harness/build_context_bundle.py --all`로 `docs/harness/bundles/HARNESS_BUNDLE_*.md`를 재생성하고 **함께 커밋**해야 합니다. 빠뜨리면 Harness CI의 `Check harness bundle drift`(`git diff --exit-code`)가 실패합니다. 본 스모크가 push 전에 이를 잡습니다.

기본 subset 목표 시간: **약 2–5분**.

## 중요

- 이 스크립트는 **git push 시 자동 실행되지 않습니다.** 수동 실행입니다.
- Push 후 **GitHub Actions**가 전체 CI(visual regression 포함)를 계속 실행합니다.
- AI 에이전트에게 push마다 전체 테스트 suite 실행을 요청하지 마세요. **로컬에서 이 스크립트를 실행**하고, 실패 시에만 에이전트에게 수정을 요청하세요 (토큰·시간 절약).

## 실패 시

1. 스크립트 출력의 `[FAIL]` 단계 확인
2. win32 stale → 위 SSOT 워크플로 1–4단계 (`--update-snapshots`, PNG 커밋, `-Visual`)
3. 해당 pytest만 단독 실행: `python -m pytest -v tests/...`
4. 수정 후 스크립트 재실행 → exit 0 확인 후 push

## 관련

- CI 정의: `.github/workflows/ci.yml`
- Linux baseline runbook: `docs/runbooks/visual-regression-baselines.md`
- stale 정책 구현: `scripts/ops/visual_baseline_stale.py`
- 에이전트 요약: `AGENTS.md` § 푸시 전 로컬 검증
