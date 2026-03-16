# FOMS → 채널톡 + 구글시트 동시 전송 Spec

**작성일**: 2026-03-16  
**목표**: FOMS 채널톡 푸시 시, 채널톡과 구글시트(실측일정)에 동시 반영

---

## 1. 현재 상황 정리

### 구글시트 구조 (동일 스프레드시트, 탭만 다름)

| gid | 시트명 | 용도 |
|-----|--------|------|
| 1573713753 | Webhook로그 | 채널톡 웹훅 원문 수신 로그 (수신일시, 컨텐츠타입, 요약, 원문) |
| 0 | 실측일정 | 파싱된 실측 스케줄 (실측일, 고객명, 발주사, 시공일, 주소, 전화번호, ...) |

### FOMS 수동 푸시 흐름

1. 사용자가 **변환** 버튼 → `erpGenerateConversionText()` 실행
2. 생성 텍스트 형식: `실측일 : 10월 23일\n시 간 : 종일\n\n고객명 : 김철수\n발주사 : 라홈\n시공일 : ...\n주 소 : ...\n연락처 : 010-...\n\n제품명 : ...`
3. **채널톡 전송** 버튼 → `POST /api/channel/push-manual` { order_id, text }
4. 서버: `send_group_message()` → 채널톡 API

### 핵심 발견

- **변환 텍스트 형식**이 웹훅 `isOrderFormMessage_` 기대 형식과 **동일** (고객명 :, 연락처 :, 시공일 : 등)
- 문제: 채널톡 API 전송 시 `personType: "bot"` → 웹훅 스크립트가 차단
- 추가: 채널톡이 API 메시지에 대해 웹훅을 아예 안 보낼 가능성 있음

---

## 2. 권장 방안: FOMS → Apps Script Web App 직접 POST

**채널톡 웹훅에 의존하지 않고**, FOMS가 채널톡 전송 성공 직후 **동일한 텍스트**를 Apps Script Web App에 POST.

```
[사용자] 변환 → 채널톡 전송 클릭
    ↓
[FOMS] 1) send_group_message() → 채널톡 ✅
       2) POST to Apps Script Web App (동일 text) → 구글시트 실측일정 ✅
```

### 장점

- 채널톡 웹훅/봇 차단과 무관
- 변환 텍스트가 이미 실측스케줄 형식이라 파싱 재사용 가능
- Google API 인증 불필요 (Apps Script Web App은 URL만 알면 됨)
- 구현 단순 (FOMS: POST 1회 추가, Apps Script: FOMS 분기 추가)

---

## 3. 구현 상세

### 3-1. FOMS 측 (channel_integration.py)

**추가 로직**: `api_channel_push_manual()` 성공 분기에서, Apps Script Web App URL로 POST.

```python
# 채널톡 전송 성공 후
GOOGLE_SCRIPT_WEBHOOK = os.environ.get("GOOGLE_SCRIPT_WEBHOOK", "")

if GOOGLE_SCRIPT_WEBHOOK and text:
    try:
        requests.post(
            GOOGLE_SCRIPT_WEBHOOK,
            json={"source": "foms", "text": text, "order_id": order_id},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
    except Exception as e:
        logger.warning("[구글시트] Web App POST 실패 (무시): %s", e)
```

**환경변수**: `GOOGLE_SCRIPT_WEBHOOK` = Apps Script Web App 배포 URL (예: `https://script.google.com/macros/s/xxx/exec`)

### 3-2. Apps Script 측 (doPost 수정)

**doPost 진입 시 분기**:

```javascript
function doPost(e){
  try {
    const raw = e?.postData?.contents || '';
    const ctype = e?.postData?.type || '';
    logDbg_('RAW', (ctype||''), (raw||'').slice(0,500));

    let body = {};
    if (raw && /application\/json/i.test(ctype)) {
      try { body = JSON.parse(raw); } catch { body = {}; }
    }

    // FOMS 직접 전송 분기
    if (body.source === 'foms' && body.text) {
      handleFomsPayload_(body);
      return ContentService.createTextOutput('ok').setMimeType(ContentService.MimeType.TEXT);
    }

    // 기존: 채널톡 웹훅 처리
    const payload = extractPayload_(raw, ctype);
    // ... 기존 handleMessage_ 로직
  } catch(err){ ... }
}

function handleFomsPayload_(body) {
  const text = asString(body.text || '').trim();
  if (!text) return;
  if (!isOrderFormMessage_(text)) { logDbg_('FOMS', 'not-form'); return; }

  const { header: h, products } = parseMessage_(text);
  const groupName = '실측스케줄';

  // 1) 발주내용 upsert
  upsertOrdersWithPriority_(groupName, h, products || []);

  // 2) 실측일정 append
  const shSched = getSheet_(SHEET_SCHEDULE, HEADER_SCHEDULE);
  deleteDuplicatesScheduleTwoOfThree_(h.customerName, h.address, (h.phone || '') + ' ' + (h.phoneExtra || ''));
  const schedRow = composeScheduleRow_(h, (products||[])[0], 'FOMS');
  shSched.appendRow(schedRow);
  sortScheduleByDateDesc_();

  // 자동회신 생략 (FOMS → 채널톡은 이미 전송됨, 중복 회신 방지)
  logDbg_('FOMS', 'append-ok', body.order_id);
}
```

