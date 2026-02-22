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
