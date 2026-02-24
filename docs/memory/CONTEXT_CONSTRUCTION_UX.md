# 시공 대시보드 UX 수정 맥락

## 기술적 결정
1. **display_stage vs workflow.stage**: 시공 대시보드는 ERP 전체 워크플로우의 `stage`(CONSTRUCTION, CS 등)를 그대로 쓰지 않고, 시공 전용 구간을 **시공대기 / 시공중 / 시공완료**로 나눔. 구분 기준은 `workflow.history`에 '시공 시작' 노트 존재 여부(`is_started`)와 `stage` 값. 프론트 상세 로드 시에도 동일 규칙으로 displayStage를 계산해 버튼을 분기함.
2. **필터 폼 stage 옵션**: 시공 대시보드 필터는 메인 ERP 대시보드와 별개이므로, 프로세스맵 타일 값(시공대기/시공중/시공완료)을 그대로 쓸 수 있도록 select 옵션에 추가함. 타일 클릭 시 `applyFilter('stage', value)`로 같은 name의 select를 설정하고 submit하므로, 옵션이 없으면 값이 무시될 수 있음.
3. **시공 완료 후 stage**: API는 기존 정책대로 `stage = 'CS'`로 두고, 시공 대시보드 뷰에서만 `CS`를 시공완료로 해석해 표시함. 메인 ERP의 완료 탭은 `COMPLETED` 등 별도 매핑을 사용할 수 있음.
4. **시공 사진 업로드**: 완료 처리 모달에서 파일 선택 후 기존 R2 직접 업로드(session → PUT → finalize)를 사용하며, `category: 'construction'`으로 저장해 공통 첨부의 '시공' 카테고리와 동일하게 처리함.
