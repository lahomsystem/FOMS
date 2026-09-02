# 지오코딩 일시오류/주소오류 분리 — 실행 플랜 + 진행 원장 (2026-09-01, **B)

조사 원장(근거·실측): `docs/plans/2026-09-01-geocode-transient-vs-data-error-ledger.md`
작업 worktree: `c:/tmp/foms-s-geo0901` · 브랜치 `session/geo0901` (base `origin/deploy` 33b556c9c)

---

## 설계 결정 (착수 전 확정)

### D1. 실패를 상태값으로 가른다 (마이그레이션 없음)

`orders.geocode_status` 는 VARCHAR(50), enum 제약 없음. 값 3개(`success`/`pending`/`failed`)에
**`address_error` 를 추가**해 4상태로 만든다.

| 상태 | 뜻 | 자동 재시도 |
|---|---|---|
| `success` | 좌표 있음 | — |
| `pending` | 큐에 있음 **또는 일시 오류로 중단됨** | 600초 백오프(기존 스윕 술어 그대로) |
| `failed` | 사유 불명(레거시 실패 포함) | **24시간 백오프(신규)** |
| `address_error` | 카카오가 "그 주소 없음"이라고 답함(영구) | **없음 — 쿼터 안 태움** |

- 일시 오류(키 부재·타임아웃·429·5xx·네트워크)는 `failed` 로 굳히지 않고 `pending` 으로
  남긴다 → 기존 스윕 `pending_retry_before` 술어가 그대로 재시도한다.
- 영구 오류는 `address_error` → 사람이 주소를 고쳐야 하는 건. 주소를 고치면 write 경로
  (`reset_order_geocode_on_address_change`)가 `pending` 으로 되돌리므로 자동 복귀한다.
- 화면은 안 바뀐다: 읽기 경로에서 `address_error` → `failed` 로 정규화해 기존
  "주소 오류 - 수정 필요" 배지를 그대로 쓴다(정규화 지점 2곳: `map_snapshot`, `erp_map`).

### D2. 재큐 백오프 술어를 SSOT 로 뺀다

지금 세 곳이 각자 판정한다 — `foms/api/erp_map.py:285`(failed 영구 제외),
`foms/api/measurement/map.py:42`(24h 백오프), `foms/services/geocode_candidates.py`(SQL).
신규 모듈 `foms/services/geocode_retry.py` 에 파이썬 술어 + 상태 정규화를 모으고
세 곳이 그걸 부른다. (신규 모듈 = PTC 물리 인벤토리 등재 필요 — T2 완료 기준에 포함)

---

## Task 원장

| Task | 내용 | 상태 | 완료 기준 |
|---|---|---|---|
| T1 | 변환기 transient/permanent 분류 | **DONE** `43c765436` | 신규 계약 17건 green |
| T2 | 상태 소비단 + 자동 재시도 배선 | **DONE** `43c765436` | 신규 계약 16건 + 기존 스위트 green |
| T3 | `번길` 절단 수정 | **DONE** `84fca19d6` | 계약 4건 추가 green |
| T4 | 구 이름 부분 치환 수정 | **DONE** `84fca19d6` | 신규 계약 7건 green |
| T5 | 실호출 대조(T3·T4) — 운영 카카오 키 | **DONE** | 아래 §T5 결과 표 |
| T6 | 전수 검증 + deploy push | **DONE** `f3d3f04f5` | 본 스위트 7645 green · smoke exit 0 |
| T7 | 문서 반영(AI_STATUS·CHANGELOG·원장 마감) | **DONE** | — |
| T8 | 운영 승격(사용자 승인 후) | **DONE** PR #243 · production `c8492b6b` | 검사 4종 pass · WORKER 신코드 확인 |
| T9 | 남긴 것 — 동네 중심 좌표를 성공으로 반환하던 폴백 | **DONE** PR #251 · production `17bc0027` | 아래 §T9 |
| T10 | **미규명 트리거 규명** — SIDEFX 카카오 키 부재 | **DONE** | 아래 §T10 |
| T11 | 곁가지 — 배달할 일 없는 outbox 행이 DEAD 로 쌓이던 것 | **DONE**(deploy 대기) | 아래 §T11 |

