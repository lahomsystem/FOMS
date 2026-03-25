# GDM 감리 보고서: 실측 대시보드 수동 행 (measurement-manual-rows)

- **일자**: 2026-03-25  
- **범위**: `static/js/erp/measurement-manual-rows.js`, `static/js/erp/measurement.js`, `templates/erp_measurement_dashboard.html`(스크립트 순서), `static/js/measurement-image-export.js`(갭 행 제거)  
- **요구사항 요약**: DB 미저장·`localStorage`만, 수동 행만 삭제, 담당자 색·정렬 연동, 행 사이 시각적 갭 없음·경계 클릭 삽입  

---

## 종합 점수: **82 / 100**

| 구분 | 건수 |
|------|------|
| 긴급 조치(🔴) | 0 (감리 시점 기준) |
| 개선 권장(🟡) | 3 |
| 양호(🟢) | 5 |

---

## 긴급 (🔴)

없음. (감리 전 잠재 이슈는 아래 “감리 중 조치”로 반영.)

---

## 감리 중 조치 (이번 세션)

1. **이벤트 순서(경계 클릭 vs 인라인 편집)**  
   - **문제**: `measurement.js`가 `tbody`에 버블 단계로 인라인 편집을 걸어 두어, 행 경계 클릭이 `td.editable-cell`에 닿으면 수동 행 삽입 대신 편집 모드가 먼저 열릴 수 있음.  
   - **조치**: 수동 행 모듈의 클릭 핸들러를 **캡처 단계(`true`)**로 등록하고, 경계 삽입 성공 시 `stopPropagation()`으로 버블 차단.

2. **데드 API (`measurementManualRowsInsertGaps`)**  
   - **문제**: 갭 `<tr>` 제거 후에도 noop이 정렬 끝마다 호출되어 의도 불명·노이즈.  
   - **조치**: `measurement.js`에서 `InsertGaps` 스텁 및 호출 제거, `measurement-manual-rows.js`에서 `window.measurementManualRowsInsertGaps` 할당 제거.

---

## 개선 권장 (🟡)

1. **경계 히트 영역**  
   - `BOUNDARY_TOL_PX = 6`은 디스플레이·줌에 따라 좁게 느껴질 수 있음. 현장 피드백 시 8~10px 또는 “행 하단 N%만” 보조 규칙 검토.

2. **테스트 부재**  
   - 단위/E2E 없음. 최소한 수동 시나리오 체크리스트(삽입·삭제·새로고침 복원·담당자 정렬·이미지 저장)를 QA 문서에 고정 권장.

3. **XSS·내용 이스케이프**  
   - 수동 행 HTML은 `escapeHtml`로 생성되어 양호. 편집 후 `textContent` 반영은 `measurement.js` 경로—지속적으로 Jinja/서버와 동일 정책 유지.

---

## 양호 (🟢)

1. **아키텍처**: Blueprint/API 확장 없이 프론트 전용·요구사항과 일치.  
2. **정렬 일관성**: 메인↔동일 주문 상세 사이 삽입 금지로 `measurement.js`의 main/detail 페어 깨짐 방지.  
3. **저장소 키**: 날짜(`selectedDate`) 단위 네임스페이스로 일자별 격리.  
4. **레거시**: `removeGapRows`·이미지 export의 `.measurement-gap-row` 제거는 과거 HTML 대비 안전망.  
5. **스크립트 순서**: `measurement.js` → `measurement-manual-rows.js`로 전역 훅 덮어쓰기 순서 적절.

---

## 잔여 리스크 (수동 확인 권장)

- 터치 디바이스에서 경계 탭 정확도.  
- 다중 `tbody`/테이블 변경 시 셀렉터 `.measurement-table tbody` 단일 가정.  

---

## GDM 절차 대조

| GDM 권장(에이전트 오케스트레이션) | 본 감리 |
|----------------------------------|--------|
| explore + code-reviewer + DB 등 | 코드 정적 리뷰 + 통합 이벤트 분석 + 필요 시 코드 수정 |
| 100점 만족 | **아님** — 브라우저 실사용·자동 테스트 미실행 |

**결론**: 구현 의도·연동은 **감리 기준으로 승인 가능(조건부)**이며, **운영 확정 전** 실측 대시보드에서 위 “잔여 리스크” 시나리오만 한 번 통과시키는 것을 권장한다.
