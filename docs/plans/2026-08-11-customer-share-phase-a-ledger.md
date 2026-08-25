# 고객 공유 채널 Phase A — Progress Ledger

> 플랜: `docs/plans/2026-08-11-customer-share-phase-a-plan.md` / 스펙: `docs/specs/2026-08-11-customer-share-phase-a-design.md` (v3)
> 상태값: PENDING / IN_PROGRESS / DONE / BLOCKED(사유 원문 필수)
> 갱신 규칙: task 완료 = 검증 명령 exit 0 + 커밋 SHA 기록 후 DONE. compaction 후 재개 시 이 파일이 정본.
> 작업 트리: `c:/tmp/foms-alimtalk-reapply` (브랜치 `alimtalk-reapply`)

## Stage-1 — 도면 공유

| Task | 내용 | 완료 기준 | 상태 | 커밋 SHA | 비고 |
|---|---|---|---|---|---|
| T1 | 토큰 모델·마이그레이션·서비스 코어 (파일럿) | `pytest tests/domains/test_order_share_service.py tests/domains/test_alembic_single_head.py -q` PASS + APP_OK | DONE | 073b89b3 | 14 passed. head=seclog_time_00 뒤 단일 연결. 지문 정합 위해 양쪽 server_default 無, snapshot=JSON+JSONB variant |
| T2 | 비로그인 열람 `GET /s/<token>` (drawing) | `pytest tests/domains/test_order_share_view.py -q` PASS(격리·410·fail-closed 503 표면·헤더·FILE_VIEW 1행) + APP_OK | DONE | 84319e30 | 12 passed + namespace 게이트 358 passed. presign 전멸=503, onerror 새로고침 안내 |
| T3 | 직원 API create/revoke + manifest·감사 | `pytest tests/domains/test_order_share_api.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py -q` PASS + audit 인벤토리 재생성 + APP_OK | DONE | 93b0e142 | 49 passed + audit 게이트 11 passed(coverage 100%). 감사에 토큰·URL 미격납 assert |
| T4 | 공유 UI 모달 (PC·모바일) + list API | 계약 테스트 PASS + browse 2뷰포트 스모크(모달·복사·목록) + APP_OK | DONE | bef517a5 | 110 passed(계약+게이트). browse 스모크는 T5 통합 실행(알림톡 T5 선례). 카톡 키=지도 앱 키 fallback+env 오버라이드 |
| T5 | Stage-1 통합 검증·스테이징 배포 | pre_push_smoke exit 0 + `gh run list` 전 워크플로 green + E2E 기록 | DONE | 1f7999e4 | smoke 0·CI 4/4 green(Harness/PG Lane/perf-gate/FOMS). E2E 13항목 PASS: 로그인→발급→시크릿 열람 200+헤더 2종→열람수 반영→revoke 410→불량토큰 404→estimate 400. 주문 4287 카드·presigned·lightbox 렌더 확인. **주의**: 스테이징 이미지 실바이트는 전 키 NoSuchKey — 스테이징 DB(운영 복제)↔R2 버킷 드리프트(환경 이슈, presign 서명·경로 정상, onerror 안내 표면화). 실객체 검증=T10 업로드 흐름 동반. 카톡 실공유=**BLOCKED**(카카오 도메인 등록 사용자 액션 대기) |

## Stage-2 — 견적서·문자·태블릿