---

### T1 — 변환기가 실패 사유를 가른다

대상: `foms/services/common/address_converter.py`

- `_try_address_api`/`_try_keyword_api` 가 실패 종류를 함께 돌려준다:
  - `permanent`: HTTP 200 + `documents` 비었음 / 좌표가 한국 bbox 밖.
  - `transient`: `requests` 예외(타임아웃·연결)·키 부재(`kakao_rest_headers()` 실패)·
    HTTP 401/403/429/5xx·JSON 파싱 실패.
- `analyze_address` 는 **한 전략이라도 transient 를 만났고 끝내 성공하지 못했으면**
  결과를 transient 로 보고한다(성공하면 성공이 이긴다).
- 공개 API: `convert_address_with_reason(address) -> (lat, lng, status, failure_kind)`.
  기존 `convert_address`/`analyze_address` 시그니처는 유지(호출자 무변경).
- transient 결과는 **캐시에 실패로 저장하지 않는다**(600초 동안 같은 오답 재사용 금지).

완료 기준:
`pytest tests/domains/test_address_converter_failure_kind.py -q` exit 0. 포함할 케이스
(전부 음성 대조군 동반):
1. 타임아웃(`requests.Timeout`) → `transient`, **양성 대조**: 200 + documents 0건 → `permanent`.
2. 429 / 500 → `transient`, **음성 대조**: 200 + 정상 문서 → 성공(`failure_kind is None`).
3. 키 부재(`kakao_rest_headers` 예외) → `transient`.
4. bbox 밖 좌표 → `permanent`(일시 오류로 오분류하지 않는다).
5. 1개 전략 transient + 다음 전략 성공 → 성공.
6. transient 실패는 실패 캐시에 남지 않는다(같은 주소 재호출 시 API 재시도).

### T2 — 상태 소비단 + 자동 재시도

대상: `geocode_helpers.py`, `geocode_delivery_handler.py`, 신규 `geocode_retry.py`,
`geocode_candidates.py`, `run_geocode_sweep.py`, `erp_map.py`, `measurement/map.py`,
`map_snapshot.py`

- `apply_geocode_to_order`: transient → 좌표 유지/삭제 규칙은 그대로지만
  `geocode_status='pending'` + `geocoded_at` 스탬프, 반환 `GEOCODE_OUTCOME_TRANSIENT` 신설.
  permanent → `address_error`.
- `handle_geocode`(SIDEFX): transient 는 **예외를 올려** worker 재시도 경로로 보낸다.
  모듈 docstring 의 "변환 실패=데이터 문제" 규정을 이 구분에 맞춰 다시 쓴다.
- `build_missing_geocode_query`: `failed_retry_before` 인자 추가(기본 24h),
  `address_error` 는 어떤 경우에도 후보에서 제외.
- 스윕 루프: 기본으로 24시간 지난 `failed` 를 다시 집는다(start.sh 변경 없음).
  `--include-failed` 는 "백오프 무시하고 전부"로 의미 확장, 로그 1줄에 백오프 값 표기.
- `erp_map.py:285`: `not stored_geocode_status` → 공용 술어 호출(pending/최근 시도/
  `address_error` 제외). 응답 `conversion_status` 는 정규화값(`failed`)으로 내보낸다.
- `measurement/map.py`: 자체 술어를 공용 모듈에 위임(상수명은 하위호환 유지).

완료 기준: 아래 전부 exit 0
`pytest tests/domains/test_geocode_helpers.py tests/domains/test_geocode_delivery_handler.py
tests/domains/test_geocode_sweep.py tests/domains/test_measurement_map_geocode_requeue.py
tests/domains/test_geocode_retry_policy.py tests/domains/test_map_snapshot.py -q`
+ `pytest tests/contracts/runtime/test_ptc_physical_exactness.py -q`(신규 모듈 등재)
신규 계약(음성 대조군 포함):
- transient → `pending` 이고 **`failed` 가 아니다**(음성 대조: permanent 는 `address_error`).
- `address_error` 는 스윕 후보에 **안 잡힌다**(음성 대조: 같은 조건의 `failed` 는 24h 뒤 잡힌다).
- `failed` 는 24h 전에는 안 잡힌다(대조: 24h + 1초면 잡힌다).
- SIDEFX handler: transient 는 예외, permanent 는 정상 반환(DONE).
- 화면 정규화: `address_error` 를 읽으면 `conversion_status == 'failed'` 로 나온다.

