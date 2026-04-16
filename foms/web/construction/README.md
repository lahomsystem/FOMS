# Construction (canonical web slice — FR20)

## 목적

시공(Construction) 단계 **페이지** Blueprint의 canonical 구현을 둔다.

## 주요 모듈

본 디렉터리의 페이지 라우트·템플릿 조립 모듈. 관련 API는 `foms/api/construction/`, 서비스는 `foms/services/` 내 시공 도메인과 함께 읽는다.

## 읽기 순서

1. `foms/platform/blueprints.py` — 등록 확인
2. 본 디렉터리 `*.py`
3. 대응 API·서비스 패키지

## 금지 의존성

- quarantine/non-product 트리 import 금지.
