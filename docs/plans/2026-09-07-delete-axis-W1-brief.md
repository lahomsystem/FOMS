# W1 — 휴지통 낱말·술어 한 벌 (화면)

계약 원문: `docs/plans/2026-09-07-delete-axis-unify-brief.md`
작업 트리: `c:\tmp\foms-s-s0907-202822` — 모든 명령을 `cd /c/tmp/foms-s-s0907-202822 && pwd && ...` 로 시작.
git 명령 금지. CRLF 보존(대상 파일 전부 CRLF). 파일 전체 재작성 금지.

## CEO 확정 사항 (바꾸지 말 것)

1. **`read_order_trash` 는 `foms/services/orders/soft_delete.py` 로 이사한다.**
   근거: 이 함수가 읽는 두 자리(`deleted_at` 컬럼 + `structured_data['delete']`)를 **쓰는 코드**가
   `soft_delete._write_delete_projection`(soft_delete.py:60-90)이고 고정폭 형식 상수
   `_DELETED_AT_FORMAT`(soft_delete.py:48)도 거기 있다. 쓰는 자리와 읽는 자리를 한 파일에 두는 것이
   오늘 고치는 드리프트를 다시 안 만드는 유일한 배치다. `state_axes.py` 는 형식 없는 canonical 값
   SSOT 라 KST 표시 형식을 넣지 않는다. 새 디렉토리·새 모듈을 만들지 않는다(닫힌집합 계약).
   순환 없음 — `soft_delete` 는 이미 `state_axes.read_deleted` 와 `datetime_kst.now_utc_naive` 를
   물고 있고(soft_delete.py:30·36), 네이버 쪽을 하나도 import 하지 않는다.
2. **후보 표·검색 표의 `trashed_at` 표시는 `MM-DD HH:MM`(KST)로 바뀐다.**
   화면 낱말 변화: 후보 표와 검색 표의 주문 칸이 지금 `2026-09-07 17:41:23 삭제` 라고 적던 자리에
   `09-07 17:41 삭제` 라고 적는다 — pane 머리줄(`{{ order_trashed_at_text }} 삭제`)·유령 폐기 블록과
   **같은 문자열 벌**이 된다. 연도가 사라지는 것은 의도된 대가다(세 화면 한 벌 > 연도 표시).
3. **키 이름은 그대로다.** 행 payload 는 계속 `trashed` · `trashed_at` 이다. 그래서 **템플릿은
   손대지 않는다** — CSS 도 안 바꾸므로 `templates/admin/naver_workbench.html` 핀 범프도 없다.
   템플릿을 고쳐야 할 이유가 생기면 고치지 말고 보고에 적는다.
4. **판정 축은 한 글자도 바뀌지 않는다.** `read_deleted`(state_axes.py:260)는 지금 후보 표의 식
   (`deleted_at is not None or status == 'DELETED'`)과 **논리적으로 동치**다. 바뀌는 것은
   (a) 시각 형식, (b) `deleted_at` 컬럼이 비었을 때 `structured_data['delete']['deleted_at']` 로
   시각을 되찾는 갈래 — 둘 다 표시 축이다.

## 편집 허용 파일 (이 밖은 읽기만)

- `foms/services/orders/soft_delete.py`
- `foms/services/integrations/naver_commerce/ghost_orders.py`
- `foms/services/integrations/naver_commerce/order_candidates.py`
- `foms/web/admin/naver_ingest.py` — **import 1줄(2144행)과 그 바로 위 docstring 참조(2127행)만**
- `tests/services/integrations/test_naver_trash_wording_unified.py` (신규)

## 해야 할 변경 (앵커별)

### A. `soft_delete.py`
- `from typing import Optional` (25행) → `Any` 추가.
- `from foms.services.datetime_kst import now_utc_naive` (30행) → `format_datetime_kst` 추가.
- 표시 형식 상수를 `_DELETED_AT_FORMAT` (48행) 옆에 새로 둔다:
  `_TRASH_AT_DISPLAY_FORMAT = "%m-%d %H:%M"` — 세 화면이 같은 상수를 읽게 하는 것이 이 작업의 목적이다.
- `read_order_trash` 를 `ghost_orders.py:137-181` 에서 **본문 그대로** 옮겨 온다(이사다 — 로직 변경 금지).
  옮기면서 딱 두 가지만 손본다: 형식 리터럴 `"%m-%d %H:%M"` → 새 상수, docstring 의 "아직 한 벌은
  아니다" 문단(ghost_orders.py:147-152)을 **지금 사실**로 다시 쓴다(후보 표·검색 표·pane 머리줄이
  이 함수 하나를 쓴다 / 판정 축이 아니라 표기 전용이다 / 복원 주문 갈래를 왜 나누는가).
- `__all__` (259행)에 `"read_order_trash"` 추가.

### B. `ghost_orders.py`
- 137-181행의 함수 정의 삭제.
- 모듈 상단 import 에 `from foms.services.orders.soft_delete import read_order_trash` 추가.
- `__all__` (70행)에서 `"read_order_trash"` 제거 — **재수출하지 않는다**(이름이 두 자리에 남으면
  다음 사람이 다시 갈라 쓴다).