| Task | 내용 | 완료 기준 | 상태 | 커밋 SHA | 비고 |
|---|---|---|---|---|---|
| T6 | 견적 스냅샷 빌더 (화이트리스트+동결+64KB 캡) | `pytest tests/domains/test_order_share_estimate.py -q` PASS(타 브랜드 계좌 부재·불변·400) + APP_OK | DONE | c871807e | 8+14 passed. 브랜드 교차 계좌 유출 0·내부 키 차단·grand total 공식·동결·캡 400 전부 assert |
| T7 | 견적 열람 렌더 + kind UI 해금 | view 테스트 PASS + browse 모바일 렌더(옵션 해금·64KB 400 표시) + APP_OK | DONE | db6f23af | 27 passed. 스냅샷-온리 렌더(수정 미반영 assert)·스냅샷 부재 503·카톡 문구 kind 분기·?v 20260812a 범프+핀 전수. browse는 T10 통합 |
| T8 | 문자 발송 (sender_phone·_solapi_send_text·멱등·버튼 배선) | `pytest tests/domains/test_order_share_sms.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py -q` PASS + audit 인벤토리 재생성 + APP_OK | DONE | 6fd32f3c | 64 passed(게이트 포함)·coverage 100%. 선점 insert 멱등=벤더 호출 1회 assert, 감사=수신번호 마스킹·토큰 미격납, 발신 폴백 2분기, senderphone_00 마이그레이션 |
| T9 | 태블릿 공유 버튼 (tablet-measure-form.js) | 태블릿 계약 테스트 PASS + browse coarse 스모크 + APP_OK | DONE | cb9feef1 | 117 passed. 발급→URL 복사→(선택) 문자 confirm 흐름, ?v 20260812a 범프. browse coarse는 T10 통합 |
| T8.1 | 발신번호 3단 우선순위(담당자→브랜드 대표→구 폴백)+②실패 시 브랜드 백업 1회 재시도 | `pytest tests/domains/test_order_share_sms.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py tests/domains/test_audit_action_coverage.py tests/domains/test_audit_coverage_inventory.py -q` PASS + APP_OK + CI 전 워크플로 green | DONE | ad6dd47e | 17+63 passed. 구 규칙(버튼 누른 직원) 폐기, resolve_brand SSOT 재사용, 멱등 앵커 1개 유지·payload attempts 2회 기록(마스킹), 감사 sender_source 기록 |
| T10 | Stage-2 통합 검증·스테이징 E2E | pre_push_smoke exit 0 + CI green + E2E(스냅샷 불변·문자 3사·카톡 실기기) | DONE | 59e12874 | smoke 0·CI 4/4 green. E2E 12항목 PASS(주문 4389): 견적 발급→비로그인 열람(계좌·출고가·잔금 렌더·헤더 2종·내부 키 부재)→revoke 410, send-sms 503 not_configured 표면(스테이징 Solapi env 無 — 정상 fail-visible)·토큰 불일치 400. 스냅샷 동결은 pytest 5건이 정본 검증. **BLOCKED 2건**: 문자 3사 실수신(Solapi 발신번호 등록 대기)·도면 이미지 실객체(스테이징 R2 드리프트, T5 참조). 카톡: 도메인 등록 후 스테이징 검증 PASS(2026-08-13 — 버튼 활성·SDK init 성공·콘솔 에러 0·SDK 200, 주문 4389 발급→회수 정리), 실기기 전송만 사용자 확인 잔여 |

## 외부 준비 (사용자 액션)

