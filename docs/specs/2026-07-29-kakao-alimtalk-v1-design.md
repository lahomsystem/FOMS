# 카카오 알림톡 고객 발송 v1 — 확정 설계 (v2)

> 상태: REVIEWED — CEO 리뷰(HOLD SCOPE) + 3-agent 교차검수(반증·단순화·사실검증) finding 전량 반영. 사용자 승인 대기.
> v1(2026-07-29 초안) 대비 주요 변경: 신규 테이블·RQ task 폐기(기존 인프라 재사용), diff 트리거 폐기(발송 자격 판정), 버튼 타입 WL 확정, failover 전제 정정.
> 근거: deep-research(104 에이전트) + 코드 recon 2회 + 반증 리뷰(H1~H6·M1~M4·L1~L5) + 단순화 리뷰(F1~F8) + 사실검증(7항목). 주요 주장 오케스트레이터 직접 재검증 완료.

## 1. 목표·범위

FOMS 주문에서 고객에게 카카오 알림톡을 자동/수동 발송한다. v1 = **실측 예약 안내 템플릿 1종**, PC·모바일·태블릿 3표면.

## 2. 확정 결정 (사용자)

| # | 결정 | 내용 |
|---|---|---|
| D0 | 접근안 | A안 — 채널톡 전송 파이프라인과 독립된 얇은 알림톡 계층 |
| D1 | 리뷰 모드 | HOLD SCOPE — v1 범위 고정, 확장은 백로그만 |
| 트리거 | 자동+수동 | 실측일·시간 확정 시 자동 + 주문 상세 수동 버튼 |
| 재발송 | 자동 | 실측일/시간 변경 시 자동 재발송 (멱등키에 일정값 포함) |
| D2 | 수동 재발송 | 자동만 멱등키 차단. 수동은 기존 발송 이력 확인 모달 후 허용 |
| 버튼 | WL 확정 | "문의하기" 웹링크 → 채널 1:1 채팅 URL (§5). 상담톡(BC)은 별도 계약+기존 1:1 채팅 상실이라 기각 |

## 3. 외부 전제 (사실검증 정정판)

- 알림톡 = 정보성 메시지, 채널 미추가 고객에게 전화번호로 도달. 공식 딜러사/리셀러 경유 필수(직접 API 없음). 실측 예약 안내 = "계약이행 정보"로 요건 부합. 홍보 문구 한 줄 혼재 시 전체 광고 판정 → 발송 불가.
- 업체 = Solapi. 알림톡 13원 < SMS 18원 < LMS 45원 (VAT별도, 2026-07 확인). 공식 Python SDK `solapi` 5.0.3 (2026-01, Python≥3.9).
- **SMS/LMS 대체발송(failover)은 기본 활성** (`kakaoOptions.disableSms` 기본 false). 실전제 = **`from`에 사전 등록 발신번호 필수** — 누락 시 대체발송 없이 조용히 실패. 콘솔 설정 아님, API 파라미터. (v1 초안의 "명시 설정 필요·콘솔 위임"은 오류 — 정정)
- 템플릿: 카카오 심사 통과본만 발송 가능. SLA 영업일 2일, **최악 10영업일**(딜러사 가이드), 반려 시 재심사. **등록 완료 후 수정 불가** — 반려/변경 = 새 템플릿 + 재심사 사이클. 변수 최대 40개, **모든 변수에 예시 텍스트 첨부 필수**(미첨부 = 반려 확정), 변수만으로 구성 불가, 버튼명 변수 금지.
- 변수에 개행 허용(Solapi 공식 확인) — 멀티라인 `#{품목내역}` 기술적 가능. 심사 통과는 §8 리스크.
- 본문 한/영 1,000자 — **변수 치환 후 총 길이 기준**, 초과 시 발송 실패.
- 야간 발송 제한(정보통신망법 §50③)은 **21:00~08:00, 광고성 한정** — 정보성 알림톡 **미적용 확정**. 야간 보류 큐 제외(§7)는 법적으로 안전. (초안의 "20:50~" 시간대·"미확정" 표기는 오류 — 정정)
- 정보성 메시지는 광고 수신동의 불요. 단 고객 전화·주소가 Solapi(제3자)로 전달 = **개인정보 처리위탁** — 개인정보처리방침에 수탁사 명시 필요(§4 체크리스트).