### T3 — `번길` 절단

대상: `foms/services/common/address_query.py:21` `_ROAD_RE`

건물번호 뒤에 한글+`길` 이 바로 붙으면 거기서 자르지 않는다(부정 전방탐색).

완료 기준: `pytest tests/domains/test_address_query.py -q` exit 0. 신규 케이스:
- `서울 강남구 강남대로 123번길 45` → `서울 강남구 강남대로 123번길 45`(절단 없음)
- `경기 성남시 분당구 판교로 256번길 25 (삼평동)` → `경기 성남시 분당구 판교로 256번길 25`
- 음성 대조: `경기 의왕시 시청로 42 108-1701` → `경기 의왕시 시청로 42`(기존 절단 유지)
- 음성 대조: `동패동 2287-15` 지번 보존(기존 계약 불변)
- `번길` 이 없는 일반 도로명은 전부 기존 결과와 동일(기존 테스트 전부 green)

### T4 — 구 이름 부분 치환

대상: `scripts/ops/foms_advanced_address_processor.py:197-199` `_normalize_district`

`강남`→`강남구` 류 치환을 **앞뒤가 한글이 아닐 때만** 적용한다.

완료 기준: `pytest tests/domains/test_advanced_address_processor_district.py -q` exit 0.
- `서울특별시 서초구 서초대로 396 강남빌딩 5층` → `강남구빌딩` 안 생김,
  `extract_address_components(...)['district'] == '서초구'`
- 음성 대조(치환이 살아있어야 하는 쪽): `서울 강남 역삼동` → `강남구` 로 보완됨
- 음성 대조: `서울특별시 강남구 …` 는 이미 `강남구` 라 무변경

### T5 — 실호출 대조 (운영 카카오 키)

`railway variables --service WORKER` 에서 키를 읽어(값 출력·커밋 금지) T3·T4 수정 전/후
좌표를 실제로 대조한다. 대상 주소는 T3·T4 케이스 + 원장에 남은 실패 27건 중 해당 형태.

완료 기준: 수정 전 좌표와 수정 후 좌표가 **다르고**, 수정 후 좌표가 실제 도로/구에
해당함을 카카오 응답(`road_address_name`/`address_name`)으로 확인한 표를 원장에 기록.

### T6 — 검증 + push

완료 기준(순서대로 exit 0):
1. `python -c "import app; print('APP_OK')"`
2. `pytest tests/domains/... tests/contracts/...`(T1~T4 신규 + 회귀 스위트)
3. `pytest tests/visual -q` (본 스위트가 `--ignore` 하는 사각 — CI red 전력 있음)
4. `scripts/ops/pre_push_smoke.ps1` exit 0
5. `origin/deploy` 리베이스 후 자기 커밋만 push → `gh run list` 로 커밋별 전 워크플로 green

### T7 — 문서

`docs/AI_STATUS.md`·`docs/AI_CHANGELOG.md` 갱신, 본 원장 T1~T6 결과·SHA 기록,
조사 원장에 "수정 완료" 줄 추가. production 승격은 **별도 승인 후** 자기 커밋 cherry-pick.

---

## 진행 기록

(각 T 완료 시 SHA·검증 출력 요약을 여기 append)


---

## 진행 기록 (실측)

### 커밋

| SHA(원격) | 내용 |
|---|---|
| `43c765436` | T1+T2 — 실패 종류 분류·상태 4상태화·재시도 SSOT |
| `84fca19d6` | T3+T4 — 번길 절단·구 이름 부분 치환 |
| `f3d3f04f5` | 네임스페이스 공개 표면 계약에 `GEOCODE_OUTCOME_TRANSIENT` 등재 |

기준: `origin/deploy` `6e8a6f75e` 위에 리베이스 후 자기 커밋만 push.

