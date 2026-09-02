# erp_phone_digits 20자 절단 — 다음 세션 작업 브리프

작성 2026-09-02. 앞선 사고 조사의 부산물(`docs/incidents/2026-09-01-naver-triage-auto-match-miss.md` 부록 A 갈래 A).

## 문제

`orders.erp_phone_digits` 는 `VARCHAR(20)` 이고 `normalize_phone_digits` 가 20자에서 자른다
(`foms/services/phone_search.py:32-34`, `models.py:108`). 전화번호를 여러 개 적은 주문은
숫자열이 22~23자가 되어 **두 번째 번호의 뒷자리가 잘린다.**

```
#4907 phone='010-8935-0264(고객), 010-5875-1125(팀장)'
      erp_phone_digits='01089350264010587511'   ← 마지막 2자리 소실
```

증상: 두 번째 번호(팀장·세입자·실측 담당)로 **통합 검색이 안 걸린다.** 화면에는 원문이
보이므로 담당자는 "검색이 왜 안 되지"로만 겪는다. 첫 번째 번호 검색은 정상이다.

## 운영 실측 (2026-09-02, 읽기 전용)

| 항목 | 수 |
|---|---|
| `erp_phone_digits` 가 정확히 20자(절단 의심) | 81 |
| `phone` 숫자열이 20자를 넘는 활성 주문 | 72 |
| 최대 숫자열 길이 | 23 |

이 갈래는 **정본/플랫 어긋남이 아니다** — `phone` 컬럼과 `structured_data` 는 서로 같다.
어긋난 것은 파생 검색 컬럼 하나뿐이다.

## 선택지

1. **컬럼 폭을 넓힌다** (`VARCHAR(20)` → `VARCHAR(64)`) + `_MAX_PHONE_DIGITS` 상향 + 백필.
   - 가장 단순. 인덱스는 btree 라 폭이 늘어도 동작한다.
   - 다만 "번호 여러 개를 한 문자열로 이어 붙인 값"이라는 모양은 그대로다 —
     `contains` 검색은 되지만 **번호 경계를 모른다**(끝 4자리 검색이 두 번호에 걸친
     우연한 부분열을 잡을 수 있다).
2. **번호 목록으로 정규화한다** — 별도 테이블이나 배열 컬럼에 번호 하나씩.
   - 검색 정확도가 제일 좋다. 대신 마이그레이션·검색 술어·인덱스가 모두 바뀐다.
3. **첫 번호만 담고 나머지는 버린다** — 지금보다 나쁘다(두 번째 번호 검색이 아예 죽는다).

권고: **1번으로 시작**하되, 경계 문제를 알고 넘어간다. 2번은 별도 배치.

## 착수 전 확인 사항

* 마이그레이션은 `alembic` 단일 head 유지 + `downgrade()` 필수. 과거 마이그레이션이
  `models` 를 live import 하지 않게 한다(상수 동결 원칙).
* `erp_phone_digits` 는 `DERIVED_COLUMNS`(`foms/services/orders/erp_flat_audit.py`)에
  **이미 있다** — 백필이 이 컬럼을 자동으로 다시 계산한다. 폭을 넓힌 뒤 부팅 백필이
  돌면 절단분이 스스로 풀릴 가능성이 있으니, 백필 경로를 먼저 읽어라.
* 검색 소비자: `foms/services/erp_dashboard_search.py:44-49`,
  `foms/services/foms_unified_search.py:265-272`, `foms/api/cs/dashboard.py:95`,
  `foms/services/integrations/naver_commerce/order_candidates.py:644`,
  `bulk_dispatch.py:614`.
* PG 레인에서 확인할 것 — SQLite 는 길이 제약을 강제하지 않아 로컬만으로는 절단이 재현되지 않는다.

## 완료 기준

1. 다전화 주문의 **두 번째 번호 뒷자리 4자리**로 통합 검색이 걸린다(계약 테스트).
2. 운영 기준 `length(erp_phone_digits)=20` 인 행이 백필 뒤 0으로 떨어진다(또는 진짜 20자만 남는다).
3. `pre_push_smoke` exit 0 + PG 레인 green.
