# 채널톡 ↔ 구글시트 웹훅 미반영 문제 분석 및 해결 방안

**작성일**: 2026-03-16  
**관련**: [실측일정 구글시트](https://docs.google.com/spreadsheets/d/1ciiCihaOkPS1E4eU3WzsfCGb59aH68RY1SUnqESL0yw/edit?gid=1573713753)

---

## 요약 (한 줄)

**구글 Apps Script 웹훅이 `personType === 'bot'`인 모든 메시지를 차단**하고 있어, FOMS에서 채널톡 API로 보낸 메시지가 실측일정에 반영되지 않음. `isBotMessageEcho_` 수정으로 FOMS 봇만 예외 허용 가능.

---

## 1. 현재 구조

```
[채널톡 앱에서 매니저가 직접 입력]  →  채널톡  →  웹훅  →  구글시트 ✅ 반영됨
[FOMS에서 채널톡 API로 푸시]       →  채널톡  →  웹훅  →  구글시트 ❌ 미반영
```

- **FOMS → 채널톡**: `writeGroupMessage` Native Function (App Store API) 사용
- **채널톡 → 구글시트**: 채널톡 웹훅이 push 이벤트를 구글시트(또는 Apps Script)로 전달
- **구글시트 데이터**: `{"event":"push","entity":{"chatKey":"group-xxx",...}}` 형태의 JSON

---

## 2. 근본 원인 (추정)

### 원인 A: 채널톡 플랫폼 (미확정)
채널톡 웹훅이 **API/봇 메시지**에 대해 push 이벤트를 발송하지 않을 수 있음.

### 원인 B: 구글 Apps Script 웹훅 핸들러 (확정)
**웹훅 스크립트가 봇 메시지를 명시적으로 차단하고 있음.**

```javascript
// isBotMessageEcho_() 함수
function isBotMessageEcho_(payload){
  const txt = asString(payload.text || '');
  if (txt.startsWith(REPLY_PREFIX)) return true;   // "✅ 등록 완료" 재수신 방지
  if (payload.personType === 'bot') return true;   // ← 모든 봇 메시지 차단
  return false;
}

// handleMessage_() 내부
if (isBotMessageEcho_(payload)) { logDbg_('WHY','bot-echo'); return; }  // 여기서 즉시 return
```

- FOMS는 `botName: "FOMS"`로 전송 → 채널톡 웹훅 페이로드에 `personType: "bot"` 포함
- 스크립트는 `personType === 'bot'`이면 **무조건 처리 생략**
- 따라서 채널톡이 FOMS 메시지에 대해 웹훅을 보내더라도, **스크립트가 버림**

---

## 2-1. 웹훅 스크립트 상세 분석

### 처리 흐름
1. `doPost(e)` → `extractPayload_(raw, ctype)` → `handleMessage_(payload)`
2. `handleMessage_` 필터:
   - `groupName` ∈ ALLOWED_GROUPS (발주방, 영업팀_발주정보, 실측스케줄)
   - `chatId` → `GROUP_NAME_BY_CHATID`: 229625=발주방, 209990=영업팀_발주정보, **229923=실측스케줄**
   - `isOrderFormMessage_()`: 고객명+연락처+시공일/주소/발주사 중 하나 이상
   - **`isBotMessageEcho_(payload)` → true면 즉시 return (처리 안 함)**
   - `isSeenPayload_()`: 10분 내 동일 메시지 중복 방지

### FOMS 전송 대상
- FOMS `CHANNEL_GROUP_MEASUREMENT` = 실측스케줄 그룹 (chatId 229923 추정)
- FOMS 메시지 형식: `[신규 접수/상태 변경] 고객명\n상태: 실측\n주소: ...\n실측일: ...\n{FOMS_URL}/orders/{id}/erp`
- `isOrderFormMessage_` 검사: `고객명:`, `연락처:`, `시공일:` 등 라벨 기반 → **FOMS 형식은 매칭 안 될 수 있음**

### FOMS vs 웹훅 기대 형식 비교

| 항목 | 웹훅 기대 형식 (`isOrderFormMessage_`) | FOMS 실제 전송 형식 |
|------|----------------------------------------|----------------------|
| 고객명 | `고객명 : 김철수` | `[신규 접수] 김철수` (라벨 없음) |
| 연락처 | `연락처 : 010-1234-5678` | **없음** (FOMS format_order_message에 미포함) |
| 시공일 | `시공일 : 10월 24일` | `시공일: 2025-10-24` (포맷 다름) |
| 주소 | `주 소 : 서울시...` | `주소: 서울시...` |
| 실측일 | `실측일 : 10월 23일` | `실측일: 2025-10-23` |

`isOrderFormMessage_` 조건: `고객명:` + `연락처:` + (시공일|주소|발주사) 중 하나.  
→ FOMS는 **연락처를 안 보내고**, 고객명도 `고객명 :` 라벨이 아니라 `[신규 접수] 이름` 형태라 **현재 형식으로는 통과 불가**.

### 결론
1. **봇 차단**: `personType === 'bot'` → 무조건 스킵 (1차 원인)
2. **폼 형식 불일치**: FOMS 메시지가 `고객명:`, `연락처:` 라벨 형식이 아님 → `isOrderFormMessage_` 탈락 (2차 원인)

---

## 3. 해결 방안

### 방안 0: 웹훅 스크립트 + FOMS 형식 맞추기 (우선 시도)
**필요 작업 2가지:**

#### 0-1. `isBotMessageEcho_` 수정 (봇 허용)
```javascript
function isBotMessageEcho_(payload){
  const txt = asString(payload.text || '');
  if (txt.startsWith(REPLY_PREFIX)) return true;

  if (payload.personType === 'bot') {
    // FOMS 봇: URL 또는 [신규 접수/상태 변경] 형식 → 허용
    if (/lahom-production\.up\.railway\.app\/orders\/\d+\/erp/.test(txt)) return false;
    if (/\[(?:신규 접수|상태 변경|정보 저장)\]/s.test(txt)) return false;
    return true;
  }
  return false;
}
```

#### 0-2. 형식 호환 (둘 중 하나)
- **A) FOMS 전송 텍스트 변경**: `format_order_message`를 실측스케줄 발주 포맷(`고객명 :`, `연락처 :`, `시공일 :` 등)에 맞게 수정
- **B) 웹훅에 FOMS 파서 추가**: `isOrderFormMessage_`에 FOMS 형식 분기, `parseMessage_`에 FOMS용 추출 로직 추가