### T5 — 운영 카카오 키 실호출 대조 (2026-09-01, 읽기 전용 검색)

키는 `railway variables --service WORKER` 에서 환경변수로만 읽었다(출력·커밋 없음).
질의는 변환기와 같은 순서(address API → keyword API)로 보냈다.

**T3 번길 절단** — 수정 전 질의 vs 수정 후 질의

| 원본 주소 | 수정 전 질의 → 결과 | 수정 후 질의 → 결과 | 거리 |
|---|---|---|---|
| 서울 종로구 종로 1길 50 | `종로 1` → 37.570986, 126.977983 (**다른 지점**) | `종로 1길 50` → 37.574724, 126.979022 (`종로1길 50`) | **426 m** |
| 경기 성남시 분당구 판교로 256번길 25 | `판교로 256` → 조회 실패 | `판교로 256번길 25` → 37.400411, 127.103133 (`판교로256번길 25`) | — |
| 서울 강남구 테헤란로 152 (음성 대조군) | 같은 질의 → 37.500024, 127.036509 | 같은 질의 → 동일 | **0 m** |

종로 사례가 이 결함의 성격을 그대로 보여준다: 수정 전에도 **좌표가 나왔다**. 실패가 아니라
426 m 떨어진 다른 지점을 성공으로 반환했다.

**T4 구 이름 부분 치환** — 6단계 `simplified` 폴백이 실제로 던지는 질의

| 축 | 수정 전 | 수정 후 |
|---|---|---|
| 전처리 결과 | `서울특별시 서초구 서초대로 396 **강남구빌딩**` | `서울특별시 서초구 서초대로 396 강남빌딩` |
| simplified 질의 | `서울특별시 강남구` | `서울특별시 서초구` |
| 좌표 | 37.517332, 127.047377 | 37.483589, 127.032735 |

두 좌표는 **3,968 m** 떨어져 있다. 서초구 주소에 강남구 핀이 꽂히던 것이 사라진다.

### T6 — 검증 결과

| 검증 | 결과 |
|---|---|
| `python -c "import app; print('APP_OK')"` | APP_OK |
| 본 스위트 `pytest -q --ignore=tests/visual --ignore=tests/harness -n auto` | **7645 passed, 587 skipped** |
| `scripts/ops/pre_push_smoke.ps1` | **exit 0** (377 passed) |
| `tests/visual` 전수 (win32 baseline, 로컬) | 19 failed / 293 passed |

visual 레인 실패 19건은 **본 변경과 무관한 기존 드리프트**다. 같은 명령을 수정 전
`origin/deploy`(`6e8a6f75e`) 워크트리에서 돌려 **실패 목록이 완전히 동일**함을 확인했다
(`test_visual_regression` 6 + `test_erp_mobile_v2_shell_regression` 6 + `test_p1_mobile_ux_smoke` 4
+ `test_scheduler_panel_compact` 2 + `test_erp_order_edit_mobile_form` 1). 로컬 win32 스크린샷
기준선 드리프트이며 CI 는 linux 기준선으로 별도 워크플로에서 판정한다.

### 남긴 것 / 후속

* 변환기 6단계 `simplified` 폴백은 여전히 **구 중심 좌표를 "성공"으로 반환**한다.
  T4 로 구 오판은 사라졌지만, "구 좌표를 그 주문의 좌표로 삼는" 설계 자체는 그대로다
  (이번 범위 밖 — 별도 판단 필요).
* 운영 DB 의 기존 `failed` 27건은 이번 배포 후 스윕이 24시간 백오프로 자동 재시도한다.
  주소가 진짜 나쁜 건은 `address_error` 로 갈라져 이후 쿼터를 태우지 않는다.
* 실측 지도에서 `pending` 재큐 동작이 바뀌었다: 예전에는 `pending` 을 절대 재큐하지 않아
  고착 건이 영구히 남았는데, 이제 600초 백오프를 지난 `pending` 은 다시 집는다.
  중복 enqueue 는 재큐 시 `geocoded_at` 시도 표식을 찍어 막는다.


### T8 — 운영 승격 (2026-09-02)

