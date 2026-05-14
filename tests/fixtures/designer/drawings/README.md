# FOMS Brain Drawing Fixture Corpus

> PG-B2: Drawing Attachment Corpus + Fixture Harness

## 개요

이 디렉터리는 FOMS Brain의 가구 도면 추출 정확도를 측정하기 위한 **golden corpus**다.

## 디렉터리 구조

```
tests/fixtures/designer/drawings/
├── README.md                         # 이 파일
├── manifest.json                     # 17장 fixture 목록 + 상태
├── expected_extractions/             # 사용자 승인된 expected JSON
│   ├── wrd_001_expected.json
│   ├── wrd_002_expected.json
│   └── ...
└── (실제 도면 이미지/PDF는 .gitignore로 제외)
```

## Fixture 등록 방법

```powershell
# 새 도면 등록 (expected JSON AI 초안 자동 생성)
python tools/designer/build_drawing_fixture_manifest.py ingest --file path/to/drawing.jpg --id wrd_001

# Gemini로 expected JSON 초안 생성
python tools/designer/generate_expected_json.py --fixture-id wrd_001

# 사용자 승인 후 상태 업데이트
python tools/designer/build_drawing_fixture_manifest.py approve --fixture-id wrd_001
```

## Corpus 진행 상태

| 버전 | 목표 | 현재 |
|---|---|---|
| v0 | 5장 POC | 0장 approved |
| v1 | 17장 전체 | 0장 approved |
| v2 | 50장 익명화 | 예정 |
| v3 | 100장 운영 regression | 예정 |

## Expected JSON 스키마

각 fixture의 expected JSON은 다음 필드를 포함한다:

```json
{
  "drawing_id": "wrd_001",
  "page_no": 1,
  "customer_name": "홍길동",
  "product_name": "붙박이장",
  "site_size": {"width_mm": 2400, "height_mm": 2400, "depth_mm": 620},
  "furniture_type": "wardrobe",
  "parts_table": [
    {"code": "[SR]", "description": "선반", "quantity": 6, "note": ""}
  ],
  "dimension_candidates": [
    {"value_mm": 2400, "axis": "width", "view": "front"}
  ],
  "views": ["front", "side"],
  "notes": "마이다 포함, 손잡이 없음"
}
```

## Gemini 추출 정확도 목표 (PG-B5/B6 acceptance)

- W/D/H 추출 정확도: **>= 95%** (±5mm tolerance)
- 부품표 recall: **>= 90%**
- 치수선 number recall: **>= 90%**

## 보안 주의

- 실제 도면 이미지/PDF는 `.gitignore`에 의해 git 추적 제외
- 고객명/전화/주소는 `expected_json`에만 내부 보관 (PG-B3A PII 처리 참고)
- Gemini API payload에는 반드시 pseudonymized 값만 전송