---

### 방안 A: FOMS에서 구글시트 직접 쓰기 (권장)

**개요**: 채널톡 API 전송과 **동시에** FOMS 서버에서 Google Sheets API로 실측일정 행을 추가.

**장점**
- 채널톡 웹훅에 의존하지 않음
- FOMS가 단일 진실 소스(Source of Truth)로 동작
- 실측일정 형식(고객명, 실측일, 시공일 등)을 FOMS 데이터 기준으로 정확히 제어 가능

**필요 작업**
1. Google Sheets API 연동 (OAuth2 또는 서비스 계정)
2. `channel_integration.py` 또는 `channel_client.py`에서 채널톡 전송 성공 시, 구글시트 append 로직 호출
3. 환경변수: `GOOGLE_SHEET_ID`, `GOOGLE_CREDENTIALS_JSON` 등

**구현 난이도**: 중 (Google API 인증 설정 필요)

---

### 방안 B: 채널톡 웹훅 설정 확인

**개요**: 채널톡 대시보드에서 웹훅이 "봇/앱 메시지"도 수신하도록 설정되어 있는지 확인.

**확인 경로**
- 채널톡 대시보드 → 설정 → 웹훅
- "그룹 채팅 알림" 옵션에 "앱/봇 메시지 포함" 같은 세부 옵션이 있는지 확인

**참고**: 채널톡 공식 문서에 해당 옵션이 명시되어 있지 않다면, API 메시지는 웹훅 대상이 아닐 수 있음.

---

### 방안 C: FOMS 웹훅 → 중간 서비스 → 구글시트