## 4. 사전 체크리스트 (사용자 액션 — 코드 착수와 병행, 순서 의존)

1. **카카오톡 채널 설정 확인**: 비즈니스 채널 인증(완료) + **홈 공개 ON** + **고객센터 정보(전화/URL) 입력** — 이 둘이 없으면 발신프로필 키(pfId) 발급 자체 불가. + 1:1 채팅 ON 유지(WL 버튼 목적지).
2. Solapi 가입 → 카카오 채널 연동 → **발신프로필 등록**.
3. **SMS 발신번호 등록** (failover 전제 — 통신사 서류 절차).
4. §5 템플릿 제출: 변수별 예시 텍스트 첨부(품목내역 = 실제 다품목 블록 예시). 심사 2~10영업일.
5. 개인정보처리방침에 수탁사(Solapi/카카오) 추가.
6. API 키 발급 → Railway env 등록 (§6.6).

## 5. 템플릿 (심사 제출 확정본 — 제출 후 수정 불가이므로 여기서 동결)

```
안녕하세요 #{고객명} 고객님, 실측 예약이 정상적으로 완료되었습니다.
일정 변경이 있을 경우 아래 문의하기 버튼으로 미리 연락 부탁드립니다.

실측일 : #{실측일}
시  간 : #{실측시간}

고객명 : #{고객명}
발주사 : #{발주사}
시공일 : #{시공일}
주  소 : #{주소}
연락처 : #{연락처}

#{품목내역}

예약금(선금) : #{예약금}
```

- 버튼: **WL(웹링크)** 1개, 버튼명 `문의하기`, linkMo=linkPc=`http://pf.kakao.com/_{채널ID}/chat` (카카오 개발자 문서 명시 1:1 채팅 URL). 심사 반려 시 폴백 = 대표번호 안내 문구(§8).
- 변수 9종. `#{품목내역}` = 품목별 블록(제품명/내 부/색 상/옵 션/손잡이/기 타) 멀티라인, 개행 포함.
- **이 산출물은 서버 포맷터 신규 생성물** — 기존 변환 텍스트(`erpGenerateConversionText`, 클라 DOM 리더)와 별개다. 빈값은 변환 텍스트처럼 라인 생략이 아니라 **"상담" 폴백**(알림톡 변수는 비울 수 없음, 사용자 문안 의도). 예약금만 예외 — 없으면 **"없음"**(2026-08-11 사용자: "예약금은 없을 경우도 있어").
- **담당자 줄 제외 확정** (2026-08-11 사용자: "최초 발송 시 담당자는 정해져 있지 않아" — 항상 '미정'만 찍힐 줄이라 템플릿에서 뺀다).
- 치환 후 1,000자 **하드 가드**: 변수 빌더가 렌더 길이 계산, 초과 시 품목내역을 "첫 품목 + 외 N건"으로 축약. 경계 pytest 필수.

## 6. 아키텍처 v2

기각: 신규 테이블+Alembic(F1), RQ task(F5), 이력 뱃지 컴포넌트(F6), diff 트리거(H1), `FOMS_ALIMTALK_ENABLED` 전역 플래그(F3 — 자동발송 전용 플래그로 축소).

