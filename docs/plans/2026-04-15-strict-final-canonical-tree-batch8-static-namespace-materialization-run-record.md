# SFC-B8 — Static namespace materialization

> Batch: `SFC-B8`  
> 실행일: 2026-04-15  
> 성격: **code** (실행 계획 `§6.11`, rebaseline SPEC `§2.2.1` `static/`)  
> 선행: `SFC-B7`

## 1. 목표

- B1 gap inventory (`§3.4`)에 나온 **누락 `static` 노드**를 물리적으로 생성한다.
- 빈 디렉터리는 `SFC-B0` 정책대로 **`.gitkeep`** 단일 sentinel으로 추적한다.

## 2. B1 대비 이번 배치에서 채운 노드

| 경로 | 비고 |
|------|------|
| `static/js/drawing/.gitkeep` | drawing 컨텍스트 전용 JS 향후 수령 지점 |
| `static/js/production/.gitkeep` | production 컨텍스트 |
| `static/js/construction/.gitkeep` | construction 컨텍스트 |
| `static/js/cs/.gitkeep` | CS 컨텍스트 |
| `static/js/admin/.gitkeep` | admin 컨텍스트 |
| `static/js/auth/.gitkeep` | auth 컨텍스트 |
| `static/css/layout/.gitkeep` | SPEC `static/css/layout/` 축 |
| `static/css/components/.gitkeep` | SPEC `static/css/components/` 축 |

## 3. 자산 이동 (same-batch)

- **없음.** 기존 제품 JS/CSS는 이미 `runtime/`, `orders/`, `measurement/`, `shipment/`, `channel/`, `wdcalculator/` 등 아래에 있으며, §6.11 “다른 namespace에 있는 자산이 해당 context 소유”에 해당하는 **오배치 파일이 없음**으로 판정.

## 4. 계약 테스트

- `test_strict_canonical_static_materialized_nodes_sfc_b8`: 위 8노드 디렉터리 + `.gitkeep` 존재 고정.

## 5. SG3 참고

- **정적 트리 슬라이스:** B1에 나열된 `static/js/{drawing,…}` 및 `static/css/{layout,components}` 누락은 본 배치로 해소.
- **전체 `SG3`:** `foms/api/files` 패키지 등은 **`SFC-B9`** 범위로 남음.

## 6. 검증

| 검사 | 결과 |
|------|------|
| `python -c "import app; print('APP_OK')"` | `APP_OK` |
| `python tools/harness/verify_result.py --json` | `success: true` |
| `pytest tests` | **576 passed** |
