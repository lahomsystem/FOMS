# erp_phone_digits 20자 절단 해소 — 실행 플랜 (B 등급)

작성 2026-09-02. 브리프: `docs/plans/2026-09-02-erp-phone-digits-truncation-brief.md`
(브랜치 `session/s0901-220206`, 커밋 aac06fba4 — deploy 에는 아직 없다).
원장: `docs/plans/2026-09-02-erp-phone-digits-widen-ledger.md`

## 문제 요약

`orders.erp_phone_digits` 가 `VARCHAR(20)`, `normalize_phone_digits` 도 20자에서 자른다.
전화번호를 둘 이상 적은 주문은 숫자열이 22~23자가 되어 **두 번째 번호의 뒷자리가 소실**되고,
그 번호로는 통합 검색이 걸리지 않는다. 운영 실측(2026-09-02): 정확히 20자 81건,
`phone` 숫자열 20자 초과 72건, 최대 23자.

## 선택한 해법 — 브리프 선택지 1 (폭 확대)

`VARCHAR(20)` → `VARCHAR(64)`, `_MAX_PHONE_DIGITS` 20 → 64, 절단된 행 재계산.

### 왜 구분자를 넣지 않는가 (선택지 1.5 기각)

번호 사이에 구분자(`,`)를 넣으면 번호 경계 오탐이 사라지지만, 미병합 브랜치
`session/naver-*` 의 소비자가 이 컬럼을 **정확 일치**로 쓴다
(`order_candidates.py:657` `Order.erp_phone_digits == digits`). 구분자는 그 계약을
조용히 깬다. 순수 숫자열 유지 = 기존 소비자 5곳 전부와 호환.

### 알고 넘어가는 한계

이어 붙인 숫자열이라 `contains` 검색이 **번호 경계를 모른다**. 예: `...0264` + `01058...`
가 이어지면 `640105` 같은 우연한 부분열이 걸릴 수 있다. 6자리 미만 질의에서 이론상
가능하나 실제 오탐 확률은 낮고, 정확도가 필요하면 브리프 선택지 2(번호 목록 정규화)를
별도 배치로 한다. 이번 범위 밖.

## 변경 지점

| 파일 | 변경 |
|---|---|
| `foms/services/phone_search.py:14` | `_MAX_PHONE_DIGITS` 20 → 64 |
| `models.py:108` | `String(20)` → `String(64)` |
| `foms/services/db_indexes.py:144,153` | ensure DDL `VARCHAR(20)` → `VARCHAR(64)` |
| `migrations/versions/<new>.py` | `ALTER COLUMN TYPE VARCHAR(64)` + 절단 행 재계산 + `downgrade()` |

과거 마이그레이션(`add_erp_phone_digits`, `startup_schema_00`)은 **수정하지 않는다**
(상수 동결 원칙). 새 DB 는 20자로 만들어진 뒤 새 마이그레이션이 넓힌다.

## 백필 경로 — 부팅이 알아서 풀지 않는다

`erp_phone_digits` 는 `DERIVED_COLUMNS`(`foms/services/orders/erp_flat_audit.py:61`)에
있지만, 그 백필(`erp_flat_backfill.run_backfill`)은 **부팅 자동 실행이 아니다** —
OPS approval(`BACKFILL_APPLY` seq>=1) + lease + CLI 가 필요한 수동 인프라다.
따라서 기존 81건은 스스로 풀리지 않는다. 새 마이그레이션이 직접 재계산한다.

재계산 술어(안전 범위 한정):

```sql
UPDATE orders
   SET erp_phone_digits = LEFT(NULLIF(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),''), 64)
 WHERE length(erp_phone_digits) = 20
   AND LEFT(NULLIF(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),''), 64) LIKE erp_phone_digits || '%'
```

`length=20` 이면서 **현재 값이 전체 숫자열의 접두사인 행만** 건드린다. 진짜 20자짜리는
재계산 값이 같아 무변화, 정본이 어긋난 행은 애초에 대상에서 빠진다(파생 재동기 범위 밖).
`phone` 컬럼을 소스로 쓰는 것은 선행 마이그레이션 `add_erp_phone_digits` 와 같은 계약이고,
사고 조사에서 `phone` 과 `structured_data` 가 서로 같음을 확인했다.

SQLite 는 `regexp_replace` 가 없으므로 파이썬 백필로 분기한다(선행 마이그레이션과 동형).

## Task 목록 (완료 기준 포함)

| # | Task | 완료 기준 |
|---|---|---|
| T1 | 격리 워크트리 + 플랜/원장 | `c:\tmp\foms-s-phonedigits` 에서 `pwd` 확인, 두 문서 존재 |
| T2 | 실패하는 계약 테스트 먼저 | 새 테스트가 수정 전 red (두 번째 번호 뒷4자리 미검출) |
| T3 | 코드 폭 확대 (normalizer·모델·ensure DDL) | T2 테스트 green, `APP_OK` |
| T4 | alembic 마이그레이션 + downgrade | 단일 head 유지, `upgrade`/`downgrade` 왕복 성공(PG) |
| T5 | PG 레인 검증 | `tests/postgres` green, 컬럼 폭 64 실측, 23자 저장 무절단 |
| T6 | 전체 게이트 | `pre_push_smoke` exit 0 |
| T7 | 커밋 + deploy push + CI | 자기 커밋만 push, 전 워크플로 green(`gh run list` 나열) |
| T8 | 스테이징 반영 확인 | 배포 후 `length(erp_phone_digits)=20 AND 절단` 행 0 |

## 범위 경계

* production 승격 안 함 (사용자가 따로 지시).
* 번호 목록 정규화(선택지 2) 안 함.
* 미병합 naver 브랜치 파일 안 건드림 (deploy 기준 트리에 없다).