### 6.1 영속화 — 기존 인프라 3종 재사용 (채널톡 `_record_push_metadata` 선례)
- **멱등**: `domain_side_effect_outbox` 행 insert — `effect_type='ALIMTALK_SEND'`, partial UNIQUE `(effect_type, dedupe_key)`가 DB 제약으로 중복 차단. `provider_idempotency_key`로 벤더 멱등 전달.
- **멱등키(자동)**: `alimtalk:measure:{order_id}:{dates}:{time}` (T1 구현 기준 정정 — 수동 키와 접두어 일관) — dates = `_normalize_date_str` 적용·정렬·중복제거한 날짜 리스트(콤마 다중일자 지원, [order_date_sync.py:60-77](../../foms/services/order_date_sync.py) 규약), time = strip. 수동 발송 키 = `...:manual:{uuid4}` (항상 신규 — D2, 중복 방지는 서버 렌더 확인 모달이 담당).
- **이력**: `structured_data['alimtalk_measurement']` 키(sent_at/message_id/dedupe/실패 사유) + `OrderEvent(event_type='ALIMTALK_SENT'|'ALIMTALK_FAILED')` — 타임라인 자동 표시([order_event_display.py](../../foms/services/order_event_display.py) 라벨 맵 1줄 추가).
- **삽입 위치(M2)**: 주문 저장 tx **커밋 후** 별도 tx (geocode enqueue 자리 선례, [erp_orders_structured.py:953-954](../../foms/api/erp_orders_structured.py)). `IntegrityError` = 정상 중복으로 흡수(로그), 그 외 예외 = 로그+표면화. 주문 저장 절대 비차단.
- 타임스탬프 = `now_utc_naive` (프로젝트 규약. 주변 일부 레거시 naive-local 혼재 인지 — 신규 기록은 UTC 고정).

### 6.2 발송 계층 — `foms/services/kakao_alimtalk.py` 1파일
- **자격 판정** `is_eligible(order, sd)`: 실측 date 정규화값 존재 + **draft 주문 아님** + (자동일 때) 멱등키 미존재. **diff 비교 안 씀** — draft autosave가 old_sd를 선점하는 H1 함정 원천 회피.
- **변수 빌더** `build_variables(sd)`: 서버 Python 포맷터 신규 —
  - 날짜 한글화 `YYYY-MM-DD`→`M월 D일`, 다중일자 `8월 14일, 8월 15일` 병기
  - 시공일 = `schedule.construction.date` 비면 `'상담'` (M3 — status 분기 불가, 폼 저장본에 status 없음)
  - 예약금 = `erp_deposit_amount_from_structured(sd)` SSOT 헬퍼 (H4 — `payment` 단수 우선, int) → `"100,000원"` 포맷
  - 발주사 비면 `'라홈'`, 기타 빈값 `'상담'`
  - 1,000자 하드 가드(§5)
- **전화 검증(M4)**: 숫자만 추출 → 10~11자리·`01` 시작 검증. 다중번호(`/` 구분 등)는 **첫 번째 유효 번호** 사용(무효 토큰 건너뜀 — T1 테스트 고정), 이력에 명시. 실패 = 발송 스킵 + `ALIMTALK_FAILED(no_valid_phone)` 이력.
- **Solapi 호출**: 공식 SDK 채택(HMAC 서명 직접 구현 리스크 > 핀 1건 관리 비용 — requirements.txt 추가 명시). `KakaoOption(pf_id, template_id, variables={"#{이름}": 값})` + **`from_`=등록 발신번호 필수**(failover 활성 전제). `disableSms` 기본값 유지(대체발송 on). `text` 파라미터는 스테이징 실계정 확인 전 미사용(§8).
- **오류 분류** → 이력 error 코드: `auth`/`balance`(잔액 부족)/`template_mismatch`(변수 불일치)/`invalid_phone`/`length_exceeded`/`network`. bare except 금지, 실패는 전부 이력+구조화 로그.

### 6.3 자동 트리거 — 쓰기 경로 3개 공통 배선 (H2)
| 경로 | 파일 |
|---|---|
| `PUT /orders/<id>/structured` | [erp_orders_structured.py:703](../../foms/api/erp_orders_structured.py) |
| `PATCH /orders/<id>/structured/fields` (인라인) | 같은 파일 :602 |
| `PUT /api/orders/<id>` 빠른수정 `measurement_date` | [field_update.py:443-447](../../foms/api/orders/field_update.py) |