### 문자 발신번호 확정 (사용자 결정 2026-08-12 — T8.1 발신 규칙의 정본)
- 발신 우선순위: ① 주문 담당자의 등록 개인번호(`users.sender_phone`, 담당자 기준 — 발송 버튼 누른 사람 아님) ② 브랜드 대표번호 ③ ② 벤더 실패 시 브랜드별 백업번호로 같은 요청 내 1회 재시도
- 하우드: 대표 `15660703` / 백업 `01044644260` → env `SOLAPI_SENDER_PHONE_HAUD` / `SOLAPI_SENDER_FALLBACK_HAUD`
- 라홈: 대표 `15660792` / 백업 `01083277282` → env `SOLAPI_SENDER_PHONE_LAHOM` / `SOLAPI_SENDER_FALLBACK_LAHOM`
- 영업 개인번호는 각자 Solapi 등록 후 /admin/users "문자 발신번호"에 입력. 위 4개 번호도 전부 Solapi 발신번호 등록 필요(법인 서류). 구 `SOLAPI_SENDER_PHONE`은 최후 폴백으로 유지.
- [x] Railway env 등록 완료 (2026-08-12, `--skip-deploys` — 다음 배포 때 적용): 스테이징=FOMS-DEV/서비스 `FOMS`, 운영=FOMS-PRODUCTION/서비스 `web`, 각 6종(발신 4 + 회전된 `SOLAPI_API_KEY`/`SECRET`). 로컬 .env도 새 키로 갱신됨. env 잔여 없음 — 실발송 검증 잔여는 Solapi 발신번호 등록(대표2·백업2·개인)과 카카오 도메인 등록뿐.
- [x] 카카오 개발자 앱 도메인 등록 완료 (2026-08-12 사용자) — 카톡 공유 검증 가능
- [x] Solapi 발신번호 등록 (2026-08-13 사용자 확인): 대표 2(`15660703`·`15660792`)·백업 2(`01044644260`·`01083277282`) **전부 활성** (라홈 백업은 반려 후 당일 재승인).
- [x] **문자 실발송 검증 완료** (2026-08-13): 1차 시도는 Solapi API 키 IP 허용 목록이 스테이징 IP(208.77.246.107) 403 차단 — 이때 `brand → brand_fallback` 재시도 로그로 T8.1 ③ 배선 실전 작동 실증. 사용자가 IP 제한 해제(모든 IP 허용) 후 재시도: **2통 발송 성공** — 주문 4404(발주사 無 → HAUD `sent:true, sender_source:brand`)·주문 4405(발주사 라홈 → LAHOM 분기 `sent:true`), 수신 010-8327-7282. 잔여물 정리 완료(share 20~22 회수·주문 4403~4405 soft delete). **수신 확인 완료(2026-08-13 사용자)**: 2통 수신 + 발신번호 1566-0703·1566-0792 육안 일치 — 브랜드 분기 종단 검증 종결. **잔여**: Solapi IP 허용 목록 원복(현재 모든 IP 허용 — 운영 static IP 3개 등록으로 재잠금 권장, 사용자).
- [x] 실측 예약 알림톡 템플릿 2건 **APPROVED** (2026-08-13 카카오 검수 승인 — 라홈 `KA01TP260811082027608jiKgfLV0q0O`·하우드 `KA01TP260811075557060ljaBmPYcckr`). 알림톡 v1 가동 잔여 = PF/템플릿 env 등록 + `FOMS_ALIMTALK_AUTO_ENABLED` 결정.
- [~] **공유 링크 알림톡 템플릿 2건 심사 제출** (2026-08-13 Solapi API로 등록·INSPECTING — 라홈 `KA01TP260813084939252sAF8ck1asOu`·하우드 `KA01TP260813084949809PEw5FMEvNmR`, 카테고리 005003 계약/견적): 변수 고객명·문서종류·유효기간·담당자·담당자연락처·토큰, WL 버튼 `https://lahom-production.up.railway.app/s/#{토큰}` + 상담톡 BC. 채널별 고정 인사말(라홈/하우드입니다)로 브랜드 분기(코드는 resolve_brand로 채널 선택). **승인 후 잔여**: 공유 모달 알림톡 발송 배선 — 반나절. **폴백 규칙(사용자 결정 2026-08-13)**: 알림톡 발송 실패 시 SMS 폴백은 기존 send-sms 경로(T8.1 발신 3단 — ①담당자 sender_phone → ②브랜드 대표 → ③백업) 재사용 = 담당자 지정 시 담당자 번호 발신. 영업 개인번호 Solapi 등록 전까지는 ①이 항상 스킵돼 브랜드 대표로 나감(등록 즉시 자동 전환, 코드 무변경). 템플릿 변수 담당자/연락처 폴백 = "고객센터"/브랜드 대표번호.
- [x] 공유 열람 고객 다운로드 (2026-08-13, `120ce5ca`): 도면 전 파일 attachment presign '내려받기' 섹션(한글 파일명 RFC 5987) + 견적서(계약서) 저장·인쇄(PDF) 버튼. 테스트 16 passed. **운영 승격 완료** — PR #91 머지, production `cee28d4e` (perf-gate·pg-lane pass).
- [x] 공유 링크 알림톡 템플릿 2건 **APPROVED** (2026-08-18 감시 포착 — 심사 5일). 감시 종료.
- [x] **T11 공유 알림톡 발송 배선** (2026-08-18, `28ebc429`): `POST /api/share/send-alimtalk/<id>` — 브랜드별 PF/템플릿 env(`SOLAPI_PF_ID_*`·`SOLAPI_TEMPLATE_SHARE_ID_*`, 스테이징·운영·로컬 .env 등록 완료 `--skip-deploys`)·발신 T8.1 3단(알림톡 실패 시 Solapi failover 가 그 번호로 SMS 대체발송 = 담당자 번호 요구 충족)·변수 6종(담당자 폴백 고객센터/브랜드 대표)·선점 멱등 `share_alimtalk` 버킷·감사 SHARE_ALIMTALK_SENT·manifest 2종·audit 인벤토리 184 재생성·모달 알림톡 버튼(erp-share.js ?v=20260818a). 테스트 10+17+63 passed. **스테이징 검증 완료(2026-08-19)**: Railway 장애(빌드 3연속 실패) 회복 후 감시 포착 → 주문 4471·share 24 로 알림톡 버튼 실발송 — 감사 `sent:true, error:null, sender_source:brand`(HAUD 채널), 수신 010-8327-7282. 잔여물 정리 완료(회수·soft delete·로그아웃). 실수신·문자 대체발송 육안 확인 = 사용자. 운영 승격 대기(T11 커밋 + env는 운영 등록 완료 — 다음 승격 배포 시 적용). **실수신 확인 완료(08-19 사용자)**.
- [x] **T12 알림톡 통합 드롭다운** (2026-08-19): '알림톡' 버튼 하나로 예약 내역(실측 미리보기 모달 재사용)·도면·계약서(견적서) 3항목 — 도면/계약서는 confirm 후 자동 발급+발송(기존 API 연쇄, 신규 라우트 없음). PC·모바일 2표면, erp-share.js ?v=20260819b. UI 계약 76 passed·smoke 0. **스테이징 검증 완료**: 주문 4475 드롭다운 3항목 렌더 + 도면 원클릭 발송 — Solapi 벤더 로그 `COMPLETE·수신 완료`, to=01083277287(사용자 지정), 하우드 채널·변수 정상. 잔여물 정리(share 25 회수·주문 soft delete·로그아웃). 잔여=**운영 승격**(T11+T12 커밋). **운영 승격 완료(2026-08-19)** — PR #115 머지, production `01ef5862`, 체크 perf-gate·pg-lane pass, 운영 라이브 확인(?v=20260819b JS 서빙 + /s/ 404·noindex·no-referrer 스모크). 충돌 해소: manifest=production 기반+신규 라우트 삽입·erp_order_js.html=production 줄 유지+erp-share 핀만 범프·인벤토리 재생성(509·178 100%). Phase A 전 기능 운영 반영 종결.
- [x] **실측 알림톡 '서버 미설정' 해소** (2026-08-19 사용자 보고): 원인 = `SOLAPI_TEMPLATE_MEASURE_ID_LAHOM/HAUD` + 구 `SOLAPI_SENDER_PHONE` env 미등록(`is_configured()` false). 승인된 실측 템플릿 ID 2종 + `SOLAPI_SENDER_PHONE=15660703` 를 스테이징·운영·로컬에 등록(재배포 트리거로 즉시 적용). **주의**: 자동발송 killswitch(`FOMS_ALIMTALK_AUTO_ENABLED`)는 여전히 off — 수동 버튼만 활성. 실측 알림톡 SMS failover 발신은 15660703 단일(브랜드 분기 안 됨 — v1 `_dispatch` 한계, 후속 개선 후보: `SOLAPI_SENDER_PHONE_{brand}` 분기). **사용자 결정(2026-08-19): 브랜드 분기 확정 — 라홈=1566-0792·하우드=1566-0703 (T14로 구현).**
- [x] **T13 미저장 입력 자동 저장 후 발송** (2026-08-19, `d83854c2`): 알림톡 버튼 클릭 시 dirty 감지 → 기존 통합 저장(`erpSaveStructured({redirect:false})`) 실행 후 preview 조회 — 저장본 SSOT 유지(화면값 직접 조립 배제). 저장 실패 시 발송 중단+문구 표면화, draft 백업 주문은 클릭만으로 승격되지 않게 저장 스킵(draft 부활 레이스 회피). 공유 링크 발급·원클릭 알림톡도 같은 가드 재사용(`window.fomsErpEnsureSavedForSend`). erp-alimtalk-send.js·erp-share.js `?v=20260819c`. 계약 테스트 3건 추가(78 passed)·smoke exit 0. **스테이징 E2E 완료**: 주문 4479 에 실측시간 '16시 30분' 미저장 입력 → 알림톡 클릭 → 자동 저장 후 미리보기 본문에 `시  간 : 16시 30분` 반영(dirty=false·발송 버튼 활성). 공유 링크도 dirty 상태에서 발급 → 자동 저장 확인. 잔여물 정리(share 회수·주문 soft delete·로그아웃).
- [x] **T13 후속 — 저장 안 한 주문도 저장(승격) 후 발송** (2026-08-24 사용자 보고): T13 은 미저장 *변경*만 저장했고 **draft 백업 주문은 저장을 건너뛰었다**(draft 부활 레이스 회피). 그래서 '주문 입력 중 → 저장 안 함 → 알림톡' 동선에서 서버 자격 판정이 `not_eligible` 로 떨어지고, 사용자에게는 "입력해 놨는데 발송이 안 된다"로만 읽혔다. 수정 = **채널 PUSH(`erpRunChannelPush`)와 같은 규칙**: 저장 조건을 `dirty ∨ (주문 id 없음 ∨ draft)` 로 넓히고, **주문 id 를 저장 뒤에 읽는다**(저장이 주문을 만들거나 승격하므로). 앞단의 '저장 후 발송할 수 있습니다' 조기 반환도 저장 뒤로 옮겼다. 공유 발급(`_create`)·내 문자 보내기(`_selfSms`)도 같은 순서 결함이 있어 함께 고쳤다(원클릭 알림톡 `_quickAlimtalk` 은 이미 올바른 순서였다). 필수값 검증은 저장 함수가 그대로 하므로 누락이 있으면 저장이 실패하고 발송이 멈춘다(조용히 옛 저장본으로 나가지 않는다). 계약 테스트 2건 추가·`?v` 핀 범프(`erp-alimtalk-send.js`·`erp-share.js` = `20260824a`).
- [~] **T15 발송 흔적(칩) + 문자 대체발송** (2026-08-24 — ②③ 구현·deploy 완료, 실발송 E2E 잔여): ① **벤더 설정 — 완료.** 실측 알림톡이 카톡 실패 시 문자로 안 나가던 원인은 코드가 아니라 **솔라피 템플릿의 대체발송 설정**이었다(우리 SDK 는 이미 `disableSms:false` 를 보내는데 벤더 기록은 `true` — 템플릿 설정이 API 값을 이긴다). 라홈 예약 템플릿 `KA01TP260819235109543IZ09ZS2GGxU` 에 `replacements={from: 15660792, text: 문자용 본문}` 등록·`disableReplacements:false`, `status:APPROVED` 유지(재심사 안 걸림). 하우드 예약 템플릿은 이미 설정돼 있었다(`010-4464-4260`). **미설정 잔여 = 문서 공유 링크 2종** — 카톡 WL 버튼으로 여는 구조라 문자 본문에 링크를 넣어야 해서 문구 별도 작성 필요. **주의: `update_kakao_template` MCP 도구에는 `replacements` 파라미터가 없다 — 콘솔에서만 설정된다.** ② **화면 — 미구현.** 설계 확정(사용자 승인): 알림톡 버튼 아래 **상시 칩 4상태**(`✓ 예약 안내 보냄 · MM-DD HH:MM · 보낸사람` / `✓ 문자로 보냄`(주황) / `✗ 발송 실패 · 사유` / `아직 안 보냄`(점선)). 데이터는 `sd['alimtalk_measurement']` 가 이미 페이지 로드 때 `window.__erpLastStructuredData` 로 실려 와 **추가 요청 0**. 칩 클릭 시 전체 이력 패널(OrderEvent `ALIMTALK_SENT`/`ALIMTALK_FAILED`, 한글 라벨 `order_event_display.py` 등재됨). PC·모바일·태블릿 동일. ③ **채널 확정 — 미구현.** 접수 시점엔 `type=ATA` 이고 카톡이 실패해야 `SMS`/`LMS` 로 바뀌므로 발송 직후엔 알 수 없다. 사용자 결정 = **발송 1분 뒤 벤더에 한 번 조회**해 채널 확정 후 칩 갱신(웹훅 아님). 판별식: 조회 결과 `type` 이 `SMS`/`LMS` 면 문자로 나간 것(계정 로그에 `type:SMS` + `kakaoOptions` 보유 실사례 있음). 시안: artifact `94b3f16e-2205-4fc8-8982-efef511c0be4`. **구현 완료(2026-08-24, deploy `431e1fc0`)**: 상세 원장 `docs/plans/2026-08-24-alimtalk-trace-t15-ledger.md`. 칩 4상태 PC·모바일·태블릿(추가 요청 0 — 이력이 이미 sd 로 실려 온다) + 칩 클릭 이력 패널(OrderEvent 2종 필터 조회) + 채널 확정 `POST /api/kakao/alimtalk/confirm-channel/<id>`(발송 1분 뒤 1회, 멱등, web 프로세스). 이력 레코드에 `sent_by_name`·`channel`·`channel_checked_at` 추가. 스테이징 실주문 렌더·패널·라우트 확인, CI 4/4 green. **잔여**: 실발송 1건 E2E(실제 알림톡 발송이라 사용자 승인 필요)·태블릿 실기기 육안·문서 공유 링크 템플릿 2종 `replacements` 콘솔 등록(①).
- [x] **T14 실측 알림톡 발신 브랜드 분기** (2026-08-19, `f40a72f2`): `sender_phone(brand)` 신설 — `SOLAPI_SENDER_PHONE_{brand}`(라홈 15660792·하우드 15660703) 우선 + 구 `SOLAPI_SENDER_PHONE` 폴백. `is_configured(brand=None)` 은 공통 판정을 (구 ∨ 브랜드 중 하나)로 완화하고 brand 지정 시 그 브랜드 발신 가능 여부까지 판정(`_ineligible_reason` 이 빈 `from_` 발송을 not_configured 로 사전 차단). 테스트 6건 추가(75 passed)·mutation writer 인벤토리 재생성·smoke exit 0·CI green. **스테이징 실발송 검증 완료**: 라홈 발주사 주문 4479 실측 알림톡 → Solapi ATA `status=COMPLETE·statusCode=4000`, **from=15660792**(직전 08-19 02:57 발송은 15660703 — 분기 전후 대비 확인), to=01083277287, 라홈 템플릿 `KA01TP2608110820...`. 주의: 템플릿 WL 버튼은 운영 도메인 고정이라 스테이징 링크는 404(발송 성공 여부만 검증 가능).