### 3-3. 보안 (선택)

- Apps Script Web App 배포 시 **"누구나"** 접근 가능해야 FOMS 서버에서 호출 가능
- 보안: `body.source === 'foms'` + **비밀 토큰** 검증
  - 환경변수 `GOOGLE_SCRIPT_SECRET` (FOMS), Script Properties `FOMS_SECRET` (Apps Script)
  - POST 시 `Authorization: Bearer <secret>` 또는 `body.secret` 검증

---

## 4. 실측일정 시트 컬럼 매핑

| HEADER_SCHEDULE | FOMS/parseMessage_ 추출 |
|-----------------|-------------------------|
| 실측일 | h.measureDate |
| 고객명 | h.customerName |
| 발주사 | h.clientName |
| 시공일 | h.installDate |
| 주소 | h.address |
| 전화번호 | h.phone (normalizePhone) |
| 추가연락처 | h.phoneExtra |
| 방문시간 | h.visitTime |
| 제품명 | firstProduct?.name |
| 수정자 | 'FOMS' |
| 수정시각 | new Date() |
| ENTRY_ID | genEntryId_(customerName) |

`parseMessage_`가 변환 텍스트(`실측일 :`, `고객명 :` 등)에서 이미 추출하므로 **추가 파서 불필요**.

---

## 5. 배포 순서

1. **Apps Script**: `doPost`에 FOMS 분기 + `handleFomsPayload_` 추가 → 배포(웹 앱) → URL 복사
2. **FOMS**: `GOOGLE_SCRIPT_WEBHOOK` 환경변수 설정 (Railway 등)
3. **channel_integration.py**: 채널톡 성공 후 POST 로직 추가
4. 테스트: ERP Beta에서 변환 → 채널톡 전송 → 구글시트 실측일정 탭 확인

---

## 6. 대안 (참고)

| 방안 | 설명 | 난이도 |
|------|------|--------|
| A | Google Sheets API (서비스 계정) 직접 append | 중 |
| B | 웹훅 스크립트 `isBotMessageEcho_` 수정 + 채널톡이 봇 웹훅 보내는지 확인 | 하 (불확실) |
| C | Zapier Webhook → Google Sheets | 중 (외부 의존) |

**본 Spec은 FOMS → Apps Script 직접 POST** 방식으로, B의 불확실성을 피하고 A보다 인증 부담이 적음.

---

## 7. Apps Script 코드 (복사용)

### doPost 진입부 수정

기존 `doPost(e)` 함수 **맨 앞**에 다음 분기 추가:

```javascript
function doPost(e) {
  try {
    const raw = e?.postData?.contents || '';
    const ctype = e?.postData?.type || '';
    logDbg_('RAW', (ctype||''), (raw||'').slice(0,500));

    let body = {};
    if (raw && /application\/json/i.test(ctype)) {
      try { body = JSON.parse(raw); } catch { body = {}; }
    }

    // FOMS 직접 전송 분기
    if (body.source === 'foms' && body.text) {
      handleFomsPayload_(body);
      return ContentService.createTextOutput('ok').setMimeType(ContentService.MimeType.TEXT);
    }

    // === 기존 채널톡 웹훅 처리 로직 그대로 유지 ===
    const payload = extractPayload_(raw, ctype);
    // ... (이하 동일)
```

### handleFomsPayload_ 함수 추가

기존 `parseMessage_`, `isOrderFormMessage_`, `upsertOrdersWithPriority_`, `getSheet_`, `composeScheduleRow_` 등을 사용하므로, 기존 스크립트에 다음 함수를 추가:

```javascript
function handleFomsPayload_(body) {
  const txt = (body.text || '').toString().trim();
  if (!txt) return;
  if (!isOrderFormMessage_(txt)) { logDbg_('FOMS', 'not-form'); return; }

  const parsed = parseMessage_(txt);
  const h = parsed.header || {};
  const products = parsed.products || [];
  const groupName = '실측스케줄';

  upsertOrdersWithPriority_(groupName, h, products);

  const shSched = getSheet_(SHEET_SCHEDULE, HEADER_SCHEDULE);
  deleteDuplicatesScheduleTwoOfThree_(h.customerName, h.address, (h.phone || '') + ' ' + (h.phoneExtra || ''));
  const schedRow = composeScheduleRow_(h, products[0], 'FOMS');
  shSched.appendRow(schedRow);
  sortScheduleByDateDesc_();

  logDbg_('FOMS', 'append-ok', body.order_id);
}
```

**주의**: `parseMessage_`, `composeScheduleRow_` 등이 반환하는 구조가 기존과 동일해야 함. 변수명(`header`, `products`)은 실제 스크립트에 맞게 조정.

### Web App 배포

1. Apps Script 편집기 → 배포 → 새 배포
2. 유형: 웹 앱
3. 실행 사용자: **나**
4. 액세스: **모든 사용자** (FOMS 서버에서 호출 가능하도록)
5. 배포 후 URL 복사 → `GOOGLE_SCRIPT_WEBHOOK` 환경변수에 설정