각 경로 커밋 후 공통 헬퍼 `maybe_send_measure_alimtalk(order_id)` 호출 (자격 판정 → outbox insert → 발송). draft autosave 경로는 배선 제외(draft = 미자격). `_record_structured_events`의 measurement **time 비교 추가**는 이벤트 정확성 개선으로 동반(현재 date만 비교).
- 발송 실행: **T0에서 Railway sidefx DELIVERY worker 가동 확인** — 가동이면 handler 등록([run_domain_side_effect_outbox.py:192](../../tools/ops/run_domain_side_effect_outbox.py) 선례) 후 worker 소비. **미가동이면** outbox 행은 dedupe 전용 insert + 커밋 직후 동기 발송(수동 선례 [channel_integration.py:371-390](../../foms/api/channel/channel_integration.py)) + 성공 시 DONE 마킹 — worker가 나중에 붙으면 재시도 경로로 자연 승격.
- 자동발송 킬스위치: `FOMS_ALIMTALK_AUTO_ENABLED` (기본 off → 스테이징 검증 → 운영 on). 수동 발송은 자격증명 존재 게이트(`is_configured()` 선례, [channel_client.py:68-70](../../foms/services/channel_client.py)).

### 6.4 수동 발송 API
- `GET /api/kakao/alimtalk/preview/<order_id>` — **서버가 저장본 sd로 렌더**한 치환 결과 반환. 클라 텍스트 불신(F2 — push-manual의 클라 text 수신 패턴 복사 금지).
- `POST /api/kakao/alimtalk/send-manual/<order_id>` — `{success,data,error}` 규약, CSRF 토큰, 권한 = `role_required(['ADMIN','MANAGER','STAFF'])` (push-manual 선례, L3). 발송자 user_id를 이력에 기록(감사).
- **manifest 등재 필수(M1·F3)**: `docs/harness/foms_write_guard_manifest.json` + `foms_order_mutation_policy_manifest.json`(`STAFF_MUTATION`) — 미등재 = CI red (최근 사고 2건 선례).
- **dirty 가드(F2)**: `window.fomsErpAutosave.isDirty()` true면 발송 버튼 비활성 + "저장 후 발송" 안내 (미리보기=저장본 기준 불일치 방지).
- 기존 발송 있으면 모달에 이력 표시 + 재발송 확인(D2).

### 6.5 UI — 3벌 각각 배선 (H5 — "자동 커버" 아님)
| 표면 | 위치 |
|---|---|
| PC | [erp_order_tab.html:413-421](../../templates/orders/partials/erp_order_tab.html) 채널톡 버튼 옆 |
| 모바일 | [erp_order_tab_mobile.html:441-446](../../templates/orders/partials/erp_order_tab_mobile.html) sticky footer |
| 태블릿 | [tablet-measure-form.js:1136-1141](../../static/js/foms/tablet-measure-form.js) JS 생성 섹션 |

- 미리보기 모달 = [erp_channel_push_resend_modal.html](../../templates/orders/partials/erp_channel_push_resend_modal.html)(25줄, PC modal/모바일 sheet 겸용) 본떠 read-only 본문 partial 1개 + [erp-channel-push-confirm.js](../../static/js/orders/erp-channel-push-confirm.js) 싱글톤·버튼 잠금 패턴 재사용(G4 idempotent 규약).
- 이력 표시 = 버튼 옆 텍스트 한 줄(마지막 발송 시각/실패 사유) + OrderEvent 타임라인. 뱃지 컴포넌트 없음(F6).
- 기존 JS 수정 파일은 `?v=` 범프 + 핀 전수 grep (SW staticCacheFirst 규약).

### 6.6 env (Railway, FOMS-DEV/PRODUCTION 각각)
`SOLAPI_API_KEY` / `SOLAPI_API_SECRET` / `SOLAPI_PF_ID` / `SOLAPI_TEMPLATE_MEASURE_ID` / `SOLAPI_SENDER_PHONE`(등록 발신번호 — failover 전제) / `FOMS_ALIMTALK_AUTO_ENABLED`

