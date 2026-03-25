# 클린코드 감리: 실측 대시보드「저장 중」무한 로딩 (로컬 OK / Production NG)

- **일자**: 2026-03-25  
- **증상**: 원격 production에서만 저장 UI가 `저장 중...`에 고정 (로컬은 정상)  

---

## 1. 원인 분석 (Root cause)

### A. 인라인 셀 저장 (`measurement.js`)

- `blur` 후 `fetch('/api/...')` → `await res.json()` 까지 **타임아웃 없음**.
- 로컬은 지연(ms) 단위로 끝나지만, production(Railway 등)에서는 **콜드스타트·네트워크·프록시**로 응답이 늦거나 연결이 **정지**하면 `fetch`가 **끝나지 않음** → 셀 문구가 `저장 중...`에서 **복구되지 않음**.
- **클린코드 관점**: 비동기 I/O에 상한(Abort)이 없으면 UI는 항상 “영구 로딩” 위험에 노출됨.

### B. PNG 일정표 저장 (`measurement-image-export.js` + 헬퍼)

- 과거: `erpTableExportWaitForImages` / `html2canvas` 가 **무한 대기** 가능 → 버튼 `저장 중...` 고정.
- **이미 조치됨**: 이미지 대기 타임아웃, `html2canvas` 레이스 타임아웃, `finally`로 버튼 복구 (`erp-table-image-export-helpers.js`, `measurement-image-export.js`).

---

## 2. 조치 (이번 커밋)

| 항목 | 내용 |
|------|------|
| `measurement.js` | `AbortController` + **45초** 후 `abort`. `AbortError` 시 사용자 알림 + 셀 원복. `finally`에서 `clearTimeout`. |

---

## 3. 감리 체크리스트

| # | 항목 | 결과 |
|---|------|------|
| 1 | API 실패 시 UI 복구 | `data.success === false` 시 기존 값 복구 유지 |
| 2 | 네트워크/지연 | `AbortError` 처리 추가 |
| 3 | PNG 경로 | 타임아웃 + `finally` (기존 패치) |
| 4 | 수동 행 | `isManual` 분기에서 서버 호출 없음 (변경 없음) |

---

## 4. 남은 권장 (🟡)

1. **서버 측**: `/api/erp/measurement/update` 응답 시간·502 로그 확인 (프론트만으로는 근본 치유 불가).
2. **`res.json()`** 극단적 지연: 필요 시 별도 타임아웃(현재는 fetch 중단으로 대부분 커버).
3. **정적 파일 캐시**: production 배포 후 브라우저 강력 새로고침으로 `measurement.js` 최신 반영 확인.

---

## 5. 검증 시나리오 (수동)

1. Production 실측 대시보드에서 셀 편집 → 저장 후 값 반영 또는 실패 메시지.
2. 개발자 도구 Network에서 **Slow 3G**로 지연 시뮬 → 45초 후 알림 + 셀 복구.
3. PNG 저장 버튼 → 완료 또는 타임아웃 알림 후 버튼 라벨 복구.
