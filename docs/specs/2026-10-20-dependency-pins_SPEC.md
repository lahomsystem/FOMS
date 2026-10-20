# 오래된 부품 업데이트 — Pillow 12.3 · 의존성 버전 고정 · Dependabot — SPEC (2026-10-20)

## 목적
1. 이미지 라이브러리 Pillow 가 10.1.0(2023-10)에 고정돼 있다. 이 판에는 공개된 결함이 16건 붙어 있고(OSV 조회 2026-10-19, 고친 판 12.3.0), FOMS 는 업로드 썸네일·채널톡 첨부·공유 합본에서 받은 이미지를 형식 제한 없이 연다(`foms/services/storage.py`, `foms/api/share.py`, `foms/services/image_margin_trim.py`).
2. `requirements.txt` 의 20줄이 범위 핀(`>=`)이라 빌드할 때마다 그날의 최신판을 받는다. 같은 커밋이라도 언제 빌드됐느냐에 따라 다른 라이브러리로 돈다.
3. 버전을 올려야 할 때 알려 주는 장치가 없다(저장소 취약점 알림 꺼짐, `.github/dependabot.yml` 없음).

## 지금 구조
- 빌드: `Dockerfile` 이 `python:3.12-slim` 에서 `pip install -r requirements.txt`. CI(`ci.yml`·`harness-ci.yml`)도 같은 파일을 새로 설치하므로 CI 는 늘 "그날의 최신판" 으로 돌아 왔다.
- Pillow 쓰는 곳: `Image.open`·`Image.new`·`Image.Resampling`·`ImageChops` 뿐. 11·12 판에서 지워진 API(`ANTIALIAS`·`getsize`·`textsize` 등) 사용 0.

## 변경
1. `Pillow==10.1.0` → `Pillow==12.3.0`.
2. 범위 핀 19줄을 2026-10-20 에 pip 가 고르는 판(= CI 가 지금까지 설치해 온 판)으로 `==` 고정. 이 커밋으로 `requirements.txt` 가 바뀌어 다음 배포는 어차피 새로 설치되므로, 고정 값이 곧 다음 배포에 깔리는 판이다.

   | 패키지 | 전 | 후 |
   |---|---|---|
   | gunicorn | >=22.0.0 | 26.2.0 |
   | pydantic | >=2.9.0,<3 | 2.11.10 |
   | pydantic-settings | >=2.3.0 | 2.15.0 |
   | pydantic_core | >=2.23.0 | 2.33.2 |
   | typing_extensions | >=4.14.0,<5 | 4.16.0 |
   | folium | >=0.14.0 | 0.20.0 |
   | beautifulsoup4 | >=4.12.0 | 4.15.0 |
   | python-Levenshtein | >=0.21.0 | 0.27.5 |
   | flask-socketio | >=5.3.6 | 5.7.0 |
   | python-socketio | >=5.10.0 | 5.17.0 |
   | gevent | >=24.10.1 | 25.4.2 |
   | boto3 | >=1.28.0 | 1.43.115 |
   | redis | >=5.0.0 | 8.1.0 |
   | Flask-Limiter | >=3.5.0 | 4.1.1 |
   | rq | >=1.15.0 | 2.12.0 |
   | Flask-Compress | >=1.14 | 1.25 |
   | whitenoise | >=6.6.0 | 6.12.0 |
   | google-genai | >=2.2.0 | 2.8.0 |
   | sentry-sdk[flask] | >=2.66.1,<3 | 2.72.0 |
3. `.github/dependabot.yml` — pip 매주 월요일 09:00(KST)·GitHub Actions 매월. **대상 브랜치 deploy**(기본 브랜치가 production 이라 그냥 두면 운영으로 PR 이 간다). 부 버전·패치는 한 PR 로 묶고 열린 PR 최대 5.
4. 저장소 취약점 알림(Dependabot alerts) 켜기 — GitHub 설정. 알림은 저장소 관리자만 본다. 자동 보안 수정 PR 은 기본 브랜치(production)로 가므로 켜지 않는다.

## 건드리지 않는 것
- 간접 의존성 전체 잠금 파일. 개발 PC(Windows)와 운영(Linux)의 해석 결과가 달라 이 저장소에서 만들어 검증할 수단이 없다. 직접 의존성 고정 + Dependabot 으로 먼저 막고, 잠금 파일은 Linux CI 에서 만드는 별건으로 둔다.
- 쓰지 않는 듯한 의존성 정리(`pydantic-settings` 등 import 0) — 지우는 쪽은 실행 경로 확인이 따로 필요하다.

## 테스트
- 새 파일 `tests/domains/test_requirements_pinned.py`: 모든 줄이 `==` 고정 · Pillow ≥ 12.3 · dependabot 두 생태계 모두 deploy 대상.
- 고정 판 그대로 새 가상환경(Python 3.12)에 설치해 전체 스위트(visual·harness·postgres 제외) 실행: 12,691 통과, 실패 4건은 Windows 전용 `win32crypt` 가 가상환경에 없어서(DPAPI 테스트, 변경과 무관).
