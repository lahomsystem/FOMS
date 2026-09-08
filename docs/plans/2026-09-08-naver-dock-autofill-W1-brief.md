# W1 — 서버 매핑 (`dock.py` 단독 소유)

작업 트리: `c:\tmp\foms-s-s0908-102606` (브랜치 `session/s0908-102606`).
bash cwd 는 호출 사이에 리셋된다 — 모든 명령을 `cd /c/tmp/foms-s-s0908-102606 && pwd && ...` 로 시작한다.

**먼저 읽어라**: `docs/plans/2026-09-08-naver-dock-autofill-contract.md` §1·§2·§3·§5.
이름·모양은 그 문서가 정본이다. 한 글자도 바꾸지 마라.

## 네가 만지는 파일 (이것 하나뿐)

`foms/services/integrations/naver_commerce/dock.py`

W2 가 JS·CSS·템플릿을, W3 가 테스트를 맡는다. **그 파일들은 읽기만** 해라.

## 앵커 (지금 코드 위치)

| 자리 | 무엇 |
| --- | --- |
| `dock.py:1-14` | 모듈 docstring — "값 전달은 사람이 복사 버튼으로만 한다" |
| `dock.py:43` | `PRODUCT_NAME_KEYS = frozenset({"제품", "제품명", "상품", "상품명", "품목"})` |
| `dock.py:77-106` | `split_option_copies` — 지금 `list[str]` 을 낸다 |
| `dock.py:84` | docstring 안의 `자동 기입 금지 — 스펙 확정 결정 3` |
| `dock.py:120` | `SIZE_OPTION_KEYS` — 오타·영문 변형을 함께 담는 선례 |
| `dock.py:127-131` | `_PAIR_SEPARATOR = "／"` (전각) 와 그 이유 주석 |
| `dock.py:175-206` | `size_option_mm` — 전각 짝을 **자리로** 맞추는 정본 규칙 |
| `dock.py:259-264` | `build_width_hint` docstring "자동 기입은 하지 않는다(규격 SSOT 보호)" |
| `dock.py:977-980` | 행 조립 — `"copies": (split_option_copies(...) if not is_addon else ([name_chip] if name_chip else []))` |
| `dock.py:1108-1116` | `__all__` |

## 해야 할 변경

### 1. 매핑 상수 `COPY_TARGET_BY_KEY` 를 `PRODUCT_NAME_KEYS` 바로 아래에 둔다

계약 §2 의 내용 그대로. `PRODUCT_NAME_KEYS` 를 dict comprehension 으로 펼쳐 만들어라 —
두 벌로 적으면 나중에 갈린다. 주석에 **왜 `사이즈`·`규격`·`폭` 이 빠졌는지**(모듈 폭 ≠ 총폭,
30cm×12 + 1cm×12 = 3,720mm) 한 줄로 적어라.

### 2. `option_copy_chips(option_text: str) -> list[dict[str, str]]` 신설

- 지금 `split_option_copies` 의 파싱을 이쪽으로 옮긴다.
- 각 `/` 그룹에서 `:` 가 있으면 키/값을 가르고, **양쪽을 `_PAIR_SEPARATOR` 로 또 자른다.**
  - 키 조각 수 == 값 조각 수 → 자리로 짝지어 **조각마다 칩 1개**.
  - 수가 다르면 오늘 그대로 칩 1개(값은 값 부분 통째, target 은 `""`).
- 키가 `PRODUCT_NAME_KEYS` 에 있으면 지금처럼 `main_product_name` 으로 다듬는다(자리별로).
- target 은 `COPY_TARGET_BY_KEY.get(key.strip().lower(), "")`.
- `:` 가 없는 조각은 값 통째, target `""`.
- 빈 값은 버린다(지금과 같다).
- 반환은 `[{"value": ..., "target": ...}, ...]`.
- 함수 50줄 이하. 넘으면 `_pair_chips(key_part, value_part)` 같은 도우미로 쪼개라.

### 3. `split_option_copies` 는 **이름·시그니처 그대로** 남긴다

```python
return [chip["value"] for chip in option_copy_chips(option_text)]
```

파서를 두 벌로 만들지 마라. docstring 에 "칩 값만 필요한 옛 호출자를 위한 얇은 껍데기" 라고 적어라.

### 4. 행 조립(`dock.py:977` 부근)에 `copy_chips` 를 덧붙인다

