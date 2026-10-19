# 미국 경찰 스타일 경광등·사이렌 변경 기록

- 요청: 기존 사이렌을 더 실감 나는 미국 경찰 경광등 버전으로 변경.
- 범위: 화면의 경광등 CSS, Web Audio 합성음, 공용 자산 캐시 버전. API·DB·전송 채널 변경 없음.
- 기존 구현: sine 단음의 600–1200Hz 직선 왕복과 둥근 회전 경광등.
- 변경: 정규화된 배음 파형과 650–1550Hz 곡선으로 Wail → Yelp → 빠른 Priority 스타일을 합성한다. 이는 특정 제조사의 녹음 또는 정밀 복제가 아니다. 외부 음원 다운로드 없이 AudioParam에 8초 곡선을 예약한다.
- 시험은 2초 Wail/Yelp, 알림은 최대 8초, 확인 즉시 정지, 기존 제스처·차단 안내·컨텍스트 재사용·종료 정리를 유지한다. 배음 파형도 컨텍스트마다 재사용한다.
- 화면: 금속 케이스, 분할 LED 렌즈, 빨강·파랑의 교대 점멸과 빛 번짐. DOM/키보드 처리 변경 없이 CSS로 구현한다. `prefers-reduced-motion`은 양쪽 렌즈와 후광을 모두 정지시킨다.
- ERP 공용 화면·도면 마법사·실측 지도 자산 버전을 `20261019a`로 동기화했다.

## 검증

- 관련 JS·공용 배선·성능 회귀 테스트: 38 passed.
- 화면 구조(`test_p1_mockup_structure`, home/chrome parity)·관련 JS·성능·하네스 drift·파일 크기 계약 통합: **105 passed, 1 warning (9.46s)**. 경고는 SQLite에서 기존 shipment dashboard의 PostgreSQL DISTINCT ON 사용 관련 SQLAlchemy deprecation이다.
- `python tools/perf/perf_scan.py --guard`: high=0, medium=0.
- SQLite 메모리 환경 앱 import: **APP_OK**. 로컬 Redis 미설정으로 single-worker 안내가 출력됐다.
- `git diff --check`: 오류 없음.
- gstack browse 실제 Chromium, DB 없는 loopback fixture: 1280×900 / 390×844에서 화면 확인. 실제 AudioContext state=running, peak≈0.12. 확인 후 peak=0, 오버레이 제거·mock ack 1회. 8초 자연 종료 후 peak=0, 확인 전 오버레이 유지. 콘솔 오류 없음.
- CDP로 reduced-motion을 적용: 빨강/파랑/후광 모두 computed animationName=none. 검증 후 미디어 override 해제.
- 실제 production JS를 별도 OfflineAudioContext에서 렌더: 48kHz·8.25초·396000 samples, peak=0.11999999, 8초 이후 tailPeak=0. 마지막 0.25초는 정지 검증용 무음이다.
- 로컬 산출물: `.gstack/us-police-qa/desktop.png`, `mobile.png`, `us-police-siren.wav`, fixture·probe·render script. 브라우저 자동화가 사용하는 헤드리스 오디오 신호를 측정했으며 실제 스피커를 청취한 결과는 아니다.
- 실제 Android/iOS 스피커·잠금화면 미검증. 운영 접근·커밋·푸시·배포 미실행.
- 이 checkout에는 gstack bridge의 `tools/harness/task_classifier.py`, `run_codex.ps1`이 없어 기존 pytest/perf 하네스와 설치된 gstack browse 런타임을 직접 사용했다.

## 설계 참고

- [Whelen의 Wail/Yelp/Priority 음색 분류](https://www.whelen.com/auditory-warning)
- [Web Audio 주파수 곡선 예약](https://developer.mozilla.org/en-US/docs/Web/API/AudioParam/setValueCurveAtTime)
