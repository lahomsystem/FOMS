# Auth (canonical web slice — FR20)

## 목적

인증·세션·로그인/프로필 **페이지**의 canonical web owner를 둔다.

## 주요 모듈

| 모듈 | 역할 |
|------|------|
| `__init__.py` | 패키지 초기화 |
| 기타 `*.py` | 인증 관련 페이지 라우트 |

관련 API는 `foms/api/auth/` 와 함께 읽는다.

## 읽기 순서

1. `foms/platform/blueprints.py` — auth blueprint 등록
2. 본 디렉터리
3. `foms/api/auth/` — 인증 API

## 금지 의존성

- quarantine/non-product 트리 import 금지.