- 호출부 `:608` (`trash = read_order_trash(order)`) 은 그대로 둔다.
- `format_datetime_kst` 가 이 파일에서 더 쓰이지 않으면 import(57행 부근)도 함께 정리한다 — 쓰이면 둔다.

### C. `order_candidates.py`
- import 43행: `from foms.services.datetime_kst import format_datetime_kst, now_utc_naive`
  → **`format_datetime_kst` 는 이 변경 뒤 이 파일에서 안 쓰인다**(유일 사용처가 1047행). 제거해서
  `now_utc_naive` 만 남긴다(1122행에서 계속 쓴다).
- `from foms.services.orders.soft_delete import read_order_trash` 추가.
- `_order_view`(1011행~) 본문에서 `facts = facts or {}` 바로 뒤에 `trash = read_order_trash(order)` 를
  두고, 1046-1047행 두 줄을 다음으로 바꾼다:
  `"trashed": trash["trashed"],` / `"trashed_at": trash["trashed_at_text"],`
  주석은 남기되 "두 축을 함께 본다" 문장을 "판정·형식 모두 `read_order_trash` 한 벌을 쓴다"로 고친다.
- `trashed_note` 는 **싣지 않는다**(읽는 템플릿이 없다).
- 검색 표는 `_search_views`(1291행)가 같은 `_order_view` 를 쓰므로 자동으로 따라온다 — 따로 고치지 않는다.
- `views.sort(... row["trashed"] ...)`(1217행) 정렬 키는 그대로 둔다(값의 뜻이 안 바뀐다).

### D. `naver_ingest.py`
- 2144행 지역 import 를 `from foms.services.orders.soft_delete import read_order_trash` 로 바꾼다.
- 2127행 docstring 의 `:func:`ghost_orders.read_order_trash`` 참조를 새 경로로 고친다.
- **이 파일에서 그 외 어떤 줄도 건드리지 않는다.**

### E. 신규 테스트 `tests/services/integrations/test_naver_trash_wording_unified.py`
같은 주문 하나로 세 화면이 **문자 그대로 같은 문자열**을 내는지 고정한다.
1. 정본 projection 주문(`deleted_at='2026-09-07 08:41:00'` + `structured_data['delete']`) →
   후보 행 `trashed is True`, `trashed_at == read_order_trash(order)["trashed_at_text"]`,
   그리고 그 값이 `MM-DD HH:MM` 정규식(`^\d{2}-\d{2} \d{2}:\d{2}$`)에 맞는다. KST 환산(+9h)을
   숫자로도 못 박는다.
2. legacy 축(`status='DELETED'`, `deleted_at=None`, `structured_data['delete']['deleted_at']` 있음) →
   후보 행 `trashed is True` 이고 `trashed_at` 이 **빈 문자열이 아니다**(옛 식은 여기서 빈칸이었다).
3. 음성 대조군 — 복원된 주문(`deleted_at=None`, `status='RECEIVED'`, `structured_data['delete']` 잔존) →
   `trashed is False`, `trashed_at == ""`.
4. 위치 계약(심볼 이사 고정): `from foms.services.orders.soft_delete import read_order_trash` 가
   되고, `ghost_orders.__all__` 에 `"read_order_trash"` 가 **없다**.
5. 검색 표(`_search_views` 경유 또는 `search_orders_for_attach`)도 같은 문자열을 낸다.
DB 픽스처는 같은 레인의 기존 테스트(`tests/services/integrations/test_naver_ghost_trash_trace.py`)
방식을 그대로 따른다. 문서를 읽는 테스트를 만들지 않는다.

## 하지 말 것
- `can_discard` · 유령 모집단 · `RELATION_BY_CLAIM_PAIR` · `recommended_relation` · `run_gate` 손대기.
- `trashed`/`trashed_at` 키 이름 변경, `trashed_note` 추가, 템플릿·CSS·핀 상수 변경.
- `ghost_orders` 에 `read_order_trash` 재수출 남기기.
- `naver_ingest.py` 의 import 1줄 + docstring 1줄 밖의 편집.
- 기존 테스트 기대값 수정 — 깨지면 고치지 말고 보고한다(특히
  `tests/services/integrations/test_naver_ghost_trash_trace.py:157` 의 `"09-07 08:41"`).

## 완료 기준 (돌릴 명령)
```
cd /c/tmp/foms-s-s0907-202822 && pwd
python -m pytest tests/services/integrations -q
python -m pytest tests/domains/test_soft_delete_core.py tests/domains/test_delete_trash.py tests/domains/test_delete_bulk.py tests/domains/test_foms_namespace_imports.py -q
python -c "import app; print('APP_OK')"
```
보고에 반드시 적을 것: 옮긴 함수의 새 경로, 따라 고친 import 목록, 화면 문자열이 어떻게 바뀌는지
한 문장, 템플릿을 안 고쳤다는 확인.