사용자 승인 후 자기 커밋 4개만 cherry-pick → PR #243 → merge.

* 승격 트리 직접 검증: 본 스위트 **7632 passed**, PG 레인 **738 passed**, `pre_push_smoke` exit 0, `APP_OK`.
  (승격 PR 은 production 계보 워크플로로 돌아 본 스위트를 다 돌지 않는다 — 그래서 트리에서 직접 돌렸다.)
* PR 검사 4종 전부 pass(test 2m56s · pg-lane 2m1s · harness 1m11s · perf-gate 1m18s), `mergeStateStatus=CLEAN`.
* 충돌은 docs 계보 2건뿐: `docs/AI_STATUS.md` 는 production 계보 유지(ours),
  조사 원장은 production 에 없던 파일이라 통째로 반입. **코드 파일은 production 과 승격 베이스가 전부 동일**
  (`git diff --numstat origin/production 43c765436^` 전 파일 0) — 코드 의존 0건.
  completeness 가 보고한 missing 84건은 전부 docs 계보였다.

**운영 반영 확인**

| 축 | 결과 |
|---|---|
| web `/healthz` | `{"commit":"c8492b6be13c…","status":"ok"}` |
| WORKER 신코드 | 부팅 로그 `[geocode-sweep] started (… pending_retry=600s failed_retry=86400s)` — `failed_retry` 는 이번 변경에만 있는 문구 |
| 워커 로그 오류 | 없음(sweep 라운드 `scanned=0 queued=0` — 좌표 미달 0 유지) |
| 운영 DB (읽기 전용) | `success 3784 · failed 20 · NULL 8`, `address_error 0`(배포 직후라 정상) |

`failed` 20건은 2026-09-01 07:47 UTC 백필이 마지막 시도라, 24시간 백오프가 지나는 시점부터
스윕이 자동으로 다시 집는다. 그중 주소가 진짜 나쁜 건만 `address_error` 로 갈라져 이후 쿼터를 태우지 않는다.


---

## T9 — 동네 중심 좌표 폴백 (2026-09-02, 사용자 지시로 범위 추가)

T1~T8 에서 "범위 밖"으로 남겼던 6단계 `simplified` 폴백을 실측으로 재고 고쳤다.

### 얼마나 있었나 (운영 실측, 읽기 전용)

주문마다 카카오를 다시 부르지 않고 **저장된 좌표가 그 주소의 동네 중심 좌표와 같은지**로 셌다
(simplified 질의 문자열 종류별로 1회씩만 호출 — 817종). 좌표 있는 활성 주문 3,784건 중
**4건**이 동네 중심 좌표였다.

| 주문 | 저장된 좌표의 정체 | 진짜 위치와의 거리 |
|---|---|---|
| #2418 `성동구 금호4가동 1546-4` | `서울특별시 성동구 **성동**` 중심 | **2,214 m** |
| #1781 `관악구 성현동, 관악센트씨엘` | `관악구 성현동` 중심 | 0 m (주소 자체가 동 단위) |
| #905 `송파구 **신천동구** 피크리오` | `송파구 신천동` 중심 | 측정 불가(주소가 틀림) |
| #2690 `오산시 궐동 432-4 세교파라곤` | `오산시 궐동` 중심 | 0 m (더 나은 답 없음) |

#2418 이 결함의 정체를 보여준다. `extract_address_components` 의 동 추출 정규식 `(\w+동)` 이
**구 이름에서 동을 만들어 냈다** — `성동구` 의 `성동`. 그 값으로 폴백이
`서울특별시 성동구 성동` 을 물어봤고, 엉뚱한 좌표가 `success` 로 굳었다.

### 고친 것 3가지

1. **동 추출** (`_extract_dong` 신설) — 뒤에 한글이 이어지면(`성동`구) 건너뛰고,
   `112동` 같은 아파트 동 번호도 제외한다.
