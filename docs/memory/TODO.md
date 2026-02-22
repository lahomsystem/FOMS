# Phase C·D·Railway 잔여 TODO (승인 후 차례대로 실행)

- [x] **1. Railway Worker 서비스 추가 + USE_RQ_WORKER=1**  
  `railway add --service worker --variables "USE_RQ_WORKER=1"` 실행 완료. railway-worker.toml 생성. **대시보드 확인 필요**: Worker > Settings > Config Path: `railway-worker.toml`, GitHub repo 연결, REDIS_URL 공유

- [x] **2. Railway Web Replica 2개 설정**  
  `railway scale -s foms --us-east4-eqdc4a 2` 실행 완료

- [x] **3. Phase C 7.3: 지도 동시 40명 부하 테스트**  
  실행 완료: map_data/generate_map 각 40/40 성공, p95 4.12s (목표 2초 미달. Railway Replica 2에서 재측정 권장)

- [x] **4. 채팅 direct upload**  
  - 4a. `apps/api/chat/routes.py`: session → complete direct 플로우 API 추가  
  - 4b. 채팅 업로드 UI: direct 플로우 적용 (chat_scripts_file.html)

- [x] **5. Phase D 6.1~6.3 검증**  
  - 6.1 session API 확인 완료
  - 6.2 수동: 동시 20건 CPU/메모리 비교 (Railway/로컬에서 선택 수행)
  - 6.3 multipart API 확인 완료 (POST /api/chat/upload HTTP 200)

- [ ] **6. 원격(Railway) 주소변환(지도) 동작 확인**  
  - 진단 보고서: `docs/incidents/2026-02-22-remote-geocode-diagnosis.md`
  - Railway 대시보드에서 FOMS 웹 REDIS_URL, Worker Online/REDIS_URL/DATABASE_URL 확인
  - 설정 반영 후 지도 페이지 새로고침으로 마커 표시 여부 검증

- [ ] **7. 지도 버튼 즉시 변환 (동기 병렬 geocode)**  
  - api_generate_map: lat/lng 없는 주문 최대 10건 ThreadPoolExecutor 병렬 geocode
  - 병렬 수 5, Kakao API 호출 후 DB 갱신, map_data에 반영

---

# 로그인 담당자 필터 + 시공팀 전용 접근 (2026-02-22)

- [x] **A1. 전역 "내 할 일" 버튼**  
  layout.html: 알림 버튼 왼쪽에 버튼 추가, cookie `erp_mine_only` 토글, ERP 페이지에서 cookie 읽어 mine=1 기본 적용

- [x] **A2. 출고 대시보드 mine 필터**  
  erp_shipment_page: mine/cookie 시 construction_workers에 current_user.name 포함된 주문만 표시

- [x] **A3. 시공 대시보드 mine 필터**  
  erp_construction_page: mine/cookie 시 construction_workers에 본인 포함된 주문만 표시

- [x] **A4. 시공팀 접근 제한**  
  app.py before_request: CONSTRUCTION 팀은 /erp/shipment, /erp/construction 외 접근 시 출고 대시보드로 리다이렉트; erp_sub_nav에서 시공팀일 때 출고·시공만 노출

- [x] **A5. 시공팀 데이터 강제**  
  출고·시공 대시보드에서 user.team == CONSTRUCTION이면 mine_only 강제(본인 배정 주문만 표시)

- [ ] **A6. 점검**  
  코드 리뷰, 수동 테스트(일반 사용자 mine 토글, 시공팀 계정으로 출고/시공만 접근·본인 건만 표시)

---

# 출고 대시보드 시공자 그룹·파스텔 색상 (2026-02-22)

- [x] **B1. 백엔드 정렬**  
  erp_shipment_page.py: get_construction_worker_key_for_sort, is_as_order 추가; rows.sort(AS, worker_key, manager, id)

- [x] **B2. 템플릿 서버 렌더**  
  worker_list·pastel_colors, 행별 worker_key·worker_bg_color, tr data-as/data-manager, td.shipment-worker-cell 스타일

- [x] **B3. CSS**  
  .shipment-worker-cell 및 hover 시 배경 유지(var(--worker-bg-color))

- [x] **B4. JS 정렬·색**  
  getFirstWorkerFromRow, workerKeyForSort, applyShipmentWorkerSortAndColors, scheduleApplyShipmentWorkerSortAndColors; PASTEL_COLORS, WORKER_DEFAULT_BG

- [x] **B5. JS 호출 시점**  
  로드 시 fetch 후 + DOMContentLoaded/setTimeout 50ms; 시공자 blur(위임 포함)·추가 blur·삭제 클릭·저장된 값 선택 시 scheduleApplyShipmentWorkerSortAndColors

- [ ] **B6. 검증**  
  시공자 입력/추가 시 같은 시공자끼리 묶임·파스텔 색 적용; 시공자 전부 삭제 시 해당 행 회색·정렬 반영; 새로고침 없이 동작
