# WDCalculator Product Settings Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `wdcalculator/product-settings`에서 수정한 제품/추가옵션/비고 카테고리 설정이 Railway 재배포 후에도 유지되도록 영속 저장 구조를 바꾼다.

**Architecture:** 런타임 쓰기 대상인 `data/*.json`을 운영 소스오브트루스로 쓰지 않고, `wdcalculator` 전용 DB 스택 안에 JSONB 기반 싱글턴 설정 레코드를 둔다. 기존 JSON 파일은 신규 환경 부트스트랩용 시드로만 유지하고, `public.orders` 및 기존 주문 데이터는 절대 건드리지 않는다.

**Tech Stack:** Flask Blueprint, SQLAlchemy, PostgreSQL JSONB, Railway, Pytest

---

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
- 운영자가 `/wdcalculator/product-settings`에서 옵션을 수정하면 값이 DB에 저장된다.
- `git push` 및 Railway 재배포 후에도 옵션값이 유지된다.
- 기존 `public.orders` 및 주문 이력/첨부/이벤트 데이터는 변경되지 않는다.

### 1.2 기능 요구사항
1. 제품 목록은 `data/products.json` 대신 `wdcalculator` 전용 DB 설정 레코드에서 읽고 저장한다.
2. 추가 옵션 카테고리와 비고 카테고리도 동일한 방식으로 DB에 읽고 저장한다.
3. 설정 레코드가 비어 있으면 읽기 경로는 기존 JSON 파일 시드를 사용하고, 첫 저장 시 DB 레코드를 생성해 이후부터 DB를 소스 오브 트루스로 사용한다.
4. 기존 프런트엔드 API 계약(`/api/wdcalculator/products`, `/api/wdcalculator/additional-options/*`, `/api/wdcalculator/notes/*`)은 유지한다.
5. 저장 실패 시 기존처럼 `success: False` 응답을 반환하고 서버 세션은 rollback 된다.

### 1.3 예외/제약 조건
- `public.orders` 및 관련 메인 ERP 테이블에는 컬럼 추가/수정/삭제를 하지 않는다.
- `web_migration.py`의 reset 경로 같은 파괴적 로직은 사용하지 않는다.
- 운영 저장 경로로 로컬 JSON 파일 쓰기를 계속 유지하지 않는다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `wdcalculator_models.py` | WDCalculator 전용 설정 싱글턴 모델 추가 |
| `wdcalculator_db.py` | 새 모델이 `create_all` 대상에 포함되도록 보장 |
| `apps/api/wdcalculator.py` | 파일 I/O helper를 DB 저장소 helper로 교체, 시드/fallback 경로 정리 |
| `tests/test_wdcalculator_product_settings.py` | 설정 시드/저장/조회 회귀 테스트 추가 |

### 2.2 아키텍처 방향
- 기존 `Estimate`, `EstimateHistory`, `EstimateOrderMatch`와 같은 `wdcalculator` 전용 DB 경계를 유지한다.
- 신규 설정 모델은 JSONB 컬럼 3개를 가진 싱글턴 레코드로 두어 현재 JSON 구조와 최대한 동일하게 유지한다.
- API 레벨에서는 기존 응답 형식과 데이터 구조를 유지해 프런트엔드 변경을 최소화한다.

### 2.3 의존성 및 영향 범위
- 메인 영향 범위는 `wdcalculator` 제품 설정 화면과 WDCalculator 계산 API다.
- DB 마이그레이션 파일 대신 기존 `init_wdcalculator_db()`의 `create_all` 패턴을 따른다.
- 다중 Web Replica 환경에서 최초 시드 경쟁이 있을 수 있으므로 idempotent 초기화가 필요하다.

## 3. Steps — 실행 단계
- [ ] Step 1: WDCalculator 설정 싱글턴 모델 추가
- [ ] Step 2: JSON 파일 시드 + DB load/save helper 구현
- [ ] Step 3: 제품/추가옵션/비고 API를 DB helper로 연결
- [ ] Step 4: 재발 방지 테스트 추가
- [ ] Step 5: import/lint/pytest 검증
- [ ] Step 6: 감리 및 위험 재점검

## 4. 검증 기준
- [ ] `python -c "import app"` 통과
- [ ] `pytest tests/test_wdcalculator_product_settings.py -q` 통과
- [ ] `ReadLints`에서 수정 파일 기준 신규 오류 없음
- [ ] 설정 저장 후 재조회 시 DB 값이 반환됨
- [ ] 기존 주문 데이터 테이블(`public.orders`)를 수정하는 코드가 추가되지 않음

## 5. 참고 자료
- 관련 결정: `docs/context/DECISIONS.md`의 Railway/Web Replica 및 Flask 유지 결정
- 관련 아카이브: `docs/ARCHIVE_INDEX.md`
- 관련 코드: `apps/api/wdcalculator.py`, `wdcalculator_db.py`, `wdcalculator_models.py`