2. **`시 + 구` 만으로는 폴백하지 않는다** — 구 중심 좌표는 수 km 오차다. 동까지 있을 때만.
3. **일시 오류를 겪었으면 폴백 자체를 하지 않는다** — 네트워크가 흔들려 앞 전략이 죽은 자리를
   동네 중심 좌표로 덮으면, 재시도됐어야 할 건이 성공으로 굳는다(#2418 이 그 모양).

### 수정 후 실호출 결과 (운영 키)

| 주문 | 수정 후 | 판정 |
|---|---|---|
| #2418 | `성공 (shared_variant2)` — **진짜 금호4가동 좌표**, 저장값에서 2,214 m | 오답이 정답으로 |
| #905 | `permanent` (좌표 없음) | 주소가 틀린 건이라 사람이 고쳐야 한다 — 이제 그렇게 말한다 |
| #1781 | `성공 (stripped)` 0 m | 폴백과 무관, 불변 |
| #2690 | `성공 (simplified)` 0 m | 동 단위지만 더 나은 답이 없다 — 유지(coverage 보존) |

### 검증

본 스위트 **7735 passed**, PG 레인 **738 passed**, `pre_push_smoke` exit 0, `APP_OK`.
신규 계약 8건(음성 대조군 동반): 구 단위 폴백 금지·동 있으면 허용·일시 오류 뒤 폴백 금지·
동 오추출 4종.

### 운영 데이터

#905·#2690 는 `success` 라 자동 재변환 대상이 아니다(주소를 고치면 write 경로가 되돌린다).
#2418 은 배포 후에도 저장값이 그대로다 — **좌표 정정은 운영 쓰기라 별도 승인 사항**으로 남긴다.


---

## T10 — 최초 트리거를 찾았다: `SIDEFX` 서비스에 카카오 키가 없다 (2026-09-02)

T8 승격 뒤 운영 DB 를 다시 읽다가 **배포 이후에도 새 `failed` 가 계속 생기는 것**을 봤다.
새 코드는 `failed` 를 쓰지 않는다(`success`/`pending`/`address_error` 뿐) — 그래서 옛 코드를
도는 프로세스가 살아 있다는 뜻이었다.

### 추적

| 단계 | 관측 |
|---|---|
| 운영 DB | 배포(22:47 UTC) 이후 23:09·23:23·23:25·23:46 에 `failed` 4건 추가 |
| 코드 | `origin/production` 트리에 `geocode_status='failed'` 를 쓰는 살아있는 경로 **0곳** |
| 서비스 목록 | `Redis / web / **SIDEFX** / WORKER / FOMS-cron / Postgres` |
| SIDEFX 로그 | `[geocode] order 5099 address conversion failed — marked failed, no retry` ← **옛 문구** |
| SIDEFX 환경변수 | **`KAKAO_REST_API_KEY` 없음** (web·WORKER 는 있음) |
| 그 주소들 | 같은 운영 키로 직접 변환 → **4/4 첫 전략(stripped)에서 성공** |

**기전**: 키가 없으면 `kakao_rest_headers()` 가 `RuntimeError` → (수정 전) 변환기가
`except Exception` 으로 삼켜 "AI 변환 실패" → 저장단이 `geocode_status='failed'`.
조사 원장이 관측한 `attempts=1 · last_error=NULL · DONE`(사유 없이 "좌표 없음")이 이것이다.

2026-09-01 조사가 이 서비스를 못 본 이유는 **운영 서비스를 3개(web·WORKER·FOMS-cron)만
확인했기 때문**이다. SIDEFX 는 그 뒤 등록됐다.

### 조치 (사용자 승인 후)

1. `SIDEFX` 에 `KAKAO_REST_API_KEY` 설정(WORKER 와 같은 값) → 재배포(신코드 동반).
   재기동 확인: `[sidefx-worker] started owner=8f41a57685de interval=5s`.
2. 옛 코드가 오늘 잘못 찍은 5건(#5095~#5099) 재변환 — **5/5 success**.
   대상 id 5개 고정·`failed`+좌표없음일 때만 진행·저장 SSOT(`apply_geocode_to_order`) 사용,
   쓴 컬럼은 lat/lng/geocode_status/geocoded_at/address_hash 뿐(알림·이벤트 0).
3. 운영 분포: `success 3789 · failed 19 · NULL 8`(재변환 전 3784/24/8).

### 이 결함이 다시 나면

근본 수정 ①이 배포된 지금은 키가 빠져도 **`transient`** 로 갈려 재시도 경로로 간다 —
멀쩡한 주소가 "주소오류" 로 굳지 않는다. 즉 설정 사고가 데이터 오판으로 번지는 길이 끊겼다.

### 곁가지 관측 (별개 결함, 이 원장 범위 밖)

SIDEFX 는 `CHANNEL_PUSH_RECORDED` 핸들러가 등록돼 있지 않아 그 effect_type 을 계속
`NoHandlerError` 로 재시도한다(로그 다수). 별도 판단 필요.


---

## T11 — 배달할 일이 없는 outbox 행 1,188개가 DEAD 로 쌓이고 있었다 (2026-09-02)

T10 에서 SIDEFX 로그를 읽다 발견한 별개 결함. 사용자 지시로 범위에 넣었다.

### 실측 (운영 outbox 전수)

| effect_type | status | 건수 | 최초 ~ 최종 |
|---|---|---|---|
| `CHANNEL_PUSH_RECORDED` | DEAD | **1,188** | 08-03 ~ 09-01 |
| `CHANNEL_PUSH_RECORDED` | PENDING | 2 | 09-01 |
| `STAGE_NOTIFICATION` | DEAD | 118 | 08-03 ~ 09-01 |
| `GEOCODE` | DONE | 101 | 08-06 ~ 09-01 |
| `STORAGE_DELETE` | DONE / PENDING | 325 / 124 | 08-11 ~ 09-01 |

`CHANNELTALK_PUSH` OrderEvent 는 같은 기간 **1,190건** — DEAD 1,188 + PENDING 2 와 맞는다.
즉 **푸시 기록 행은 하나도 빠짐없이 죽었다.**

### 기능 손실은 없었다 (그래서 더 위험했다)

채널톡 전송은 이 outbox 와 무관하게 이미 끝났고(전송이 먼저·기록이 나중), 이력
(`structured_data.channeltalk_push*` — 584주문)과 OrderEvent 는 같은 트랜잭션에서 쓰인다.
이 행의 유일한 역할은 **같은 send 를 두 번 기록하지 않게 막는 dedupe** 다.

문제는 그 1,188행이 worker 로그와 DEAD 목록을 채워 **진짜 배달 실패를 덮는다**는 것이다.
T10 에서 GEOCODE 실패를 찾을 때 실제로 이 로그를 헤집고 지나가야 했다.

### 수정

`foms/services/record_only_effects.py` 신설 — "배달할 일이 없음"을 **명시적으로 등록**한다.
등록을 빼먹어서 죽는 것과, 할 일이 없어서 바로 끝나는 것은 다른 상태여야 한다.
러너(`tools/ops/run_domain_side_effect_outbox.py`)가 `CHANNEL_PUSH_RECORDED` 를 이 handler 로
등록한다.

계약 3건(`tests/domains/test_sidefx_record_only_effects.py`):
등록 결과 확인(주석만 남기고 호출을 지우는 회귀 차단)·부수효과 0·**음성 대조군**으로
미등록 타입은 종전대로 `NoHandlerError`(모르는 타입을 조용히 통과시키는 퇴화 차단).

검증: 본 스위트 **7755 passed**, PG 레인 sidefx 26 passed, `pre_push_smoke` exit 0.

### 남은 판단 (사용자 몫)

* **`STAGE_NOTIFICATION` 118행**: 이쪽은 *기록 전용이 아니라 소비자 미구현*이다.
  운영 `notifications` 전수 조회 결과 단계 전이 알림 유형은 **한 번도 존재한 적이 없다**
  (있는 유형: DRAWING_TRANSFERRED·SHIPMENT_ORDER_CHANGED·ERP_ORDER_CHANGED·
  NAVER_ORDER_CLAIMED·PRODUCTION_ORDER_CHANGED 등). 즉 회귀가 아니라 미구현이다.
  "단계 전이 알림을 낼 것인가"는 제품 결정이라 손대지 않았다.
* 이미 쌓인 DEAD 1,188행은 되살리지 않는다 — 배달할 것이 없다(retention 이 정리한다).
