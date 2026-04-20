# Files (API-first context — FR20)

## 목적

첨부·업로드·스토리지 **API**의 canonical owner를 둔다. (human-facing 첨부 UI는 해당 context 템플릿과 함께.)

## 주요 모듈

| 모듈 | 역할 |
|------|------|
| `__init__.py` | Blueprint |
| 기타 | presigned URL, 업로드, 내부 첨부 API |

`foms/services/files/` (예: storage)와 짝을 이룬다.

## 읽기 순서

1. `foms/platform/blueprints.py`
2. 본 디렉터리
3. `foms/services/files/`

## 금지 의존성

- quarantine/non-product 트리 import 금지.