### 운영 검증에서 드러난 진짜 장애: `solapi` SDK 의존 누락 (2026-08-19 — PR #118 → production `aca8cfa7`)
- 증상: 운영 실측 알림톡 수동 발송이 `error=unknown` 으로 실패. 운영 web 로그 `알림톡 발송 실패 (to=010****7282, error=unknown): No module named 'solapi'`.
- 원인: `requirements.txt` 의 `solapi==5.0.3` 이 deploy(`57ee6e5e`)에만 있고 production 브랜치에 한 번도 승격되지 않았다 — **T11·T12 승격 이후에도 운영 알림톡/문자 벤더 호출은 전부 import 단계에서 실패**하고 있었다(Solapi 벤더 로그에 운영발 ATA 기록 없음이 방증).
- 수정: production 브랜치 `requirements.txt` 에 한 줄 추가(두 브랜치 diff 는 이 줄뿐) → 재배포 빌드에 `solapi-5.0.3` 설치 확인.
- **운영 실검증 완료**: 주문 4870(CLAUDE-TEST-PROD-T13, 라홈 발주사) 미저장 실측시간 `11시 20분` → 알림톡 클릭 → 자동 저장 후 본문 반영(T13) → 발송 성공. Solapi ATA `status=COMPLETE·수신 완료`, **from=15660792**(T14 라홈 분기), to=010-8327-7282(사용자 변경 번호). 정리 완료: 주문 soft delete·로그아웃·`claude_master`(id57) 재잠금.