**개요**: FOMS에서 채널톡 전송 후, **FOMS 자체 웹훅**을 호출하여 Zapier/Make/n8n 등으로 구글시트에 쓰기.

```
FOMS → 채널톡 API
    → FOMS 내부: POST to Zapier Webhook (실측 데이터 JSON)
         → Zapier: Google Sheets "Add Row"
```

**장점**
- FOMS 코드 변경 최소화 (웹훅 URL 호출만 추가)
- Zapier/Make 무료 플랜으로도 가능

**단점**
- 외부 서비스 의존
- 실측일정 시트 컬럼 구조에 맞게 Zapier 시나리오 구성 필요

---

### 방안 D: 채널톡 대신 매니저 계정으로 전송 (비권장)

**개요**: `writeGroupMessage` 대신 매니저 계정으로 메시지를 보내는 API가 있다면, 웹훅이 트리거될 수 있음.

**문제**
- 채널톡 Native Functions에는 "매니저로 위장 전송" API가 없을 가능성이 높음
- 보안/감사 측면에서도 부적절

---

## 4. 권장 실행 순서

1. **방안 0**: 웹훅 스크립트 `isBotMessageEcho_` 수정 → FOMS 봇 메시지 허용 (10분)
2. **방안 0-2**: FOMS 전송 텍스트를 실측스케줄 발주 포맷(고객명:, 연락처:, 시공일: 등)에 맞게 조정, 또는 `isOrderFormMessage_`에 FOMS 형식 분기 추가
3. **방안 B**: 채널톡 웹훅 설정에서 "봇/앱 메시지 포함" 옵션 유무 확인 (5분)
4. **방안 A**: Google Sheets API 연동 후 FOMS에서 직접 append 구현 (1~2일)
5. **방안 C**: 방안 A가 어렵다면 Zapier/Make로 우회 (반나절)

---

## 5. 방안 A 구현 시 참고 (FOMS 코드)

- `apps/api/channel_integration.py`의 `api_channel_push_manual()` 성공 분기
- `services/channel_client.py`의 `send_group_message()` 반환 후
- 구글시트 append 시 필요한 데이터: `order` 객체의 `structured_data`, `customer_name`, `address` 등
- 실측일정 시트 컬럼: 수신일시, 컨텐츠타입, 길이, 요약, 원문 일부 등 (기존 웹훅 형식에 맞출지, FOMS 전용 컬럼으로 할지 결정 필요)

---

## 6. 다음 단계

- [ ] **방안 0**: `isBotMessageEcho_` 수정 후 FOMS 푸시 테스트
- [ ] FOMS 메시지가 `isOrderFormMessage_` 형식에 맞는지 확인 (고객명:, 연락처:, 시공일: 등)
- [ ] 채널톡 웹훅 설정 화면 스크린샷 확보 후 "봇 메시지" 옵션 확인
- [ ] 방안 A 선택 시: Google Sheets API 연동 Spec 작성
- [ ] 방안 C 선택 시: Zapier Webhook URL 및 시나리오 설계

---

## 부록: 웹훅 스크립트 구조 요약

| 구성요소 | 역할 |
|----------|------|
| `doPost(e)` | 채널톡 웹훅 POST 수신 진입점 |
| `extractPayload_` | JSON 파싱 → chatId, groupName, text, personType, messageId |
| `resolveGroupNameStrict` | chatId/그룹명 → 발주방/영업팀_발주정보/실측스케줄 |
| `GROUP_NAME_BY_CHATID` | 229625→발주방, 209990→영업팀_발주정보, 229923→실측스케줄 |
| `isOrderFormMessage_` | 고객명+연락처+(시공일\|주소\|발주사) 라벨 형식 검사 |
| `isBotMessageEcho_` | **personType===bot 또는 "✅ 등록 완료" → true(스킵)** |
| `isSeenPayload_` | 10분 캐시로 동일 메시지 중복 방지 |
| `parseMessage_` | 텍스트에서 고객명, 시공일, 실측일, 주소, 연락처 등 추출 |
| `handleMessage_` | 발주내용 upsert + 실측스케줄 append + 자동회신(postToChannelGroup_) |