### 6.7 오류 지도 (요약)
| 경로 | 실패 | 처리 | 사용자/이력 |
|---|---|---|---|
| 자격 판정 | 전화 없음/불량 | 스킵 | FAILED(no_valid_phone) 이력 |
| outbox insert | dedupe 충돌 | IntegrityError 흡수 | 정상(중복 차단) 로그 |
| outbox insert | 그 외 DB 오류 | 로그+표면화 | 주문 저장은 무영향(별도 tx) |
| Solapi 호출 | 인증/잔액/템플릿 불일치/번호 불량 | 오류 코드 분류 저장 | FAILED(코드) 이력+한 줄 표시 |
| Solapi 호출 | 네트워크/타임아웃 | worker 경로면 backoff 재시도, 동기 경로면 FAILED | FAILED(network) |
| 알림톡 도달 실패 | 채널 차단 등 | 벤더 failover → SMS/LMS 자동 | 벤더 측 처리 |
| 치환 후 1,000자 초과 | — | 사전 하드 가드로 축약(발송 전) | 발생 불가 설계 |
- 잔액 소진 경보 = Solapi 콘솔 알림 설정 위임(코드 0, §4 체크리스트에 설정 항목 추가).
- Runbook 한 줄: FAILED 급증 시 Solapi 콘솔(잔액·발신프로필 상태) → env 키 → 템플릿 상태 순 확인.

### 6.8 검증
- pytest: 변수 빌더(한글 날짜·다중일자·상담 폴백·예약금 포맷·1,000자 경계 축약), 멱등키 canonicalize(공백·콤마 순서 변형 동일키), 자격 판정(draft 제외·전화 불량), 수동 API 권한/CSRF/manifest 계약, OrderEvent 라벨.
- 스테이징: `FOMS_ALIMTALK_AUTO_ENABLED=on` + **직원 본인 번호**로 E2E (자동 최초/변경 재발송/중복 차단/수동 재발송/failover, `text` 파라미터 거동 확인). 고객 실번호 금지.
- `import app` APP_OK + pre_push_smoke + 계약 테스트(manifest 2종).

## 7. v1 제외 (YAGNI — 백로그)
**계약서 발송 템플릿**(WL 버튼 링크 방식 — 파일 첨부 불가 확인, FOMS 고객용 서명 토큰 열람 페이지 신설 필요) / **도면 발송 템플릿**(동일 — 이미지 알림톡은 템플릿 고정 이미지 1장뿐이라 주문별 도면 직접 발송 불가, 링크 방식) / 타 단계 템플릿 / 야간 보류 큐(법적 불요 확정) / 발송 통계 대시보드 / 광고성(브랜드메시지 100원) / 이력 뱃지 컴포넌트 / 발주사별 발신프로필 분리(하우드 등) / 변환 텍스트-알림톡 포맷터 통합(JS 사본 2벌 존재 — 3벌째 금지 원칙만 유지).

## 8. 리스크·불확정 (스테이징/심사에서 해소)
1. **WL 채팅 URL 심사**: `pf.kakao.com/_{id}/chat` 웹링크 승인 명시 규정 미발견(금지 조항도 없음). 반려 시 폴백 = 대표번호 안내 문구로 템플릿 재제출.
2. **품목내역 멀티라인 심사**: 기술 지원 확인, 심사 관행 불확정. 반려 시 폴백 = "첫 품목 + 외 N건" 요약형 재제출.
3. **Solapi `text` 파라미터 상충**: API 문서(대체발송 콘텐츠) vs SDK 예제 경고(기입 시 발송 실패) — 스테이징 실계정 확인 전 미사용.
4. **sidefx worker 가동 여부**: T0 확인. 미가동 = §6.3 동기 폴백 경로 채택.
5. 발신프로필 심사 소요 일수 1차 출처 없음(비공식 1~3영업일) — §4를 코드와 병행해 리드타임 흡수.
