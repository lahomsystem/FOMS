# 3/16 필터 시 2건 미표시 문제 — 해결 과정 분석 보고서

- **작성일**: 2026-03-16
- **대상**: measurement-map-rebuild-spec 구현 후 17건 중 2건 지도 미표시
- **실제 원인**: 동일 아파트 주소 → 동일 좌표 → 마커 겹침 (2662↔2655, 2670↔2650)
- **해결**: `_apply_marker_offset_for_duplicates`로 겹친 마커에 ~15m 오프셋 적용

---

## 1. 수정 항목별 평가

### 1.1 map_snapshot.py — `_measurement_date_variants` + regexp_replace

| 항목 | 내용 |
|------|------|
| **추가 시점** | 원인 파악 전, "날짜 형식 불일치" 가설로 도입 |
| **역할** | OrderScheduleDate.date가 6가지 형식(하이픈/점/슬래시, zero-pad 유무)으로 저장된 경우 모두 매칭 |
| **진단 결과** | DB의 date는 모두 `'2026-03-16'` (표준 형식). **날짜 형식 문제 아님** |
| **코드량** | ~25줄 (함수 + 쿼리 OR 조건) |
| **난잡도** | 🟡 **중간** — 가설 기반으로 추가된 방어 코드, 현재 데이터에는 불필요 |

**판단**: 현재 DB 기준으로는 **과잉 방어**. `order_date_sync`의 `_normalize_date_str`로 저장 시 이미 YYYY-MM-DD 정규화되므로, 조회 시 6가지 형식 대응은 중복.

---

### 1.2 order_date_sync.py — `_normalize_date_str`

| 항목 | 내용 |
|------|------|
| **추가 시점** | 3/16 수정 과정에서 강화 또는 신규 추가 (EDIT_LOG 2026-03-15 다수 편집) |
| **역할** | 저장 시 날짜를 YYYY-MM-DD로 정규화 (레거시/structured_data 등 다양한 소스 대응) |
| **Phase 4 Spec** | "마이그레이션 도중 누락되는 날짜 포맷이 없도록 정규표현식 및 파서 고도화" 명시 |
| **난잡도** | 🟢 **양호** — 단일 책임, 재사용 가능, Spec 정렬 |

**판단**: **유지 권장**. 저장 파이프라인 정규화는 데이터 무결성에 필수. 3/16 이슈와 무관해도 Phase 4 설계 의도에 부합.

---

### 1.3 map_snapshot.py — `_apply_marker_offset_for_duplicates`

| 항목 | 내용 |
|------|------|
| **추가 시점** | 근본 원인(동일 좌표 마커 겹침) 규명 후 |
| **역할** | 동일 (lat,lng) 마커에 ~15m 나선형 오프셋 적용 → 2건 모두 표시 |
| **실제 효과** | 2662↔2655, 2670↔2650 등 겹침 해소 |
| **난잡도** | 🟢 **양호** — 목적 명확, 부작용 최소 |

**판단**: **필수 유지**. 이번 이슈의 실제 해결책.

---

## 2. 롤백 vs 수정 유지

| 옵션 | 내용 | 권장 |
|------|------|------|
| **전면 롤백** | 3개 수정 모두 제거 | ❌ 비권장 — 마커 오프셋 제거 시 2건 미표시 재발 |
| **수정 유지** | 현재 상태 그대로 유지 | ⚠️ 조건부 — 아래 단순화 후 유지 권장 |
| **선택적 단순화** | 불필요한 날짜 형식 대응 제거, 나머지 유지 | ✅ **권장** |

---

## 3. 단순화 권장 사항

### 3.1 제거 권장: `_measurement_date_variants` + regexp_replace

**이유**:
- DB 진단 결과: date는 모두 `'2026-03-16'` 형식
- 저장 경로(`order_date_sync._normalize_date_str`)에서 이미 YYYY-MM-DD 정규화
- 6가지 형식 + 숫자 추출 비교는 **현재·향후 데이터에 불필요한 복잡도**

**수정 예시** (`services/map_snapshot.py`):

```python
# 변경 전 (L98-113)
date_variants = _measurement_date_variants(date)
date_digits = date.replace('-', '')[:8] if date else ''
query = query.filter(
    OrderScheduleDate.kind == 'measurement',
    or_(
        OrderScheduleDate.date.in_(date_variants),
        func.substring(
            func.regexp_replace(func.trim(OrderScheduleDate.date), r'[^0-9]', '', 'g'),
            1, 8
        ) == date_digits
    )
)

# 변경 후
query = query.filter(
    OrderScheduleDate.kind == 'measurement',
    OrderScheduleDate.date == date
)
```

- `_measurement_date_variants` 함수 전체 삭제
- `func.substring`, `func.regexp_replace` 등 불필요 import 정리

---

### 3.2 유지: `_normalize_date_str` (order_date_sync.py)

- 저장 시 날짜 정규화는 Phase 4 Spec 및 데이터 무결성에 필요
- 변경 없이 유지

---

### 3.3 유지: `_apply_marker_offset_for_duplicates` (map_snapshot.py)

- 동일 좌표 마커 겹침 해소의 실제 해결책
- 변경 없이 유지

---

## 4. 부수 정리 (선택)

### 4.1 map_snapshot.py import 순서

현재 `_measurement_date_variants` 정의 직후(33행)에 `from services.erp_display import ...` 등이 위치. 함수 정의와 import가 섞여 있음. `_measurement_date_variants` 제거 시 import를 파일 상단으로 정리하면 가독성 향상.

### 4.2 diagnose 스크립트

`scripts/diagnose_measurement_date_missing.py`는 진단용으로 유용. 삭제하지 말고 `docs/evolution/` 또는 `scripts/diagnostic/`에 보관 권장.

---

## 5. 요약

| 수정 | 난잡도 | 판단 | 조치 |
|------|--------|------|------|
| `_measurement_date_variants` + regexp_replace | 🟡 | 과잉 방어 | **제거** — `date == date` 단순화 |
| `_normalize_date_str` | 🟢 | 적정 | **유지** |
| `_apply_marker_offset_for_duplicates` | 🟢 | 필수 | **유지** |

**결론**: 롤백하지 말고, **날짜 형식 관련 코드만 단순화**한 뒤 나머지는 유지하는 것이 적절하다.
