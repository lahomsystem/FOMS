# 지오코딩 일시오류/주소오류 분리 — 원장 (2026-09-01)

## 배경 사실 (전부 실측)

사용자 신고: 운영 실측 지도(`/map_view?dashboard=measurement`)에 `주소오류` 배지가 붙은 주문들이
있는데, 그 주소를 주소 수정 모달에서 검색하면 10건씩 정상으로 나온다.

조사 결과 **주소는 무죄였다.**

- 실패 11건 전부를 운영 카카오 REST 키 + 운영과 동일한 코드로 직접 변환 → **11/11 성공**
  (대부분 첫 전략 `stripped` 에서 즉시 좌표 획득, 나머지는 keyword 검색으로 성공).
- 카카오 address API 는 **원본 주소 통째로도** 좌표를 준다(`total_count=1`, x/y 정상).
  괄호 `(법정동, 아파트명)`·동호수·이중공백 전부 무해.
- 반례: 같은 날 07:28 에 **같은 괄호 형태**가 성공했다.
  `일산서구 강선로 188 (일산동, 후곡마을11단지아파트) 1105동 1406호` → success.
  도로명이 아예 없는 `인천 부평 두산위브더파크 105동1703호` 도 success.
- outbox 행은 `attempts=1 · last_error=NULL · DONE` — 예외 흔적 없이 "좌표 없음"으로 판정됐다.
- 운영 3개 서비스(web·WORKER·FOMS-cron) 전부 같은 커밋, 전부 `KAKAO_REST_API_KEY` 설정됨.
  워커 재배포 누락도 아니고 키 부재도 아니다.

**최초 실패를 유발한 트리거는 규명하지 못했다.** 실패는 이전 배포에서 났고 Railway 로그는
현재 배포분(07:14)부터만 남아 있다. 변환기가 예외를 문자열로 삼켜 DB 에도 사유가 안 남는다 —
이 "사유가 안 남는다"는 사실 자체가 아래 결함 1의 증상이다.

## 당장 조치 (완료)

`python tools/ops/backfill_geocode_missing.py --apply --mode sync --include-failed --limit 60`
운영 DB 대상 실행(2026-09-01 07:47 UTC). 58건 중 **40건 성공**, 실패 66→27건.
신고된 11건(5077·5080·5081·5084·5085·5086·5087·5088·5089·5091·5092) **전부 success**.
쓴 것은 `lat`·`lng`·`geocode_status`·`geocoded_at`·`address_hash` 5개 컬럼뿐(알림·이벤트 0).

남은 27건은 주소에 메모가 섞인 진짜 지저분한 값들이다 —
`검암ehd 597-4 엘리시움 2동 303호`, `해체지: 송파구 송파대로40길 7-7 303호`,
`구로 고척 경남 2차 203-1201 (공실) 오전일찍시공요청 / 오후 입주청소예정` 등.

> **[2026-09-01 마감] 아래 4건 전부 수정 완료 — deploy `f3d3f04f5`(커밋 3개).**
> 실행 원장·실호출 대조 표·검증 결과: `docs/plans/2026-09-01-geocode-transient-vs-data-error-plan.md`

## 고쳐야 할 것 4건 (사용자 승인 범위)

### 1. 일시 오류와 주소 오류를 구분한다 (근본 원인 자리)

`foms/services/common/address_converter.py:141,173` 이 키 부재·타임아웃·429·HTTP 비200 을
전부 `except Exception` 으로 삼켜 `"API 오류: …"` 문자열로 강등하고, 최종적으로
`:331` 이 `"AI 변환 실패"` 를 반환한다. 그러면 `foms/services/geocode_helpers.py:179` 가
`geocode_status='failed'` 로 박는다. **네트워크 사고와 주소 오류가 DB 에서 구분되지 않는다.**

