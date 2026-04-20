# Admin (canonical web slice — FR20)

## 목적

관리자 **페이지** Blueprint의 canonical 구현을 둔다.

## 주요 모듈

| 모듈 | 역할 |
|------|------|
| `__init__.py` | 패키지 초기화 |
| `*.py` | 관리자 화면 라우트·템플릿 조립 (개별 파일은 디렉터리 목록 기준) |

관련 API는 `foms/api/admin/` 과 함께 읽는다.

## 읽기 순서

1. `foms/platform/blueprints.py` — admin blueprint 등록
2. 본 디렉터리 모듈
3. `foms/api/admin/` — 관리자 JSON/API

## 금지 의존성

- quarantine/non-product 트리 import 금지 (`2026-04-13` §2.5).