### T16 도면+계약서 한 번에 (2026-08-25 — 통합 링크 deploy, 새 템플릿 심사 중)

- 사용자 요구: 알림톡으로 도면·계약서를 **한 번에** 보내고 싶다. 두 갈래를 **둘 다** 하기로 결정.
- **① 통합 열람 링크(deploy `703e61e3`)** — `SHARE_KINDS` 에 `bundle` 추가. 계약서 쪽 동결 규칙은
  estimate 와 동일(`SNAPSHOT_KINDS`), 스냅샷 없는 bundle 링크는 열람에서 503. 열람 페이지는 도면 본문·
  계약서 본문 **파셜을 공유**(사본 금지 — 단독 링크와 문구가 갈리지 않게). 인쇄는 계약서만.
  알림톡 드롭다운·모바일 시트에 '도면 + 계약서 (한 링크로)'. **지금 승인된 템플릿 그대로 사용**
  (문서종류 = 도면·계약서). 테스트 6건 추가.
- **② 새 템플릿 2종 심사 제출(2026-08-25)** — WL 버튼 2개(`도면 보기`·`계약서 보기`), 변수 6종
  (고객명·유효기간·담당자·담당자연락처·**도면토큰·계약서토큰**), 카테고리 005003.
  라홈 `KA01TP260825021747177Iu2C2ykuJfS` · 하우드 `KA01TP260825021755111MLTAvg2dLLn` — `INSPECTING`.
  승인되면 도면·계약서 share 2건을 만들어 한 통에 싣는 경로로 갈아탄다(env 스위치 예정).
  **문자 대체발송 문구(replacements)는 콘솔 작업 — 사용자 몫**(URL 2개 본문).
