# 삭제 축 통일 — 낱말 한 벌 + 저장 규약 (2026-09-07)

작업 트리: `c:\tmp\foms-s-s0907-202822` (브랜치 `session/s0907-202822`, base `origin/deploy` = `1443af4a6`).
bash cwd 는 호출 사이에 메인 트리로 리셋된다 — 모든 명령을 `cd /c/tmp/foms-s-s0907-202822 && pwd && ...` 로 시작한다.

## 왜 하는가

오늘 휴지통 표기를 넣으면서 같은 사실을 세 곳이 서로 다르게 말한다는 것이 드러났다.

### 문제 1 — 휴지통 낱말·술어가 두 벌이다
- `foms/services/integrations/naver_commerce/ghost_orders.py` 의 `read_order_trash` 는
  `state_axes.read_deleted` 로 판정하고 시각을 `MM-DD HH:MM`(KST)로 낸다.
- `foms/services/integrations/naver_commerce/order_candidates.py:1046-1047` 은 제 식
  (`bool(order.deleted_at is not None or order.status == "DELETED")`)으로 따로 세고,
  시각은 `format_datetime_kst(order.deleted_at)` 기본 형식(`YYYY-MM-DD HH:MM:SS`)이다.
- 그래서 같은 주문의 같은 사실이 머리줄과 후보 표에서 **다른 문자열**로 뜬다.

### 문제 2 — 삭제 시각 저장 규약이 세 갈래다
정본은 `foms/services/orders/soft_delete.py` — naive UTC 고정폭 `%Y-%m-%d %H:%M:%S`.
읽는 쪽(`format_datetime_kst(..., assume_utc_if_naive=True)`)이 그 규약을 전제한다. 그런데:

| 자리 | 지금 쓰는 값 | 결과 |
| --- | --- | --- |
| `foms/web/orders/listing.py:584` (일괄 삭제) | `now_kst().strftime('%Y-%m-%d %H:%M:%S')` | KST 를 UTC 로 읽어 **9시간 앞선 시각**이 화면에 뜬다 |
| `foms/api/erp_orders_structured.py:2378` (드래프트 폐기) | `datetime.datetime.now().isoformat()` | 형식도 다르고(`T` 포함) 컨테이너 로컬 시각이다 |
| `soft_delete.py` (정본) | `now_utc_naive().strftime(...)` | 규약대로 |

운영 실측(2026-09-07 읽기전용 조회): 휴지통 행 308건 중
**246건이 legacy 일괄 삭제 표식**(`status='DELETED'` + `original_status` 있음 + `structured_data['delete']` 없음),
**28건이 ISO `T` 형식**(드래프트 폐기), 45건이 정본 projection 이다.

## 무엇을 하는가

### W1 — 낱말·술어 한 벌 (화면)
`order_candidates.py` 의 후보 행이 `ghost_orders.read_order_trash` 를 쓰게 한다.
키 이름(`trashed`·`trashed_at`)은 템플릿이 이미 쓰고 있으므로 **바꾸지 않는다**.
값만 한 벌이 된다 — 판정은 `read_deleted`(legacy `status='DELETED'` 축 포함), 시각은 `MM-DD HH:MM`(KST).
`read_order_trash` 를 어느 모듈에 둘지는 CEO 가 정한다(지금 자리는 네이버 전용 모듈이라
후보 표·검색 표까지 쓰기에는 결이 안 맞을 수 있다 — 옮기면 기존 import 를 전부 따라 고친다).
관련 템플릿: `templates/admin/partials/naver_workbench_pane.html:1031·1134`,
`templates/admin/partials/naver_workbench_seek.html:47`.

### W2 — 저장 규약 한 벌 (쓰기)
위 표의 두 자리를 정본과 같은 값으로 바꾼다: `now_utc_naive().strftime('%Y-%m-%d %H:%M:%S')`.
읽는 쪽에서 보정하지 않는다 — 보정을 넣으면 규약이 네 갈래가 된다.
`listing.py` 의 legacy `status='DELETED'` 쓰기 자체는 **이번 범위가 아니다**(별건).
`deleted_at` 에 값을 쓰는 자리가 더 있는지 `grep -rn "deleted_at\s*=" --include=*.py` 로 전수 확인하고
빠진 자리가 있으면 함께 고친다(보고에 목록을 적는다).

### W3 — 백필 도구 (실행하지 않는다)
`tools/ops/backfill_deleted_at_utc.py` 신설. **기본 dry-run**, `--apply` 가 있어야 쓴다.
표식으로만 고른다:
- ISO `T` 포함 행 → 형식 정규화(+ 필요하면 시각 보정. 컨테이너 TZ 를 **확인한 뒤** 결정하고,
  확인 못 하면 형식만 고치고 시각은 건드리지 않는다 — 모르는 값을 옮기지 않는다).
- `status='DELETED'` + `original_status IS NOT NULL` + `structured_data['delete']` 없음 → KST 로 적힌 행.
  `-9시간` 보정.
경계·함정: **되돌릴 수 있어야 한다**(변경 전 값을 파일로 남긴다). 두 번 돌려도 같은 결과여야 한다(멱등).
이 세션에서는 운영 DB 에 절대 쓰지 않는다 — 사용자 승인 뒤 별도로 돌린다.
테스트는 SQLite 로 표식별 선별·보정·멱등을 검증한다.

## 파일 소유권

| 워커 | 편집 허용 |
| --- | --- |
| W1 | `foms/services/integrations/naver_commerce/order_candidates.py`, `ghost_orders.py`(옮길 때만), 위 템플릿 2개, `tests/services/integrations/test_naver_trash_wording_unified.py`(신규) |
| W2 | `foms/web/orders/listing.py`, `foms/api/erp_orders_structured.py`, `tests/domains/test_deleted_at_write_convention.py`(신규) |
| W3 | `tools/ops/backfill_deleted_at_utc.py`(신규), `tests/domains/test_backfill_deleted_at_utc.py`(신규) |

git 명령 금지. CRLF 보존. 판정 축(`can_discard`·유령 모집단·`RELATION_BY_CLAIM_PAIR`·`run_gate`)은 불변.
CSS 를 바꾸면 `templates/admin/naver_workbench.html` 의 핀 2줄을 `?v=20260907d` 로 **함께** 올리고
핀 상수를 세는 계약 테스트 5개도 같이 고친다(오늘 그것 때문에 CI 가 빨갛게 됐다).

## 검증 (완료 기준)

```
cd /c/tmp/foms-s-s0907-202822 && pwd
python -m pytest tests/services/integrations -q
python -m pytest tests/domains -q
python -c "import app; print('APP_OK')"
```
