# W3 — 계약 테스트 2벌 (테스트 파일 소유)

작업 트리: `c:\tmp\foms-s-s0908-102606` (브랜치 `session/s0908-102606`).
bash cwd 는 호출 사이에 리셋된다 — 모든 명령을 `cd /c/tmp/foms-s-s0908-102606 && pwd && ...` 로 시작한다.

**먼저 읽어라**: `docs/plans/2026-09-08-naver-dock-autofill-contract.md` 전문.
값·문구·이름은 그 문서가 정본이다. 네 테스트가 그 계약을 못박는다.

## 네가 만지는 파일

신규 2개:

- `tests/services/integrations/test_naver_dock_autofill_map.py` (서버 매핑)
- `tests/services/integrations/test_naver_dock_autofill_wire.py` (화면 배선)

기존 수정 — **핀 assert 6줄만**:

- `tests/services/integrations/test_naver_dock.py:790·791·972·973`
- `tests/services/integrations/test_naver_dock_household_split.py:317·318`

`dock.py`(W1)·도크 JS/CSS/템플릿(W2)은 **읽기만** 해라.

## 전제 (네 테스트는 W1·W2 가 끝나기 전엔 빨갛다 — 정상이다)

계약이 이미 확정돼 있으니 병렬로 쓴다. 마지막에 셋을 합쳐 초록을 확인하는 것은 총괄이 한다.

## 규율 — "소스 문자열만 훑는 테스트"를 만들지 마라

브리프 경계다. 대신 **실제로 실행**해라. 두 수단이 이미 저장소에 있다:

1. **서버**: `build_dock_payload` 를 실제로 불러 payload 를 만든다.
   재료는 `tests/services/integrations/test_naver_dock.py` 의 `_staff`·`_naver_order`·`_link`·`_snapshot` 를
   import 해서 쓴다(선례: `test_naver_dock_width_live.py:38-43`).
2. **화면**: 도크 JS 에서 함수를 통째로 뜯어 **Node 에 태워 실행**한다.
   선례이자 그대로 재사용할 도구: `tests/services/integrations/test_naver_dock_width_live.py`
   - `_extract_function(source, name)` (`:59-80`) — 중괄호 균형으로 함수 원문을 뜯는다. **import 해서 쓰고 베끼지 마라.**
   - `_needs_node = pytest.mark.skipif(not shutil.which("node"), ...)` (`:47`) — 같은 방식으로 건너뛴다.
   - `subprocess` 로 `node` 실행 + `json.dumps`/`json.loads` 로 값 주고받기 (`:100-` 참고).

배선 못박기용 소스 문자열 assert 는 **두세 줄까지만** 허용한다(핀·이벤트 이름 같은 것). 선례가
`test_naver_dock_width_live.py` 머리말에 이미 적혀 있다: "계산 규칙은 Node 에 태워 실행하고, 화면 배선은
소스 문자열로 못박는다".

## 파일 1 — `test_naver_dock_autofill_map.py` (서버)

모듈 docstring에 **왜 이 파일이 있는지**를 적어라: 담당자가 2026-09-08 에 "자동 기입 금지" 결정을 4칸에
한해 뒤집었고, 그 4칸의 정본이 `COPY_TARGET_BY_KEY` 라는 것.

물어야 할 것:

1. **운영 옵션 원문 → 칩+target** (`option_copy_chips` 직접 호출)
   - `'제품: 로라 무몰딩 여닫이 30cm / 컬러: 클린 화이트 / 손잡이: 푸쉬타입'`
     → `[('로라 무몰딩 여닫이','product_name'), ('클린 화이트','color'), ('푸쉬타입','handle')]`
   - `'제품: 보테가 슬라이딩 30cm （풀오토댐퍼 포함） / 컬러: 포그 그레이'`
     → `[('보테가 슬라이딩','product_name'), ('포그 그레이','color')]`