- **지방 주문 안내 연락처 규칙(deploy `b7b37042`·`70b94b14`)** — 지방 주문은 도면 컨펌을 본사 CS 가
  받으므로 담당자 표기 `고객센터` + 연락처 본사 대표번호(라홈 `1566-0792` / 라홈 외 발주사 `1566-0703`),
  **문자 대체발송 발신번호도 같은 번호**. env `FOMS_REGIONAL_CONTACT_PHONE_{LAHOM,HAUD}` 로 교체 가능.
  발신 우선순위에 `regional_cs` 단계가 담당자 앞에 붙는다(비지방 T8.1 3단 무변경).

### 개정 템플릿 4종 교체 (2026-08-24 — 승인 완료, PR #140)
- Solapi 심사 승인: 실측 라홈 `KA01TP260819235109543IZ09ZS2GGxU` · 실측 하우드 `KA01TP260819083609155X1JFCnksFJ2` · 공유 라홈 `KA01TP260819084043806JpKvOqz3TDo` · 공유 하우드 `KA01TP260819084128244ThoZdhdBocC`.
- env 교체 완료 3곳(로컬 `.env` · 스테이징 `FOMS` · 운영 `web`, `--skip-deploys`). 템플릿 ID 는 web 서비스에만 존재(worker·cron 없음).
- 개정 내용: 실측 2종은 안내 문구 변경(카카오 고객센터 채팅/담당자 문의) + 상담톡 버튼 제거, 공유 2종은 본문 동일·상담톡 버튼만 제거. ERP 미리보기 상수 `ALIMTALK_TEMPLATE_MEASURE` 를 승인본에 맞춤(`77d20bea`) + REV-99 인벤토리 재생성(`a3bbe5bb`).
- **스테이징 실발송 검증**: 실측 → 신규 templateId·`from=15660792`·COMPLETE·새 문구 확인 / 공유(도면) → 신규 templateId·버튼 `WL:열람하기` 단독·COMPLETE. 잔여물 정리 완료.
- **함정**: 상수 줄 수가 바뀌면 REV-99 인벤토리 lineno 가 밀려 smoke red — 재생성 필수(2026-08-24 실사례, push 후 후속 커밋으로 복구).

