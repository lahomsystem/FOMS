# 느린 첫 로딩 원인 기록(RUM 느린 화면 분해) — SPEC (2026-10-21)

## 목적
사용자 신고(2026-10-21): "한용희 사용자가 초기 로딩이 느리다". 운영 RUM 7일(11,019건)을 실시간 연결 시각으로 사람별로 나눠 보니,
한용희(id 25)·id 47 은 화면 로드의 **16~18%** 가 4.7~7.0초다(나머지 12명 0~5%). 같은 화면 크기(같은 기종 추정)인 27·58 은 정상이라
기종 탓이 아니고, 배포 직후·유휴 시간과 무관하며, 값이 약 5초에 몰린다. 지금 RUM 은 `LOAD` 숫자 하나만 남겨
**무엇을 기다렸는지**(서버 응답·외부 CDN·우리 정적 파일·캐시 없음)를 가를 수 없다. 느린 로드에서만 분해 정보를 함께 남긴다.

## 지금 구조
- `static/js/foms/rum-baseline.js` 가 `LOAD`(navigation `loadEventEnd`)·LCP·INP·SWAP 을 `/api/foms/rum` 에 보낸다.
- `foms/api/foms_rum.py` `_validate_rum_payload` 는 키 5개(`metric value path viewport mobile_v2`)만 받고 그 밖은 400. 통과한 값은
  한 줄 JSON 로그(`foms.rum`) + 일별 히스토그램(`record_metric`, metric·value 만).
- 사용자 식별 정보는 없다(익명). 사람별 분석은 로그 시각을 실시간 연결 로그와 맞춰서 한다(메모 레시피).

## 변경
1. **클라이언트**(`rum-baseline.js`, `LOAD` 만): 값이 **3,000ms 이상**일 때만 두 필드를 더 싣는다.
   - `nav`: navigation 항목에서 정수 ms 6개 — `dns`(domainLookupEnd−Start), `conn`(connectEnd−connectStart, TLS 포함),
     `ttfb`(responseStart−requestStart), `resp`(responseEnd−responseStart), `dcl`(domContentLoadedEventEnd), `redir`(redirectEnd−redirectStart).
   - `slow`: resource 항목 중 `duration` 상위 **3개**. 항목마다 `h`(호스트 이름), `p`(우리 도메인 `/static/` 이면 쿼리 뺀 경로,
     그 밖은 확장자만 — 사진 주소·서명·주문 번호를 남기지 않는다), `d`(duration), `s`(startTime), `c`(transferSize==0 이고
     decodedBodySize>0 이면 `1`=캐시, 아니면 `0`), `k`(initiatorType 앞 8자).
   - 3초 미만 로드는 지금과 똑같이 보낸다(크기·개수 변화 0).
2. **서버**(`foms_rum.py`): 허용 키에 `nav`·`slow` 추가, 엄격 검증(아니면 400 — 지금 계약과 같은 방식).
   - `nav`: 정해진 6개 키만, 각 0~120,000 정수. `slow`: 리스트 길이 ≤3, 항목 키 6개만, `h` 는 호스트 문자(영숫자·`.`·`-`) 253자 이하,
     `p` 는 `/static/` 으로 시작하는 쿼리·조각 없는 경로(≤200자) 또는 `.` + 영숫자 ≤8자, `d`·`s` 0~120,000, `c` 0/1, `k` 영소문자 ≤8자.
   - `metric` 이 `LOAD` 가 아니면 두 필드는 400. 통과 시 로그 한 줄에 그대로 싣고, 히스토그램 집계는 그대로(metric·value 만).
3. 정적 자산 핀: `rum-baseline.js` 를 싣는 템플릿의 `?v=` 를 올린다.

## 건드리지 않는 것
- 사용자 식별·IP·UA 를 RUM 에 넣지 않는다(익명 유지). 사람 구분은 지금처럼 로그 시각 조인으로 한다.
- 히스토그램·`/api/foms/rum/report`·rum-daily 판정 — 값과 개수가 그대로다.
- 원인을 고치는 변경(외부 CDN 을 우리 서버로 옮기기 등) — 기록이 쌓인 뒤 원인을 보고 따로 정한다.

## 판단 방법(배포 뒤 1~2일)
한용희·47 의 느린 로드에서 `nav.ttfb` 가 크면 서버, `slow[0].h` 가 `cdn.jsdelivr.net`·`cdnjs.cloudflare.com`·`cdn.socket.io` 면 외부 CDN,
우리 호스트 + `c=0` 이 여럿이면 캐시가 비워진 것, `nav.dns`·`nav.conn` 이 크면 그 망의 연결 문제다.

## 테스트
- `tests/` RUM 계약 테스트에 추가: `LOAD`+정상 `nav`·`slow` 200, 로그 줄에 두 필드가 실린다 / 키 초과·값 범위·`slow` 4개·
  `p` 에 쿼리·`h` 에 `/`·`LCP` 에 `nav` 는 400 / 기존 5키 페이로드는 그대로 200(음성 대조군).
- JS: `node --check` + 3초 미만이면 두 필드가 없다는 것을 소스 계약으로 고정.
- 스테이징: 실제 브라우저로 느린 로드를 흉내(네트워크 지연)해 로그 줄에 `nav`·`slow` 가 남는지 확인.
