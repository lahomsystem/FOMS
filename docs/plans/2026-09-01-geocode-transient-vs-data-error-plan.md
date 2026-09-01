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