`foms/services/geocode_delivery_handler.py:15-17` 은 변환 실패를 "데이터 문제"로 규정해
예외를 올리지 않고 DONE 처리한다 — 그 규정이 맞으려면 변환기가 둘을 갈라줘야 한다.

요구: 변환기가 **재시도 가능한 실패(transient)** 와 **주소가 나쁜 실패(permanent)** 를 구분해
반환하고, transient 는 `failed` 로 굳히지 말고 재시도 경로로 보낸다.

### 2. 실패 건도 자동으로 다시 시도한다

- 상시 스윕이 `include_failed=False` 로 돈다 — `start.sh:36`(운영 로그
  `[geocode-sweep] started (… include_failed=False …)` 확인).
- 범용 ERP 지도는 `not stored_geocode_status` 조건이라 `failed` 를 **영구 제외** —
  `foms/api/erp_map.py:285`.
- 유일한 구제책이 실측/AS 지도의 24시간 백오프 재큐 — `foms/api/measurement/map.py:42`.

요구: 실패 건도 backoff 를 두고 자동으로 재시도되게 한다(쿼터 소모가 트레이드오프 —
transient/permanent 구분이 선행되면 permanent 는 재시도에서 빼면 된다).

### 3. `번길` 절단 — 실패보다 나쁜 조용한 오답

`foms/services/common/address_query.py:21` `_ROAD_RE` 가 도로명+건물번호까지만 남기는데,
`판교로 256번길 25` 를 `판교로 256` 으로 자른다. **서로 다른 도로다.**
워커는 이 잘린 문자열을 0번 전략으로 먼저 던지므로(`address_converter.py:283`)
실패가 아니라 **엉뚱한 좌표로 성공**한다 — 지도 마커가 수백 m~수 km 어긋난 채 정상으로 보인다.

실측 예: `서울 강남구 강남대로 123번길 45` → `서울 강남구 강남대로 123`,
`경기 성남시 분당구 판교로 256번길 25 (삼평동)` → `경기 성남시 분당구 판교로 256`.

### 4. 구 이름 부분 치환이 구를 오판한다

`foms/services/common/foms_advanced_address_processor.py:197-199` 의 `_normalize_district` 가
`'강남'→'강남구'`, `'서초'→'서초구'` 를 **부분 문자열 전역 치환**한다.
실측: `서울특별시 서초구 서초대로 396 강남빌딩 5층` → `… 강남구빌딩`, 컴포넌트 추출이
`district=강남구` 로 뒤집힌다. 그 상태로 6단계 `simplified` 폴백(`address_converter.py:311-322`)
이 돌면 **"서울특별시 강남구" 좌표를 성공으로 반환**한다.

## 기존 계약 테스트의 사각

`tests/domains/test_address_query.py:54` `test_modal_and_geocode_pipeline_share_the_same_preprocessing`
는 `strip_detail`/`query_variants` **문자열 동일성만** 본다. 위 1~4는 전부 이 테스트 밖이다
(호출 파라미터·성공 판정·문서 순회·bbox·예외 처리·실패 영속화).
"SSOT 화했다"는 사실이 비대칭 해소를 보장하지 않는다.

## 모달 vs 워커 남은 비대칭 (참고)

| 축 | 모달 `foms/api/address.py` | 워커 `address_converter.py` |
|---|---|---|
| 문서 채택 | 전 documents 순회 | **`documents[0]` 하나만** (`:109`, `:160`) |
| 좌표 검증 | x/y 존재만 | **한국 bbox 강제** (`:55-57`) |
| HTTP 비200 | 그 후보만 건너뜀 | **"주소를 찾을 수 없음"과 동일 취급** (`:139`, `:173`) |
| 예외 | HTTP 500 으로 드러남 (`address.py:159`) | 문자열로 강등 → 조용히 failed |
| 캐시 | 없음 | 프로세스 메모리, 실패 600초 (`:35`) |
| 요청 수 | 주소당 약 6회 | 주소당 최대 14회(7전략×2 API) |