2. **전각 짝** (계약 §3) — 운영 실사례 2026-09-01 주문 `2026090191203001`
   - `'사이즈 ／ 색상: 180cm ／ 클린 화이트 / 손잡이: 푸쉬타입'`
     → `[('180cm',''), ('클린 화이트','color'), ('푸쉬타입','handle')]`
   - 짝이 안 맞으면 오늘 그대로: `'색상 ／ 사이즈: 클린 화이트'` → `[('클린 화이트','')]`
3. **사이즈는 일부러 target 이 없다** (계약 §2 근거를 docstring 에 적어라 —
   `150` 은 모듈 폭이고 총폭은 `모듈 × 수량 + 길이추가` 라 30cm×12 + 1cm×12 = 3,720mm)
   - `'사이즈: 150（무몰딩）'` → `[('150（무몰딩）','')]`
   - `'서랍: 1단(소)'` · `'수납구성: TYPE A'` 도 `''`
4. **서버는 `spec_width` 를 절대 안 내보낸다**: `set(COPY_TARGET_BY_KEY.values())` 에 `'spec_width'` 없음.
5. **`copies` 무회귀**: `split_option_copies('사이즈: 150（무몰딩）/ 색상: 클린 화이트 / 피닉스바')`
   `== ['150（무몰딩）', '클린 화이트', '피닉스바']`, 그리고 임의 원문에 대해
   `[c['value'] for c in option_copy_chips(t)] == split_option_copies(t)` (같은 파서에서 나온다는 계약).
6. **실제 payload 가 실어 나른다** — `build_dock_payload` 를 불러 만든 본품 행에
   `copy_chips` 가 `copies` 와 **같은 길이·같은 value 순서**로 들어 있고 target 이 맞는지.
   추가옵션 행은 `copy_chips == [{'value': 이름칩, 'target': ''}]` 인지.
   `copies` 가 **여전히 문자열 목록**인지도 여기서 못박아라(옛 JS 안전장치가 계약이다).

## 파일 2 — `test_naver_dock_autofill_wire.py` (화면, Node 실행)

모듈 docstring에 왜 Node 로 도는지 적어라(도크 JS 는 IIFE 라 통째로는 안 돌고, 순수 함수만 뜯어 태운다).

Node 하네스 프리앰블(테스트가 만들어 넣는다):

```js
function Event(type, opts) { this.type = type; this.bubbles = !!(opts && opts.bubbles); }
```

그리고 스텁 객체로 DOM 을 흉내 낸다 — 진짜 브라우저가 아니어도 **판단과 이벤트 발사는 진짜로 실행된다**.

물어야 할 것:

1. **빈 칸 판정** `dockIsBlankValue`: `''`·`'   '`·`'상담'` → `true`; `'포그 그레이'`·`'상 담'` → `false`.
   docstring 에 근거를 적어라: 신규 항목의 색상·손잡이 기본값이 `'상담'` 이다
   (`erp-order-shared.js:1370-1372`). 이걸 빈 값으로 안 세면 확인창이 항상 뜬다.
2. **항목 고르기** `dockPickItemRow` — 계약 §4.1 네 갈래를 전부:
   - 마지막으로 만진 항목이 우선
   - 그 항목이 목록에서 사라졌으면(제거됨) 다음 규칙으로 떨어진다
   - 마스터-디테일: `erp-item-row--md-hidden` 이 붙은 행은 안 고른다
   - 모바일: `is-open` 이 붙은 행 우선
   - 항목 0개면 `null`
3. **칸 찾기** `dockFieldFor`: `spec_width` 는 `.erp-spec-row [data-erp="spec_width"][data-spec-row]`,
   나머지는 `[data-erp="<target>"]`. 셀렉터 문자열을 스텁이 그대로 받아 확인하게 만들면 된다.
4. **확인창 문구** `dockFillConfirmText` — 계약 §4.3 의 두 예시 블록을 **글자 그대로** 대조한다.
   (덮어쓰기 / 규격 여러 행 + 빈 값)
5. **이벤트 발사** `dockApplyValue`: 값이 들어가고, 발사된 이벤트가 정확히
   `['input', 'change']` 순서이며 **둘 다 `bubbles === true`** 인지.
   docstring 근거: 자동저장이 `#erp-order` 에서 캡처로 듣는다(`erp-order-autosave.js:416-417`).
