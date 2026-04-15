# SFC-B9 — API package-shape normalization

> Batch: `SFC-B9`  
> 실행일: 2026-04-15  
> 성격: **code** (실행 계획 `§6.12`, rebaseline SPEC `§2.2.1` `foms/api/`)  
> 선행: `SFC-B8`

## 1. 목표

- `foms/api/files.py`, `foms/api/measurement.py`, `foms/api/measurement_map.py` flat 모듈을 **패키지 디렉터리**로 전환한다.
- `public import contract`는 `__init__.py` 재노출로 유지; 기능 변경은 하지 않는다.

## 2. Authoritative target shape (계획 §6.12)

| 경로 | 내용 |
|------|------|
| `foms/api/files/__init__.py` | `get_storage`, `files_bp`, URL 빌더 재노출 |
| `foms/api/files/routes.py` | 구 `files.py` 본문 |
| `foms/api/measurement/__init__.py` | `erp_edit_required`, 큐·디스플레이 바인딩, `erp_measurement_bp`, `api_erp_measurement_update` 재노출 |
| `foms/api/measurement/routes.py` | 구 `measurement.py` 본문; 런타임에서 패키지 속성 갱신(테스트 monkeypatch)을 위해 `import foms.api.measurement as measurement_api`로 위임 호출 |
| `foms/api/measurement/map.py` | 구 `measurement_map.py` 본문 |

## 3. 제거된 flat 파일

- `foms/api/files.py`
- `foms/api/measurement.py`
- `foms/api/measurement_map.py`

## 4. 소비자 갱신

- `foms/api/erp_map.py`: `from foms.api.measurement.map import measurement_*`
- 계약 테스트: `measurement_map` 모듈 → `from foms.api.measurement import map as measurement_map`; lazy geocode fallback 검사는 `foms.api.measurement.routes` 소스로 이동

## 5. 계약 테스트

- `test_strict_canonical_api_package_shape_sfc_b9`: flat twin 없음 + `files/`·`measurement/` 패키지 필수 파일 고정

## 6. SG3 참고

- B1 §3.4의 `foms/api/files`·`foms/api/measurement` **디렉터리 노드** 누락은 본 배치로 해소.

## 7. 검증

| 검사 | 결과 |
|------|------|
| `python -c "import app; print('APP_OK')"` | `APP_OK` |
| `python tools/harness/verify_result.py --json` | `success: true` |
| `pytest tests` | **577 passed** |