```python
"copies": (...),        # 지금 줄 그대로 둔다
"copy_chips": (option_copy_chips(source["option_text"])
               if not is_addon
               else ([{"value": name_chip, "target": ""}] if name_chip else [])),
```

`copies` 를 **바꾸지 마라.** 이유는 계약 §1 — SW `staticCacheFirst` 때문에 옛 JS 가 새 payload 를
받는 창이 반드시 생기고, 그때 `copies` 가 dict 목록이면 칩이 전부 `📋 [object Object]` 로 뜬다.

### 5. `__all__` 에 `COPY_TARGET_BY_KEY` · `option_copy_chips` 추가

`__all__` 변경은 `tests/domains/test_foms_namespace_imports.py` 가 판정한다 — 완료 기준에 그 명령이 있다.

### 6. "자동 기입 금지" 문장 정정 (계약 §5)

- 모듈 docstring(`:3-6`), `split_option_copies` docstring(`:84`), `build_width_hint` docstring(`:264`).
- 금지가 남아 있으면 다음 사람이 이 기능을 버그로 읽고 되돌린다.
- 정정 문장에는 **범위**를 적어라: 넣는 칸은 제품명·색상·손잡이·총폭 4개뿐, 돈(예약금)·발송기한은 여전히 복사만.
- 결정을 누가·언제 뒤집었는지도 적어라: 담당자 요구 2026-09-08.

## 하지 말 것

- `copies` 의 타입·값·순서 변경. 기존 테스트 9곳이 문자열을 물고 있다.
- `size_option_mm` · `build_width_hint` · `_row_width_facts` 의 **계산 로직** 손대기. docstring 문장만 고친다.
- DOM·화면 이름(`data-erp`, `.erp-item-row`)을 서버로 끌어오기. 서버는 `target` 낱말까지만 안다.
- 서버에서 `spec_width` target 내보내기. 총폭 칩은 화면이 만든다.
- 새 파일 만들기, 다른 모듈 수정, git 명령(읽기 전용 제외), 운영 DB 접속.

## 규율

- 함수 50줄 이하 · docstring 필수(목적·Args·Returns) · 타입 힌트 필수 · bare except 금지.
- 주석은 한글로, **왜**를 적는다. CRLF 보존. 파일 전체 재작성 금지(부분 편집만).

## 완료 기준 (직접 돌려서 통과를 확인하고 보고해라)

```
cd /c/tmp/foms-s-s0908-102606 && pwd
python -m pytest tests/services/integrations/test_naver_dock.py tests/services/integrations/test_naver_dock_household_split.py tests/services/integrations/test_naver_dock_width_live.py -q
python -m pytest tests/domains/test_foms_namespace_imports.py -q
python -c "import app; print('APP_OK')"
```

빠른 자기 확인(위 명령과 별도, 결과를 보고에 붙여라):

```
cd /c/tmp/foms-s-s0908-102606 && pwd && python -c "
from foms.services.integrations.naver_commerce.dock import option_copy_chips, split_option_copies
print(option_copy_chips('제품: 로라 무몰딩 여닫이 30cm / 컬러: 클린 화이트 / 손잡이: 푸쉬타입'))
print(option_copy_chips('사이즈 ／ 색상: 180cm ／ 클린 화이트 / 손잡이: 푸쉬타입'))
print(option_copy_chips('색상 ／ 사이즈: 클린 화이트'))
print(split_option_copies('사이즈: 150（무몰딩）/ 색상: 클린 화이트 / 피닉스바'))
"
```

기대값:

1. `[{'value':'로라 무몰딩 여닫이','target':'product_name'}, {'value':'클린 화이트','target':'color'}, {'value':'푸쉬타입','target':'handle'}]`
2. `[{'value':'180cm','target':''}, {'value':'클린 화이트','target':'color'}, {'value':'푸쉬타입','target':'handle'}]`
3. `[{'value':'클린 화이트','target':''}]` (짝이 안 맞으면 오늘 그대로)
4. `['150（무몰딩）', '클린 화이트', '피닉스바']` (**회귀 없음**)

## 보고에 반드시 넣을 것

- 위 4개 기대값과 실제 출력의 대조.
- 기존 테스트 중 깨진 것이 있으면 파일:테스트명 전량(없으면 "없음"이라고 명시).
- 고친 docstring 3곳의 새 문장 원문.