### T13·T14 운영 승격 (2026-08-19 — 완료, PR #117 → production `40248a45`)
- 승격 커밋: `f40a72f2`(T14) → `0fc0770d`, `d83854c2`(T13) → `4a4d1928` (자기 세션 커밋만 cherry-pick, docs 제외).
- 충돌 해소: `erp_order_js.html` = production 줄 유지 + 본인 핀 2개만 `?v=20260819c` 범프 / `test_erp_order_shared_form_scripts.py` = production 핀 유지 + 본인 assertion 2줄 추가 / mutation writer 인벤토리 = 승격 트리 재생성.
- 검증: 승격 트리 pre_push_smoke exit 0 · 관련 스위트 127 passed · APP_OK, PR 체크 perf-gate·pg-lane pass.

## production 승격 (2026-08-13 — 완료, PR #89 → production `a59c0d7d`)

- 1차 선행 점검 중단: production 에 `itemuid_00` 부재(체인 `share_token_00→itemuid_00→senderphone_00` 단절) → **사용자 승인 ①** itemuid 포함. 2차 promote_completeness INCOMPLETE: share.py 가 `kakao_alimtalk.py` 하드 의존(production 에 파일 부재) → **사용자 승인 ②** 알림톡 v1 코드 포함(발송은 이중 잠금 — killswitch off·PF/템플릿 env 미설정, 수동 버튼만 노출).
- 세트 21커밋 = 알림톡 v1 8(인벤토리 전용 95c982aa 는 재생성 대체) + 고객 공유 10(T1~T9·T8.1, docs-only T5·merge T10 제외) + itemuid 2 + 정리 2(인벤토리 4종 재생성·`erp-order-shared.js` ?v=20260813d 범프·share_token_00 재부모화 deploy 정본 동기화 — bc810a9a 병합 해결분은 cherry-pick 불가라 파일 동기화).
- 충돌 해소: erp_order_js.html ?v 드리프트(기계적 병합)·models.py OrderFieldChange/OrderShareToken 병치·ledger=승격분·AI_STATUS=production 유지·인벤토리 JSON=재생성. 검증: 단일 head·APP_OK·도메인 82 passed·pre_push_smoke 322 passed·PR 체크 perf-gate/pg-lane pass.
## 결정 기록
- 플랜 확정 3건(CEO 2-agent 리뷰 반영): 스냅샷 64KB 캡=초과 시 400(절단 금지) / send-sms 멱등=**발송 전 앵커 선점 insert**+시간버킷 dedupe_key(`share_sms:{share_id}:{floor(epoch/5)}`) — DB UNIQUE로 동시 중복 차단, 감사 조회식 check-then-act 폐기 / send-sms URL=body 토큰 원문 재해시 검증 후 서버 조립(해시-온리 저장과 충돌 해소, 문자 발송은 발급 직후만)
- CEO 2-agent 리뷰(2026-08-11): HIGH 3건(T1 가짜 테스트 경로·URL 재구성 충돌·멱등 레이스)+MED 6건 플랜 반영 완료, 수용 리스크는 플랜 §4 기록
- 스펙 v3 사용자 결정 D1~D8 준수(풀스코프 v1, 도면 먼저 단계 배포)
