# 채널 정산(네이버) 대시보드 탭 — 스펙 v0.9 (승인 대기, 2026-09-02)

- 상태: **사용자 승인 대기** (RPI Plan 단계). 리서치 정본: `docs/research/2026-09-02-naver-settlement/` (R1~R5 + CEO 3인 판정)
- 워크트리: `c:/tmp/foms-s-settle-naver` · 브랜치 `session/settle-naver` · base `origin/deploy` 416a3acfc
- 진행 원장: `docs/plans/2026-09-02-naver-settlement-ledger.md`
- 선행 스펙: `docs/specs/2026-08-31-settlement-dashboard_SPEC.md` §비목표("채널 수수료 대사·반품 환불액 동기화는 후속 스펙") — 본 스펙이 그 후속이다.

## 0. 결정 (CEO 3인 만장일치 + 페르소나 2인 일치)

| 항목 | 결정 | 근거 요약 |
|---|---|---|
| 정보구조 | **C 하이브리드** — 탭 바 맨 오른쪽 4번째 탭(시스템 오브 레코드) + 기존 탭 접점은 v1.1 | 기존 3탭은 페르소나 축(경영진/경리/분석)·완료일 기준 발생주의, 네이버 정산은 데이터소스 축·정산예정일 기준 현금주의. 축이 달라 섞으면(B) 이중 계상·라벨 오독. 순수 A는 "오늘 입금 예정" 류 크로스 질문에 두 화면 왕복 |
| 탭 라벨 | **"채널 정산"** + 힌트 "네이버" (기존 `s-tab-name`/`s-tab-hint` 2줄 마크업) — 사용자 확인 대상 | 실무 탭에 이미 뜻이 다른 "정산상태"(내부 차감청구 발행 여부) 컬럼이 있어 "네이버 정산"은 동음이의 충돌. 라벨은 나중에 2줄로 바꿀 수 있음 |
| 코드 네임스페이스 | **채널 중립 고정**: `settlement_channel.py` / `/api/settlement/channel` / `s-ch-*` / `data-settlement-ch-*` / 테이블 `channel` 컬럼(기본 `NAVER`) | 네임스페이스는 나중에 못 바꾼다(자산 핀·계약 테스트·SW 캐시). `ExternalOrderLink.channel`과 같은 원칙 |
| 파이프라인 | **워커 전용 일 배치(시각창) + 롤링 30일 재조회 + 날짜 파티션 전면 교체(replace-by-day) + 백필은 야간 수동 enqueue** | web 프로세스는 네이버 IP 화이트리스트 밖(3슬롯=워커 egress). 소급 변경 실증(#3123)·완결 신호 없음(#3674) |
| 시간축 SSOT | **정산 예정일(`settleExpectDate`)** 단일 축. `settle/case`·`commission-details`는 `periodType=SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE` 고정 | `settle/daily`가 예정일 기준 필터(#1481)·완료일은 은행 처리 후에만 채워짐(#414) |
| 회계 비타협 | 부호 그대로(취소·환급 음수 유지)·네이버 값 재계산 금지·날짜축 라벨 상시 노출·정산예정≠완료 분리·충전금(`CHARGE_AMT`) 별도 라벨·VAT 전월 말일 제약 문구 | CEO-1 §D, CEO-3 §D |
| 등급 | `**C` 릴레이, v1 12 task(T0~T11) + v1.1 3 task | CEO-3 F.3 기준, CEO-2 22 task는 블록 세분화 차이 |

### T0 실측 결과 (2026-09-02 17:21 KST, 스테이징 워커 `railway ssh -s worker`, 읽기 전용)
- 기존 주문 API(`get_last_changed_statuses`) **OK** — 토큰·IP 정상.
- 정산 5종 전부 **HTTP 403 `GW.AUTHN` "요청을 보낼 권한이 없습니다."** — 토큰 강제 재발급도 동일 토큰 반환(네이버는 유효기간 내 같은 토큰 재사용).
- 원인 후보: (1) [정산] 그룹이 **다른 애플리케이션**에 추가됨(FOMS env `NAVER_COMMERCE_CLIENT_ID` 앞 4자 `4RYv`) (2) 권한 추가 후 **기존 토큰 만료 전** — 스테이징 토큰 잔여 약 96분(≈18:58 KST 만료) 뒤 새 토큰으로 재검증 필요. 공식 답변 #1205·#2788: 토큰을 발급한 '내스토어 애플리케이션'에 [정산] 그룹이 있어야 한다.
- **T0 재검증 통과 전 T2 이후 착수 금지.**

## 1. 화면 — "채널 정산" 탭 (1440px 기준, 좁은 폭은 container query)

구조 = **고정 컨텍스트(상단) + 원장 스위처(하단)**. 중첩 탭이 아니라 Stripe Balance/Shopify Payouts형.

| ID | 블록 | 형태(기존 어휘 재사용) | 엔드포인트 | 등급 |
|---|---|---|---|---|
| S0 | 동기화 헤더: 최종 동기화·적재 구간·롤링 폭·지연 배지·확정 구간·[지금 동기화] | 텍스트+배지+버튼 | SystemSetting 워터마크 | v1 |
| S-bar | 기준일 셀렉터(기본 **정산 예정일**, 완료일·기준일·결제일 전환)·기간·일/주/월·전기 비교 — "정산 예정일 기준(완료일 아님)" 상시 라벨 | 기존 필터바 복제(채널 탭 전용) | — | v1 |
| S1 | KPI 6타일: 정산 완료액 / 정산 예정액(계좌입금 예정·충전금 상계 분리) / 수수료 합계 / 실효 수수료율(분모=결제정산액, 각주) / 보류·차감 / 주문 매칭률(→예외 큐) | `appendKpi`+`sparkSvg` | daily·case·commission | v1 |
| S2 | 일별 정산 흐름: 일반정산·빠른정산·공제환급 누적 막대 + 전기 비교선 | `columnChart` 스택 확장 | settle/daily | v1 |
| S3 | 정산 구성 워터폴: 결제정산액 → −수수료 → +혜택 → +공제환급 → −지급보류 → −충전금상계 → 정산액 | 부동 막대(신규 렌더러 1개, 단일 축) | settle/daily | v1 |
| S4 | 입금 채널 카드: 계좌이체(은행·예금주·계좌 **뒤 4자리만**) vs 충전금 상계("통장 미기록" 배지) | 소형 표+배지 | settle/daily | v1 |
| S9 | 대사 배너 2줄: ①일별 합계 vs 건별 합계 차이 ②FOMS 완료 매출 vs 정산 매칭액 차이(+"정상 시차" 각주) | 배너 | daily·case·기존 커널 읽기 | v1(①) / v1.1(②) |
| S5 | 건별 정산 원장: 정산예정일 그룹 접기 → 건별 행, 유형 필터·주문번호 검색, 60건 페이저, 행 펼치기(`<details>`)에 원본 스냅샷 전 필드 | 표(`s-dt` 확장) | settle/case (+vat/case 과세 컬럼) | v1 |
| S6 | 수수료 구성: `commissionType` 14종 share bar + 랭킹, 매출연동 상한 미터 | share bar+`renderBarList`+meter | commission-details | v1 |
| S7 | 부가세 기간표: 일자×8금액열, 합계행 sticky, "전월 말일까지 제공" 배너, 과세표준 각주 | 표 | vat/daily | v1 |
| S8 | 예외 큐: 미매칭(PROD_ORDER 행만 매칭 시도)·지급보류·한도보류·음수·소급변경·건수불일치 — "0건"과 "미동기화" 문구 구분 | 표 | daily·case·external_order_links | v1 |
| S10 | CSV 내보내기 4종(건별정산/수수료/부가세일별/부가세건별, 47필드 전량) | 드롭다운(GET) | 5종 | v1.1 |
| S11 | 요약 탭 크로스 스트립 1줄("정산일 기준 · 네이버: 완료 ₩ / 예정 ₩ / 예외 N건 →") | 요약 pane 하단 앵커 1줄, `channel.js`가 렌더 | settle/daily | v1.1 |
| S12~S16 | 결제수단별 수수료 매트릭스·상품별 랭킹·입금 캘린더·부가세 건별 화면·실무 탭 상태 컬럼 | — | — | v1.1 |
| 보류 | 은행 실계좌 자동 대사·회계 프로그램 전표·채널 스위처 실동작 | 각주로 범위 밖 명시 | — | 보류 |

"모든 데이터" 처리: 데이터 카탈로그 47항목 → **적재 100%(JSONB raw_snapshot) · CSV 100%(v1.1) · 화면 즉시 렌더 41항목**, 나머지 6항목(`payMeansType`·`maximumSellingInterlockCommissionAmount`·`contractNo`·`purchaserName`·`productId`·`settlementLimitAmount`)은 S5 행 펼치기에서 원본 노출. 차트 어휘는 기존과 동일(외부 라이브러리·파이·도넛·이중축 금지 — 계약 테스트로 강제됨). ASCII 와이어프레임: `06-ceo-2.md` §B-3.

## 2. 데이터 파이프라인

- **호출**: `client.py`에 public 메서드 5개 append(`_request` 재사용, 새 토큰 경로 금지 — #3751 벌칙 전염 방지). `gncp-gw-quota-limit` 헤더 수신 시 run 즉시 중단·워터마크 미전진.
- **적재 단위**: `(channel, search_date|basis_date, endpoint)` 파티션을 트랜잭션 안에서 **통째 교체**. 교체 전후 diff → 소급 변경 감지 → 예외 큐.
- **테이블 5종(단일 마이그레이션 `naversettle_00`, down_revision=`wizsend_00`, 상수 동결, downgrade 포함)**: `naver_settle_daily`·`naver_settle_case`·`naver_settle_commission`·`naver_vat_daily`·`naver_vat_case`. 공통 컬럼: `channel`(기본 NAVER)·조회축 날짜 `Date`(KST 문자열 그대로, DateTime 승격 금지)·금액 `Numeric`(재계산 금지)·enum 문자열·`raw_snapshot JSONB`·`synced_at`. `naver_settle_case.foms_order_id`는 `productOrderType='PROD_ORDER'` 행만 `external_order_links.external_id`로 매칭. 인덱스: (channel, 축날짜), (product_order_id), 부분 인덱스(미매칭·음수).
- **워터마크**: `SystemSetting` 키 `naver_settle_sync_state` `{rolling_from, rolling_to, per_endpoint, vat_final_month, last_run_at, rev}` — 성공 구간까지만 전진.
- **주기**: `scripts/maintenance/run_naver_settle_sync.py --loop --at 05:30 --window 10`(start.sh `FOMS_NAVER_SETTLE_SYNC_ENABLED=1` 가드, 기본 꺼짐). 일 배치 = settle/daily 1회(오늘−30~오늘+14) + case 30일 + commission 30일 ≈ 72호출/36초(간격 `backfill.py` `CALL_INTERVAL_SECONDS=0.5` 재사용). 부가세 = 익월 10일 1회(전월). 백필 1년 ≈ 766호출/6.4분 — **자동 금지, 야간 수동 enqueue, 30일 창 job으로 분할**(워커 1대 큐 정지 함정).
- **확정본 규칙(자체 정의, 화면에 문구로 노출)**: settle = `settleExpectDate+30일 < 오늘`이면 확정(롤링 제외). VAT = 전월분을 익월 10일 이후 1회 조회한 스냅샷.
- **화면 요청**: `enqueue_naver_settle_sync()`(동기 폴백 금지) → 워커 → DB → web `rev` 폴링(기존 run-state 지문 패턴).

## 3. API

`GET /api/settlement/channel` (신규 blueprint `foms/api/cs/settlement_channel.py`, 권한 = `SETTLEMENT_DASHBOARD_READ` 재사용). params: `channel=NAVER`·`basis=expect|complete|basis|pay`·`from`·`to`·`granularity=day|week|month`·`ledger=case|commission|vat|exceptions`·`page`·`type`·`q`. 응답 `{'success','data':{sync, kpi, daily, waterfall, deposit_channels, reconcile, ledger:{rows,pagination}}, 'error'}`. `POST /api/settlement/channel/sync`(enqueue만, manifest 2종+감사 라벨 등재). 서버가 계좌번호 마스킹·권한 밖 키 제거(클라 숨김 금지).

## 4. 파일 경계 (다른 세션 충돌 회피)

- **신규 파일만(11)**: `foms/services/integrations/naver_commerce/settle_sync.py` · `foms/services/settlement_channel.py`(services 루트 플랫 — SLG 닫힌집합 회피) · `foms/api/cs/settlement_channel.py` · `templates/cs/partials/settlement_channel_body.html` · `static/css/settlement/settlement-channel.css` · `static/js/settlement/channel.js` · `scripts/maintenance/run_naver_settle_sync.py` · `migrations/versions/naversettle_00_channel_settlement.py` · `tests/domains/test_settlement_channel_render.py` · `tests/domains/test_settlement_channel_api.py` · `tests/services/integrations/test_naver_settle_sync.py`
- **기존 파일 소 hunk(9)**: `settlement_dashboard_body.html`(탭 버튼·pane include·link·script 4 hunk, 전부 append) · `test_settlement_dashboard_render.py`(`_TABS` 1행, 3→4 카운트, `_MOCKUP_LEFTOVERS` "예정" 스캔을 기존 3 pane으로 한정) · `client.py`(메서드 5 append) · `queue.py`·`tasks.py`(enqueue/task append) · `foms/api/cs/__init__.py`+`foms/platform/blueprints.py`(등록 2줄) · `start.sh`(가드 블록) · `feature_flags.py`(플래그 1) · `ci.yml`(docs-facing 서브셋 1줄, CRLF 유지)
- **v1에서 열지 않는 파일**: `dashboard.js`·`operations.js`·`settlement-dashboard.css`·`settlement-operations.css`·`settlement_operations_body.html`·`settlement_aggregation.py`·`settlement_rows.py`·`foms/api/cs/settlement.py`·정산 테스트 4종(ops/aggregation/rows/api). 4번째 탭은 `collectEls()` querySelectorAll이 자동 인식, `channel.js`는 `operations.js`의 `watchTabActivation` 패턴 복제로 자가 배선.

## 5. 테스트·검증 완료 기준

1. 신규 계약: 렌더(자산 실재·`?v` 핀·defer·외부 CDN 0·인라인 스타일 0·상태노드 `data-settlement-ch-*` 소유·"정산" 단독 라벨 0·날짜축 라벨 존재) · API(권한 매트릭스=FINANCE·400/403 문구·응답 스키마) · 회계 4종(부호 항등식 Σ=원값·재계산 금지·CHARGE_AMT 분리·VAT 전월 배너) · 파이프라인(멱등 재적재·소급 감지·PROD_ORDER 매칭 가드·페이지 순회·quota 헤더 중단).
2. 기존 정산 5스위트 전량 green + 마이그레이션 왕복 + 단일 head + 인벤토리/네임스페이스 계약 + CI-DOCSCOPE-01 등재 + `pre_push_smoke` exit 0(정산 스위트는 smoke 밖이라 별도 실행) + `gh run list` 전 워크플로 green.
3. 실서버: T0 재검증(5종 200) → 스테이징 적재 1회 → 스마트스토어센터 정산내역 화면과 숫자 3개(정산액·수수료합·건수) 대조 → 워터마크 rev 전진 → 화면 QA(gstack browse).

## 6. Task 표 (v1, 각 task 완료 기준 = 원장에 기록)

| T | 내용 | 완료 기준 |
|---|---|---|
| T0 | 스테이징 워커 정산 5종 읽기 실측(토큰 만료 후 재시도) | 5종 200 + 페이지·폭 확인. **실패 시 사용자에게 앱 권한 확인 요청** |
| T1 | `client.py` 정산 메서드 5개 | FakeTransport 단위 테스트 green, EXT-TOKEN 계약 유지 |
| T2 | 마이그레이션 5테이블 | upgrade→downgrade→upgrade 왕복 + 단일 head |
| T3 | `settle_sync.py` 적재(파티션 교체·소급 감지·매칭 가드) | 픽스처 재적재 유령 행 0 |
| T4 | 워터마크·enqueue·task·스크립트·start.sh·플래그 | `--once --dry-run` 모의 exit 0, 동기 폴백 없음 |
| T5 | `settlement_channel.py` 조회 커널 | 스키마 계약 + 회계 4종 green |
| T6 | `/api/settlement/channel` (+sync POST manifest 등재) | 권한 매트릭스·400/403·감사 라벨 |
| T7 | **파일럿** 탭 등록 4 hunk + 파셜 뼈대 + 기존 계약 3종 갱신 | 정산 5스위트 전량 green |
| T8 | CSS + `channel.js`(KPI·차트·워터폴·원장·예외) | 렌더 계약 green, 숨은 pane 폭 0 재렌더 확인 |
| T9 | 신규 테스트 3파일 마감 | `pytest tests/domains/test_settlement_*.py tests/services/integrations/test_naver_settle_sync.py` green |
| T10 | ci.yml 등재 + 게이트 전수 + push(deploy) | 전 워크플로 green |
| T11 | 스테이징 실적재·화면 검증·숫자 대조 | §5-3 |
| v1.1 | T12 요약 스트립 · T13 실무 탭 컬럼(`_GRID_HEADERS` 12칸) · T14 CSV 4종 | 별도 승인 |

## 7. 미결(사용자 결정)
1. 탭 라벨 "채널 정산"(힌트 네이버) vs "네이버 정산".
2. 초기 백필 범위: 최근 3개월 / 1년(권장, 부가세 신고 2기 커버).
3. 열람 범위: 기존 정산 대시보드와 동일(ADMIN·MANAGER·STAFF CS/SALES) vs ADMIN·MANAGER만(계좌·구매자명 포함 근거).
4. T0 403: FOMS가 쓰는 앱(client_id `4RYv…`)에 [정산] 그룹이 있는지 확인. (기존 실무 탭 "정산상태"→"차감청구" 개명은 타 세션 파일이라 v1.1로 미룸.)
