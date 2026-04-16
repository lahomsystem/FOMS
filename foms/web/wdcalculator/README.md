# WDCalculator (canonical web slice — FR20)

## 목적

WD 견적 계산기 **페이지**·템플릿 진입점의 canonical web owner를 둔다. 대형 static JS는 `static/js/wdcalculator/` 와 chunk 계약을 따른다.

## 주요 모듈

본 디렉터리의 Blueprint·페이지 조립. persistence는 루트 `wdcalculator_db.py` / `foms/persistence/wdcalculator` 계약을 따른다.

## 읽기 순서

1. `foms/platform/blueprints.py`
2. 본 디렉터리
3. `foms/api/` 내 wdcalculator 관련 surface
4. `static/js/wdcalculator/` — JS 런타임 파일 (로드 순서·chunk 맵은 `docs/context/wdcalculator-static-js-chunk-map.md` 참고)

## 금지 의존성

- quarantine/non-product 트리 import 금지.
- thin wrapper-only 미세 분해 증식 금지 (`2026-04-13` §1.2.9).