6. **판단 전체** `dockFillFromChip` — 인자로 받은 가짜 `confirmFn` 으로 네 갈래를 다 태운다:
   - 빈 칸 + 규격 1행 → 확인창 **안 부르고** 넣는다, `{ok:true, itemLabel, fieldLabel}`
   - 값 있음 → 확인창 1회, 승인하면 넣고 거부하면 값이 그대로 + `{ok:false, reason:'넣지 않았습니다'}`
   - 규격 행 2개 + 빈 칸 → 확인창을 부르고, 문구에 `'규격 행이 2개입니다 — 1행에 넣습니다.'` 가 들어간다
   - 항목 없음 → `{ok:false, reason:'넣을 항목이 없습니다'}`
   - `target` 이 `''` → 확인창도 안 부르고 `{ok:false}` (오늘의 복사 전용 경로)
7. **옛 응답 호환** `dockChipsOf`: `{copies: ['화이트']}` → `[{value:'화이트', target:''}]`;
   `copy_chips` 가 있으면 그것을 쓴다.
8. **배선 못박기(문자열 assert, 여기서만 최대 3줄)**
   - 클릭 위임이 target 을 읽어 `dockFillFromChip` 에 넘긴다:
     `"dockFillFromChip(copy.getAttribute('data-naver-dock-target') || '',"` 가 소스에 있다
   - 총폭 칩이 `spec_width` target 을 단다:
     `"data-naver-dock-target', 'spec_width'"` 가 소스에 있다
   - **예약금 칩에는 target 이 없다** — `buildDepositCard` 함수 원문(`_extract_function` 으로 뜯어서)에
     `'data-naver-dock-target'` 이 **없음**을 확인한다. 돈은 사람이 넣는다는 결정을 이 줄이 지킨다.

## 기존 테스트 수정 (핀 6줄만)

계약 §6 의 새 값으로 바꾼다:

- `?v=20260907b` → `?v=20260908a` (JS)
- `?v=20260902a` → `?v=20260908a` (CSS)

자리: `test_naver_dock.py:790·791·972·973`, `test_naver_dock_household_split.py:317·318`.
그 테스트들의 docstring·다른 assert 는 건드리지 마라.

## 하지 말 것

- `dock.py`·도크 JS/CSS/템플릿 수정. 빨간 것이 있으면 **고치지 말고 보고**해라(W1·W2 몫이다).
- 문서를 읽는 테스트 신설(`docs/**` 를 `read_text` 하는 테스트).
- 소스 문자열만 훑는 테스트 파일(§ "규율" 참고 — 문자열 assert 는 파일 2에서 최대 3줄).
- `_extract_function`·`_needs_node` 를 복사해 두 벌 만들기. import 해서 써라.
- 운영 DB 접속, git 명령(읽기 전용 제외).

## 규율

- docstring 필수(**왜 이 계약이 있는지**·무엇이 깨지면 무슨 일이 나는지), 타입 힌트 필수, bare except 금지.
- 파일당 500줄 이하(파일 크기 래칫은 신규 대형 파일을 red 로 만든다 — `tests/harness/test_file_size_ratchet.py`).
- CRLF 보존. 한글 주석.

## 완료 기준 (직접 돌려서 확인하고 보고해라)

```
cd /c/tmp/foms-s-s0908-102606 && pwd
python -m pytest tests/services/integrations/test_naver_dock_autofill_map.py tests/services/integrations/test_naver_dock_autofill_wire.py -q
python -m pytest tests/services/integrations -q
python -m pytest tests/domains -q
python -c "import app; print('APP_OK')"
node --version
```

`node` 가 없으면 화면 테스트는 skip 된다 — 그때는 **skip 이 몇 건인지** 보고에 적어라(초록으로 오해 금지).

## 보고에 반드시 넣을 것

- 위 명령들의 출력 원문(통과·실패·skip 건수 포함).
- **깨진 기존 테스트 전량**(파일:테스트명). W1·W2 미착지로 빨간 것과, 그 밖의 것을 갈라서 적어라.
- 핀 6줄을 실제로 고친 자리(파일:행).
