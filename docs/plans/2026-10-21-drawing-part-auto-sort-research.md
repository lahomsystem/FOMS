# 도면 그림 조각 자동 분류 · 정렬 조사 (2026-10-21)

> 상태: 조사·실험 기록. 코드 변경 없음. 마법사에 붙이는 일은 코어 변경이라 Spec → 승인 → 구현 순서를 따른다.
> 캔버스: https://claude.ai/artifact/Lq4yYvxX7YV3YJoZBr7uQ5 (첫 페이지 J01~J11 · R1 검토표 · R2 자동 분석 · K2 마법사 화면)

## 0. 이 문서가 답하는 질문
- 사용자 요청(10-21): "AI가 파트를 보고 무엇인지 파악해서 나눠 주게 할 수 있나? 무료 AI 라이브러리가 있는지 찾아봐" + "시트 자동 자르기 뿐만 아니라, 여러 모듈을 주면 자동 분석해서 정렬".
- 방법: 무료 AI 조사는 워크플로(조사 4갈래 + 갈래마다 반박 검증 + FOMS 코드 조사 + 종합, 10 에이전트)로 병렬 처리. 실험은 총괄이 샘플 11장으로 직접 했다.

## 1. 총괄이 직접 잰 값 (샘플 11장, numpy·scipy만, 새 패키지 없음)
- 시트 자동 자르기: 새 샘플 9장에서 사진 · 자재표 · 큰 그림 · 작은 상세를 거의 다 분리. 사진과 빗금을 가르는 기준은 "어두운 점 비율 0.12 이상 + 밝기 다양함(엔트로피 3.5 이상)". 가까이 붙은 작은 부품(사선장 10개)은 덩어리로 묶였다.
- 그림 조각 62장(새 9장 39 + 앞서 자른 주방 2장 23)을 그림 한 장만 보고 판단한 결과:
  - 사진/그림 62/62 · 정면/입체 48/52 · 큰 그림/상세 50/53 · 서랍 단면/부품 13/14 · 내부/도어 21/30
  - 붙박이장 · 수납장류는 내부/도어까지 거의 맞음. 주방은 내부/도어 14개 중 7개 — 회색(포그그레이) 도어를 빗금으로 착각, 큰 그림이 많아 크기 기준이 흔들림.
  - 규칙은 같은 11장에 맞춰 다듬었으므로 새 도면에서는 더 낮게 나올 것. 규칙에는 '모르겠다'가 없다(음성 대조군 미실시).
- 자동 정렬: 11개 제품 모두 같은 틀에 자동 배치. 틀 두 가지(위 띠형 · 왼쪽 기둥형)를 다 계산해 큰 그림이 크게 나오는 쪽을 고름. 큰 그림 크기는 지금 도면 대비 89~124%(평균 약 105%), 겹침 · 칸 밖 0건(숫자 검사). 사람 손질 2건(모네 사선 도어 모양을 상세로, 하부장 평면/상판 이름).

## 2. 조사 종합 (워크플로 결과 — 라이선스는 갈래마다 다른 에이전트가 공식 자료로 재확인, 총괄은 코드 앵커만 직접 대조)
## 1. 결론 한 줄

**됩니다. 다만 "AI가 처음부터 알아서 맞히는" 방식은 아니고, 우리 도면 수십 장으로 가르친 작은 모델에 간단한 규칙을 섞는 방식이어야 합니다. 그리고 확신이 낮은 그림은 사람이 고르게 해야 합니다.**

기대 정확도는 이렇습니다. 모두 추정이며 PoC로 직접 재야 합니다.
- **사진 / 자재표 / 도면, 이 세 갈래:** 거의 다 맞힐 것으로 봅니다. 색과 글자 패턴만으로도 갈리기 때문에 AI가 없어도 됩니다.
- **도면 종류 7가지**(정면-내부, 정면-문, 아이소, 평면, 상판, 서랍 단면, 부품 상세): 종류마다 30~50장씩 가르치면 80~95% 정도로 봅니다.
  - 렌더 스타일이 아주 일정하고, 빗금·30도 선·윤곽선만 있는 상판처럼 뚜렷한 단서가 있어서 높게 기대할 수 있습니다.
  - 다만 같은 문제를 잰 논문은 찾지 못했습니다.
  - 가까운 근거는 적은 예시로 가르친 쪽이 설명만 주고 맞히게 한 쪽을 크게 이긴다는 것입니다(CLIP 논문, CoOp 논문).
  - 제조 검사 사례도 있습니다. 쉬운 과제는 종류당 10~50장에서 0.94~0.97이 나왔습니다. 하지만 어려운 과제는 10장에서 0.57, 여러 부품이 섞인 장면은 50장에서 0.58에 그쳤습니다(https://arxiv.org/html/2501.12596v1).
  - 그래서 "90%대"는 약속할 수 없는 수치입니다.
- **어느 가구 부위인지**(키큰장, 상부장, 하부장, 옷장): 그림만 보고는 정확도가 낮을 것입니다. 그런데 마법사는 이미 시트마다 제품이 정해져 있습니다(`product_index`, `foms/api/drawing/wizard.py:556-569(총괄 정정 — 조사 보고의 249-262는 틀린 줄)`). 그래서 제품 정보, 그리고 OCR로 읽은 가장 큰 높이 치수(예: 2357 대 904)로 정하고 사람이 확인하는 쪽이 맞습니다.

## 2. 단계 계획

### 0단계: AI 없이 규칙부터 (바로 가능, 난이도 낮음)

이 단계에서는 규칙이 AI보다 낫습니다.
- **파일명 규칙:** 도면팀이 SketchUp 장면 이름을 정해진 형식(예: `정면_내부`, `아이소_문`)으로 쓰고, 파일을 끌어다 놓거나 파일 선택으로 넣으면 100% 맞습니다. 붙여넣기(Ctrl+V)를 하면 파일명이 `image.png`로 바뀌어 사라집니다(`c:\DEV\FOMS\static\js\drawing\wizard.js:2860`).
- **실측 사진 패널에서 가져온 그림:** 출처 자체가 현장 사진이므로 무조건 왼쪽 현장 사진 자리로 보냅니다(`wizard.py:948` import-attachment).
- **현장 사진 판별:** 색이 진하고 많으면 사진입니다. 이미 설치된 Pillow와 numpy로 됩니다.
- **자재표 판별:** OCR로 `[SR]`, `[DOOR]` 같은 대괄호 머리글이나 `숫자*숫자=숫자` 꼴 줄이 2개 이상 나오면 자재표입니다.
  - OCR 도구는 RapidOCR 3.10.0(Apache-2.0)에 PP-OCRv5 한국어 모델(Apache-2.0)을 씁니다.
  - 반드시 한국어 모델을 따로 지정해야 합니다. 기본값인 PP-OCRv6는 한국어를 못 읽습니다.
- **어디서:** 규칙은 브라우저에서, OCR은 Railway WORKER에서 돌립니다.

### 1단계: 학습용 그림 모으기와 예전 시트 나누기 (사무실 PC에서 한 번에 처리, 난이도 중간)

- **마법사로 만든 시트는 나눌 필요가 없습니다.** 그림마다 원본 파일(R2 key)과 위치가 이미 저장되어 있습니다(`wizard.py:368-382`).
- **마법사 이전 PNG 시트만 OpenCV로 나눕니다.**
  - 도구는 opencv-python-headless(Apache-2.0, Windows 휠 43.8MB)입니다.
  - 순서는 바깥 틀과 제목칸 지우기 → 잉크 번지기 → 덩어리 찾기입니다.
- **로컬 시험 결과(샘플 3장, 조사 담당이 직접 잰 값이며 다시 재지는 않음):**
  - 설정 A: 13.png 5/5, 20.png 12/12, 15.png(주방) 6/13
  - 설정 B: 15.png 12/13, 20.png 작은 부품 3/10
  - 설정 하나로는 3장을 다 맞히지 못했습니다. 그래서 두 설정을 같이 돌리고, 결과가 다른 곳만 사람이 보게 합니다.
  - 처리 시간은 한 장에 1초 안팎이었습니다.
- **제목칸(고객 이름, 전화, 주소)은 학습 데이터에서 반드시 버립니다.**
- **PDF 시트:** pdfplumber(MIT)는 그림의 위치만 알려 주고 그림 자체는 꺼내 주지 않습니다. PyMuPDF는 AGPL이라 쓰면 안 됩니다.

### 2단계: 그림 종류 분류기 PoC (사무실 PC CPU로 충분, 난이도 중간)

- **이미지 모델로 그림마다 숫자 묶음(임베딩)을 뽑습니다.** 후보는 셋입니다.
  - DINOv2-small(코드·가중치 Apache-2.0, 22.1M, ONNX int8 24.4MB): 1순위입니다. 작고 라이선스가 깨끗하며 선 그림의 구조를 잘 잡는다는 보고가 있습니다.
  - SigLIP 2 base vision(Apache-2.0, ONNX q8 94.6MB): 비교 대상입니다. 근거로 쓴 스케치 점수 67.9%는 SigLIP 2가 아니라 SigLIP 1의 수치입니다.
  - PE-Core-S/B(Meta, Apache-2.0): 비교 대상입니다. 공식 ONNX가 없어서 직접 변환해야 하고, 선 그림 성능은 미확인입니다.
- **그 위에 아주 작은 분류기를 학습합니다.** scikit-learn(BSD-3-Clause)의 로지스틱 회귀나 k-NN을 씁니다. 결과물은 수십 KB짜리 숫자 표입니다.
- **간단한 숫자 특징을 함께 넣습니다.**
  - 가로세로 비율, 원본 크기
  - 회색 빗금 비율 → 정면-내부와 정면-문을 가르는 데 씁니다
  - 30도 기울어진 선의 비율 → 아이소와 정면을 가르는 데 씁니다
- **전처리 주의:** 기본 전처리는 그림 가운데만 잘라내거나 찌그러뜨립니다. 반드시 흰 여백을 채워 정사각형으로 만든 뒤 넣습니다.
- **기대 정확도:** 도면 종류 7가지에서 80~95%(추정).

### 3단계: 마법사에 붙이기 (브라우저 우선, 난이도 중간~높음)

- **실행 방법:** 이긴 모델을 ONNX q8로 바꾸고 Transformers.js(Apache-2.0, 4.3.1) WASM으로 브라우저에서 돌립니다. 분류기 가중치는 JSON으로 내려보내 JS에서 계산합니다.
  - 그림이 분류 때문에 서버로 따로 가지 않습니다.
  - 서버 비용이 0입니다.
  - 첫 접속 때 약 24MB를 내려받습니다.
- **붙일 위치:** `wizard.js:2920-2925`입니다. 업로드가 끝나 key를 받은 직후 분류하고, 해당 라벨 근처 좌표를 pos로 넘겨 `placeImageFromKey`를 부릅니다. 여러 장을 한꺼번에 넣을 때는 `addImagesFromFiles`(`:2932`)에서 모아서 분류합니다.
- **확신이 낮으면 자동 배치하지 않고 "미분류" 칸에 둡니다.** 기준 확률은 0.7 정도로 시작하고 실제 값은 PoC에서 정합니다.
- **2순위 실행 위치:** Railway WORKER에서 onnxruntime(MIT, 1.31.0)으로 돌립니다. 웹 프로세스에서 돌리면 그동안 요청 처리가 멈춥니다(gevent 2 workers). 또 torch를 넣으면 Dockerfile 하나로 만드는 서비스 4개가 모두 무거워지므로 넣지 않습니다.
- **주의할 점:**
  - 이미지 객체에 `part` 필드를 추가하면 저장 형식(`wizard.js:3950`)과 서버 검증(`wizard.py:368-382`)이 바뀝니다. 핵심 변경이므로 Spec → 승인 → 구현 순서를 따릅니다.
  - 서버에 새 API를 만들면 세 곳에 등록해야 합니다: `request_limits.py`, `foms_write_guard_manifest.json`, `foms_order_mutation_policy_manifest.json`.

### 4단계: 사람이 고친 결과로 계속 좋아지기 (난이도 중간)

- **고친 결과를 다시 학습합니다.** 사람이 그림을 다른 섹션으로 옮기면 그것이 정답 보정 신호가 됩니다. k-NN은 예시를 추가하기만 해도 바로 반영됩니다.
- **종류당 수백 장이 쌓이면 다음으로 넘어갈 수 있습니다.**
  - timm MobileNetV3-Large / EfficientNet-B0 미세조정(코드 Apache-2.0): ImageNet으로 학습된 가중치라 라이선스가 조건부입니다. 법무 확인이 필요합니다.
  - 시트 나누기와 종류 판별을 한 번에 하는 RF-DETR Nano/Small(Apache-2.0): 사무실 GTX 1660 SUPER 6GB에서 학습할 수 있다고 공식 문서에 적혀 있습니다.
- **생성형 VLM은 라벨 붙이기 도우미로만 사무실 PC에서 씁니다.** 운영 판정에는 쓰지 않습니다.
  - Qwen3.5-4B(Apache-2.0, Ollama q4_K_M 3.3GB, 생각 모드 끔), 대안은 Qwen3-VL-4B-Instruct입니다.
  - 숫자를 그럴듯하게 지어낼 수 있습니다.
  - GTX 1660 계열은 PyTorch fp16에서 NaN 문제가 보고되어 있으니 Ollama/GGUF로 돌립니다.

## 3. 학습 데이터 확보 방법

**FOMS 안에 이미 있는 것** (DB 조회는 아직 하지 않았고, 건수를 세는 SQL은 코드 조사 보고서에 실행 전 상태로 있습니다)
- **마법사 시트의 그림 객체:** R2 원본 파일(key)과 시트 위 좌표가 있습니다. 같은 시트의 `[DOOR]` 같은 라벨 글자와의 거리로 약한 정답을 추정할 수 있습니다.
- **전달 때 남은 시트 사본:** `drawing_wizard/versions/` 아래에 있고, 주문당 최대 30개입니다.
- **합본 PNG:** `drawing_wizard/exports/`와 주문 첨부(category='drawing')에 있습니다. 마법사 이전 시트를 나누는 재료가 됩니다.
- **감사 로그 `DRAWING_WIZARD_ASSET_ADDED`의 원래 파일명:** SketchUp 장면 이름이 남아 있으면 약한 정답이 됩니다. AUDIT-LOG T8 이후 기록만 있습니다.
- **캔버스에서 지운 그림도 R2에 남아 있습니다.**
- **한계:** "이 그림이 무슨 종류인지" 적힌 값은 어디에도 없습니다. 그래서 처음 정답은 사람이 붙여야 합니다.

**앞으로 쌓는 방법**
- **처음 정답 붙이기:** 종류별 폴더에 30~50장씩 넣는 것으로 충분합니다. 종류 9~12개면 300~600장입니다. 양이 수천 장으로 늘면 Label Studio(Apache-2.0)나 CVAT Community(MIT)를 사내에 설치합니다. 클라우드판은 쓰지 않습니다.
- **VLM이나 2단계 분류기로 먼저 라벨을 달고, 사람은 고치기만 합니다.**
- **운영에 들어가면** 이미지 객체에 `part`(그리고 자동/사람 구분)를 저장합니다. 사람이 옮긴 기록이 다시 학습할 데이터가 됩니다.
- **가장 빠른 길:** 도면팀이 갖고 있는, 시트에 붙이기 전의 낱장 PNG를 받는 것입니다.

## 4. PoC 제안

**설치할 것** (사무실 PC에 한정. 설치 전에 사용자에게 이름과 이유를 먼저 확인받습니다)
- **pip 패키지:**
  - `onnxruntime` 1.31.0 (MIT): Linux 휠 23.8MB, Windows 크기는 미확인
  - `scikit-learn` (BSD-3-Clause): 크기 미확인
  - `opencv-python-headless` (Apache-2.0): Windows 43.8MB
  - `rapidocr` 3.10.0 (Apache-2.0): 27.3MB. 모델은 modelscope.cn에서 받게 되어 있으니 미리 받아 로컬 경로로 지정합니다.
  - numpy와 Pillow는 이미 있습니다.
- **모델 파일:** Hugging Face에서 내려받기만 하고, 그림은 올리지 않습니다.
  - `onnx-community/dinov2-small`: `model_quantized.onnx` 24.4MB
  - `onnx-community/siglip2-base-patch16-224-ONNX`: `vision_model_quantized.onnx` 94.6MB만 받습니다. 통합 파일은 378MB이니 받지 않습니다.
- **선택(VLM 비교용):** Ollama와 `qwen3.5:4b` (3.3GB).
- **나중에 브라우저용 npm:** `@huggingface/transformers` 4.3.1 (크기 미확인).

**실험 순서**
1. 샘플 11장을 OpenCV로 나눕니다. 두 설정을 같이 돌리고 사람이 보정해서 조각 그림 약 100장과 정답을 만듭니다.
2. **기준선:** 파일명 없이 "가로세로 비율 + 빗금 비율 + 30도 선 비율"만으로 분류기를 만듭니다. AI는 이 점수를 이겨야 의미가 있습니다.
3. DINOv2-small과 SigLIP 2를 각각 임베딩만 쓴 경우, 그리고 임베딩에 간단 특징을 더한 경우로 로지스틱 회귀와 k-NN을 돌립니다.
4. 평가는 시트 단위로 하나씩 빼는 교차검증(leave-one-sheet-out)으로 합니다. 같은 시트의 그림이 학습과 시험에 섞이면 점수가 부풀기 때문입니다. 혼동표를 만듭니다.
5. 사진과 자재표 규칙, OCR 단서를 합쳐 최종 정확도를 냅니다.
6. 걸린 시간을 잽니다. 기준은 사무실 PC CPU이며, 브라우저 WASM은 다음 단계에서 잽니다.

**통과 기준**
- 사진 / 자재표 / 도면 세 갈래: 98% 이상
- 도면 종류 7가지: 정답률 85% 이상
- 확신이 기준 이상인 것만 자동 배치했을 때, 자동 배치한 것의 정확도 95% 이상, 자동 처리 비율 70% 이상
- 시트 나누기: 11장 전체에서 그림 90% 이상을 정확히 분리. 실패한 곳은 모두 "사람 확인" 표시가 붙어야 합니다.
- 장당 분류 시간: 1초 이내(CPU)
- 2번 기준선보다 10%p 이상 높아야 합니다.

**음성 대조군** (모두 같은 도면 모집단 안에서 고릅니다)
- **정답 섞기 시험:** 정답을 무작위로 섞어 학습시키면 우연 수준(약 1/9)으로 떨어져야 합니다. 떨어지지 않으면 데이터가 새고 있다는 뜻입니다.
- **종류 밖 조각:** 같은 시트에서 잘라 낸 제목칸, 머리말 글자, 빈 조각, 로고 조각을 넣었을 때 "미분류"로 빠지는 비율이 80% 이상이어야 합니다.
- **양식이 다른 시트:** EHAUS/LAHOM 판을 따로 모아 점수가 크게 떨어지는지 봅니다.

## 5. 쓰면 안 되는 것과 이유

**라이선스 문제**
- **Ultralytics YOLO 전부, YOLOv10, DocLayout-YOLO(AGPL-3.0), YOLOv9, YOLO-World(GPL-3.0):** 사내 비공개 ERP에 넣으면 소스 공개 의무 위험이 있습니다. 같은 일을 하는 Apache 대안이 있습니다.
- **연구 전용이거나 비상업 전용:**
  - MobileCLIP/MobileCLIP2, Apple DFN CLIP
  - MetaCLIP(CC-BY-NC-4.0)
  - XRay-DINO, Cell-DINO(DINOv2 저장소 안의 비상업 가중치)
  - Qwen2.5-VL-3B(Qwen Research License. llama.cpp 공식 목록에 있어서 명령어를 복사하면 그대로 받게 됩니다)
  - InternVL2.5-4B, VARCO-VISION, KLOCR
- **조건이 붙은 것:**
  - Surya: 매출이나 투자가 500만 달러를 넘으면 쓸 수 없고, 출력물에도 조건이 걸립니다.
  - LFM2-VL: 연매출 1천만 달러 기준이 있습니다.
  - DEIMv2: 자체 라이선스이고 상업 사용은 문의하라고 되어 있습니다.
  - RF-DETR의 XL/2XL/Atto/Femto/Pico 크기(PML-1.0): Roboflow 계약이 필요합니다. N/S/M/L만 씁니다.
  - Moondream 3(BSL 1.1)
- **대한민국 사용 불가:** HunyuanOCR, BrainOCR. 라이선스에서 대한민국이 제외되어 있습니다.
- **기본값으로 쓰지 않는 것(법무 확인 전):**
  - DINOv3: 맞춤 라이선스이고 받을 때 게이트가 있습니다.
  - OpenAI CLIP, LAION 체크포인트: 모델 카드에 "배포 용도는 범위 밖"이라는 권고가 있습니다.
  - Gemma 3, PaliGemma 2: Google이 원격으로 사용을 제한할 수 있는 조항이 있습니다.
  - Kanana, HyperCLOVA X: "Powered by" 표시 의무가 있습니다.
  - ConvNeXt-Tiny(Facebook 가중치): timm README에 비상업 경고가 있습니다.
  - Detectron2 Model Zoo: CC BY-SA 3.0입니다.
  - PyMuPDF: AGPL입니다.

**개인정보 문제**
- 고객 그림을 온라인 데모, HF Space, 외부 API에 올리면 안 됩니다(Gemini, GPT-4o, Grounding DINO 1.5/1.6 클라우드, MiniCPM 공개 API 포함).
- 시트 제목칸은 학습과 OCR 대상에서 제외합니다.

**속도와 크기 문제**
- **6GB 카드나 Railway CPU에 맞지 않는 것:** SAM 3(848M), Llama 3.2 Vision 11B, Gemma 4 E4B(6.1GB 이상), DeepSeek-OCR 2, PaddleOCR-VL을 GTX 1660에서 돌리는 경우(vLLM은 CC 8.0 이상이 필요하고, 직접 실행하면 GPU 메모리 7.9GB 실측).
- **유지보수가 멈추거나 한글이 약한 것:**
  - EasyOCR: 한글이 913자뿐이라 "쿡", "캡"을 못 읽습니다.
  - docTR: 한글 모델이 없습니다.
  - LayoutParser: 2022년 이후 멈췄습니다.
- **생성형 VLM을 운영 판정에 쓰는 것:** 숫자를 지어낼 수 있고, CPU에서 이미지 한 장에 수십 초가 걸릴 수 있습니다.

## 6. 남은 의문

1. **"파트 섹션"이 무엇인지 먼저 정해야 합니다.** 지금 코드에 있는 섹션은 자재 라벨 5개(`[SR] [EP] [DOOR] [옷봉] [마이다]`, `wizard.js:60`)입니다. 그림 종류(정면, 아이소, 평면 등)와는 다릅니다. 시트 위 어느 칸에 어떤 종류를 둘지 배치 규칙부터 정해야 합니다.
2. **도면팀이 SketchUp 장면 이름을 정해진 형식으로 쓰고 끌어다 놓기로 바꿀 수 있다면,** 그것만으로 대부분 해결됩니다. AI는 붙여넣기를 하는 경우를 위한 보조가 됩니다. 이 방법이 가능한지 확인이 필요합니다.
3. **과거 데이터 양:** 위 SQL로 이미지 객체 수, 파일명 단서, 합본 PNG 수를 세어야 합니다. 마법사 이전 시트가 어떤 형식(PNG, PDF, PPT)으로 몇 장 있는지도 알아야 합니다.
4. **도면팀 PC 사양:** 브라우저에서 WASM/WebGPU가 어느 정도 속도로 도는지 실측이 없습니다. Railway WORKER의 메모리 여유도 확인해야 합니다.
5. **틀렸을 때의 비용:** 자동 배치 뒤 사람이 확인하는 흐름이면 85~90%로 충분한지, 기준 확률을 얼마로 둘지 정해야 합니다.
6. **샘플 11장에 없는 종류**(손잡이 상세, 거울·유리 상세, 조명 위치도 등)가 더 있는지 확인해야 합니다.
7. **가구 부위를 가르는 높이와 폭 치수 기준**을 FOMS가 정해 줄 수 있는지 확인해야 합니다.
8. **아직 확인하지 못한 수치:**
   - DINOv2-small의 CPU 속도
   - SigLIP 2 자체의 스케치 성능
   - PE-Core의 선 그림 성능
   - 아이소 그림에 30도로 기울어진 치수 글자가 있을 때의 OCR 정확도
   - 브라우저에서 PaddleOCR.js가 한국어 모델로 실제 도는지
   - 이 수치들은 PoC에서 재야 합니다.
9. **중국 회사 모델(Qwen, OpenBMB) 사용에 회사 정책상 제한이 있는지** 확인해야 합니다. 제한이 있으면 VLM 도우미는 Gemma 4 E2B나 Ministral 3 3B(둘 다 Apache-2.0)로 바꿉니다.

이번 조사에서는 패키지를 설치하지 않았고, 파일도 고치지 않았습니다. 이미지는 어디에도 올리지 않았습니다. 시트 나누기 시험 결과 그림은 C:\Users\USER\AppData\Local\Temp\claude\c--DEV-FOMS\0a2dfb0b-85f4-43fd-8a82-9a74c53e73ab\scratchpad\split_test\ 에 있습니다.

## 3. FOMS 코드 조사 원문 (앵커는 총괄이 일부 대조: wizard.js:60 · 2858 · 2868 · 2911 · 2932 확인, product_index 줄 정정)

## FOMS 도면 마법사에 "AI 파트 자동 분류"를 붙일 위치와 학습 데이터 조사 결과

**결론:** 붙여넣은 이미지는 한 함수(`addImagesFromFiles`)로 모이고, 배치 함수가 이미 위치(pos) 인자를 받습니다. 그래서 분류 결과로 위치만 정해 넘기면 되고, 고칠 곳은 적습니다. 이미지 파일과 시트 위 좌표(x/y/w/h)는 남아 있습니다. 다만 그 이미지가 어느 파트인지 적힌 값은 어디에도 없습니다. 바로 쓸 수 있는 학습 데이터는 없고, 근처 라벨 텍스트로 추정해야 합니다. DB 조회는 하지 않았고, 건수 확인용 SQL은 맨 아래에 실행하지 않은 상태로 적었습니다.

### 0. "파트 섹션"이 무엇인지
- 기본 라벨 5개가 코드에 박혀 있습니다: `PRESETS = { SR:'[SR]', EP:'[EP]', DOOR:'[DOOR]', ROD:'[옷봉]', MAIDA:'[마이다]' }` — `c:\DEV\FOMS\static\js\drawing\wizard.js:60`
- 새 시트를 만들면 이 라벨들이 y=120, x≈628/798/968/1138/1308 위치에 자동으로 깔립니다 — `c:\DEV\FOMS\static\js\drawing\wizard.js:61-65`, `:306-317`
- 왼쪽 빈칸은 현장 사진 자리라고 코드 주석에 적혀 있습니다 — `c:\DEV\FOMS\static\js\drawing\wizard.js:309`
- 아직 내용을 안 쓴 라벨인지 판별하는 함수가 있습니다 — `c:\DEV\FOMS\static\js\drawing\wizard.js:333`
- 사용자가 추가한 라벨은 SystemSetting 키 `drawing_wizard_presets`에 전역으로 저장됩니다 — `c:\DEV\FOMS\foms\services\drawing_wizard_presets.py:1-8`, `:55`
- 시트는 주문의 제품 하나에 대응합니다(`product_index`) — `foms/api/drawing/wizard.py:556-569(총괄 정정 — 조사 보고의 249-262는 틀린 줄)`

### 1. 이미지가 들어오는 경로
- **화면 요소:** 파일 선택 버튼 `c:\DEV\FOMS\templates\drawing\wizard.html:72-75`, 실측 사진 패널 `:187-192`, 스크립트 로드 `:604-606`
- **들어오는 길 3개가 한 함수로 모입니다:**
  - 붙여넣기 `c:\DEV\FOMS\static\js\drawing\wizard.js:5150-5184` (5181에서 `addImagesFromFiles(blobs)` 호출)
  - 드래그앤드롭 `:3041-3058` (놓은 지점 좌표를 같이 넘김)
  - 파일 선택 `:5030-5033`
- **처리 순서:**
  1. `addImagesFromFiles` `:2932-2943`
  2. `addImageFromFile` `:2911-2927` (10MB 초과는 업로드 전에 거부)
  3. `uploadAsset` `:2858-2862` → `POST /api/orders/<id>/drawing-wizard/asset`
  4. `placeImageFromKey(key, pos, cascade, maxLong)` `:2868-2909`
- **서버:** `c:\DEV\FOMS\foms\api\drawing\wizard.py:881-945`
  - 확장자는 png/jpg/jpeg/webp/gif만 허용 (`:85`)
  - Pillow로 흰 여백을 잘라낸 뒤 저장합니다 (`:910-917`, `c:\DEV\FOMS\foms\services\image_margin_trim.py:23-28`)
  - 주문 첨부(OrderAttachment) 행은 만들지 않고 R2에만 올립니다
  - 업로드마다 감사 로그 `DRAWING_WIZARD_ASSET_ADDED`가 남습니다 (원래 파일명 + 저장 키, `:925-932`)
- **R2 저장 키 형식:** `orders/<id>/drawing_wizard/assets/<YYYYmmdd_HHMMSS>_<uuid8>_<secure_filename>` — `c:\DEV\FOMS\foms\services\storage.py:452-456`
  - `secure_filename`이 한글을 지워서, 키에는 한글 파일명이 남지 않습니다. 원래 파일명은 감사 로그에만 있습니다.
  - 붙여넣은 이미지는 파일명이 `image.png`나 `paste-<ts>.png`(`wizard.js:2860`)라서 단서가 되지 않습니다.
- **이미지 원본 조회:** `GET .../drawing-wizard/asset-raw` — `c:\DEV\FOMS\foms\api\drawing\wizard.py:1636-1661`

### 2. 저장 방식 (학습 데이터가 있는지)
- **시트 상태:** `PUT /api/orders/<id>/drawing-wizard` — `c:\DEV\FOMS\foms\api\drawing\wizard.py:726-857`
  - `orders.structured_data`(JSONB) 안의 `['drawing_wizard']` 키에 저장합니다 (`c:\DEV\FOMS\models.py:17`, `:101`)
  - 저장할 때마다 덮어쓰므로 DB에는 최신본만 있습니다 (`wizard.py:786-795`)
  - 모양: `{v:1, sheets:[{id, name, form, objects:[...], product_index?, attachment_id?, presets_seeded?}], pending:{}, versions:[], updated_at, updated_by...}`
  - 제한: 시트 10장, 시트당 객체 200개, 전체 64KB (`wizard.py:75-77`)
- **이미지 객체 1개:** `{id, type:'image', x, y, w, h, key, natural_w, natural_h, rotation, locked?, flipX?, flipY?}`
  - 화면 쪽 저장 형식 `c:\DEV\FOMS\static\js\drawing\wizard.js:3950-3955`, `:4030-4048`
  - 서버 검증 `c:\DEV\FOMS\foms\api\drawing\wizard.py:368-382`, `:462-495`
- **즉, 이미지는 낱장 파일로 R2에 있고 시트 위 좌표도 남아 있습니다.**
- **전달 시점 이력:** 시트 JSON이 `orders/<id>/drawing_wizard/versions/v<n>_<sheet_id>.json`으로 저장되고, 목록은 `drawing_wizard.versions`에 주문당 최대 30개까지 남습니다 — `wizard.py:84`, `:1152-1187`, `:1202-1260`, `:1512-1585`
- **합쳐진 PNG 한 장도 따로 저장됩니다:**
  - 저장 위치 `orders/<id>/drawing_wizard/exports/` — `wizard.py:1014-1124`
  - 전달 대기 목록 `drawing_wizard.pending`과 `drawing_wizard_pending` 테이블 — `c:\DEV\FOMS\models.py:3038-3077`
  - 전달하면 주문 첨부(category='drawing') 행이 생깁니다 — `c:\DEV\FOMS\foms\api\drawing\erp_orders_drawing.py:304-315`
- **한계:**
  - 이미지별 "이게 어떤 파트인지" 필드가 없습니다. 저장 형식이 필드를 정해진 것만 남깁니다 (`wizard.js:3948-3956`).
  - 라벨이 필요하면 같은 시트의 `[DOOR]` 같은 라벨 텍스트와의 거리, 또는 시트의 제품명으로 추정해야 합니다.
  - 캔버스에서 지운 이미지 파일도 R2에 그대로 남습니다. 지워지는 건 주문 전체를 삭제할 때뿐입니다 (`c:\DEV\FOMS\foms\services\order_storage_cleanup.py:107-120`).
  - 감사 로그의 구조화 컬럼은 AUDIT-LOG T8 이후 기록에만 채워져 있습니다 (`c:\DEV\FOMS\models.py:1379-1414`).

### 3. 실측 사진 패널의 출처
- 마법사를 열 때 `GET /api/orders/<id>/drawing-wizard` 응답의 `measure_photos`로 받습니다 — `c:\DEV\FOMS\foms\api\drawing\wizard.py:642`
- 이 목록은 `_build_measure_photos`가 만듭니다 — `wizard.py:265-297`
  - 주문 첨부 중 category가 `measurement`, `measure_photo`, `photo`인 것을 최신순으로 모읍니다 (`wizard.py:107`)
  - 범위를 벗어난 `item_index`는 공통 사진으로 처리하고, 썸네일 주소는 `/api/files/view/<thumbnail_key|storage_key>`입니다
- 테이블은 `order_attachments`입니다 — `c:\DEV\FOMS\models.py:353-395` (item_index `:363`, item_id `:367`, storage_key `:382`, deleted_at `:392`)
- 화면 쪽 흐름:
  - 데이터 받기 `c:\DEV\FOMS\static\js\drawing\wizard.js:4149`
  - 썸네일 그리기 `:3194-3237`, 현재 제품 사진만 걸러내기 `:3183-3189`
  - 클릭하면 `POST .../import-attachment`(`wizard.py:948-1011`)로 assets 폴더에 복사한 뒤, 긴 변 480px로 배치합니다 (`wizard.js:3246-3267`)

### 4. 이미지·AI 관련 Python 패키지와 기존 AI 연동
- `c:\DEV\FOMS\requirements.txt` 기준:
  - 설치되어 있음: `numpy==1.26.4`(:56), `Pillow==12.3.0`(:61), `google-genai==2.8.0`(:134-135, 주석 "FOMS Brain AI provider")
  - 없음: opencv, onnxruntime, torch, transformers, anthropic, openai
- 실제로 쓰는 곳:
  - Pillow: 썸네일 생성(`c:\DEV\FOMS\foms\services\storage.py:33-39`)과 여백 자르기에서만 씁니다
  - numpy: 오프라인 스크립트 `c:\DEV\FOMS\tools\design\import_user_spade_icon.py` 하나에서만 씁니다
  - google-genai: 앱 코드 어디에서도 import하지 않습니다
- 예전 AI 연동은 삭제됐습니다:
  - Gemini 연동과 `drawing_template_classifier.py` 등이 들어 있던 `foms/services/designer/`는 커밋 75b00b653 "DESIGNER-RETIRE-01"(2026-07-24)에서 지워졌습니다
  - 오프라인 도구 `c:\DEV\FOMS\tools\designer\generate_expected_json.py:114-127`는 아직 지워진 모듈을 import합니다. 그래서 import 단계에서 실패할 것으로 보입니다(실행해 보지는 않음).
  - 이 도구의 프롬프트에 파트 코드 목록이 있습니다: `[SR]`, `[EP]`, `[DOOR]`, `[마이다]`, `[옷봉]` (`:58`)
  - DB의 `designer_*` 테이블과 pgvector 마이그레이션은 남아 있습니다 (`c:\DEV\FOMS\migrations\versions\designer_drawing_intake.py`, `designer_pgvector.py:56-64`)
  - `c:\DEV\FOMS\tests\domains\test_designer_retired.py`가 `/api/designer` 경로가 404인지 검사합니다. 새 기능은 이 경로를 쓰면 안 됩니다.
- `.env.example`에는 AI 키가 없고 R2 설정만 있습니다 (:40-47).
- 브라우저 쪽: 스크립트 출처를 막는 CSP(script-src)가 아직 없습니다 (`c:\DEV\FOMS\foms\platform\security_headers.py:10`). 그래서 브라우저에서 돌리는 WASM 모델이 CSP에 막히지는 않습니다.

### 5. Railway 서비스 구성
- 루트 `Dockerfile` 하나로 서비스 4개(web, worker, cron, sidefx)를 모두 빌드합니다 — `c:\DEV\FOMS\Dockerfile:3`, `:18-27`, `:47`, `c:\DEV\FOMS\railway-worker.toml:4-5`, `c:\DEV\FOMS\railway-cron.toml:17-22`, `c:\DEV\FOMS\railway-domain-sidefx.toml:9-14`
  - 따라서 torch를 추가하면 서비스 4개의 이미지가 모두 커집니다.
- `c:\DEV\FOMS\start.sh:9-27`: `USE_RQ_WORKER=1`이면 백그라운드 작업 감독 프로세스(rq 포함)를 띄우고, 아니면 `gunicorn -k gevent -w 2 --timeout 120`을 띄웁니다 (`c:\DEV\FOMS\Procfile:3,8`)
  - 웹 프로세스 안에서 CPU를 많이 쓰는 추론을 돌리면 그동안 요청 처리가 멈춥니다.
- 백그라운드 작업 등록 방식 예시: `c:\DEV\FOMS\foms\services\jobs\queue.py:37-54`, `:150-168`
- 새 API를 만들면 세 곳에 등록해야 합니다:
  - 요청 크기 제한 `c:\DEV\FOMS\foms\platform\request_limits.py:114-118`
  - `c:\DEV\FOMS\docs\harness\foms_write_guard_manifest.json:500-528`
  - `c:\DEV\FOMS\docs\harness\foms_order_mutation_policy_manifest.json:616-651`

### 붙일 위치 후보
1. **브라우저, 업로드 직후 (추천)**
   - `wizard.js:2920-2925`에서 업로드가 끝나면 key가 손에 들어옵니다. 여기서 분류한 뒤, 해당 라벨 근처 좌표를 pos로 넘겨 `placeImageFromKey`를 부르면 됩니다.
   - 라벨 위치는 현재 시트 객체 중 `isPresetPlaceholder`(`:333`)나 `[DOOR]`로 시작하는 텍스트를 찾아 정합니다.
   - 여러 장을 한꺼번에 나누려면 `addImagesFromFiles`(`:2932`)에서 먼저 모아 분류합니다.
2. **브라우저에서 모델 실행**
   - html2canvas를 필요할 때만 불러오는 방식(`wizard.js:37`, `:115-131`)을 그대로 따라 모델을 불러오면, 서버를 고치지 않아도 됩니다.
3. **서버, 기존 업로드 API**
   - `wizard.py:914`에서 이미 이미지 바이트를 메모리에 들고 있으므로, 응답(`:933-941`)에 `part`/`confidence`를 붙일 수 있습니다.
   - 외부 API 호출이나 가벼운 ONNX 모델만 적합합니다. 무거운 추론은 웹 프로세스를 멈춥니다.
4. **서버, 새 분류 API**
   - `POST .../drawing-wizard/classify {keys}`를 만들고 `storage.read_file_bytes`(`wizard.py:984-985`)로 이미지를 읽습니다. 위의 등록 3곳이 필요합니다.
   - 과거 데이터 일괄 처리나 미리 계산은 RQ 작업으로 WORKER 서비스에 맡깁니다.
5. **라벨을 저장해 앞으로의 학습 데이터 만들기**
   - 이미지 객체에 `part` 필드를 추가합니다: 저장 형식 `wizard.js:3950`, 불러오기 `:4067~`, 서버 검증 `wizard.py:368-382`
   - 사용자가 이미지를 다른 섹션으로 옮기면 그게 정답 보정 신호가 됩니다.
6. **현장 사진**
   - `import-attachment`(`wizard.py:948`)로 들어오는 실측 사진은 왼쪽 현장 사진 자리로 바로 보낼 수 있습니다.

### 과거 이미지 건수를 세는 SQL (PostgreSQL, 실행하지 않았음)
```sql
-- (A) 최신 상태 안에 배치된 이미지 수와 파트 라벨 텍스트 수
WITH sh AS (
  SELECT o.id AS order_id, s.value AS sheet
  FROM orders o
  CROSS JOIN LATERAL jsonb_array_elements(o.structured_data->'drawing_wizard'->'sheets') AS s(value)
  WHERE o.deleted_at IS NULL AND o.status <> 'DELETED'
    AND jsonb_typeof(o.structured_data->'drawing_wizard'->'sheets') = 'array'
), ob AS (
  SELECT sh.order_id, sh.sheet->>'id' AS sheet_id, x.value AS obj
  FROM sh CROSS JOIN LATERAL jsonb_array_elements(sh.sheet->'objects') AS x(value)
  WHERE jsonb_typeof(sh.sheet->'objects') = 'array'
)
SELECT COUNT(DISTINCT order_id) AS orders,
       COUNT(DISTINCT order_id || ':' || sheet_id) AS sheets,
       COUNT(*) FILTER (WHERE obj->>'type'='image') AS image_objects,
       COUNT(DISTINCT obj->>'key') FILTER (WHERE obj->>'type'='image') AS distinct_asset_keys,
       COUNT(*) FILTER (WHERE obj->>'type'='text'
                        AND obj->>'text' ~ '^\[(SR|EP|DOOR|옷봉|마이다)\]') AS part_label_texts
FROM ob;

-- (B) 월별 업로드 이력 (캔버스에서 지운 이미지 포함, T8 이후 기록만)
SELECT date_trunc('month', timestamp) AS month, COUNT(*) AS uploads, COUNT(DISTINCT target_id) AS orders
FROM security_logs
WHERE action = 'DRAWING_WIZARD_ASSET_ADDED' AND target_type = 'order'
GROUP BY 1 ORDER BY 1;

-- (B2) 원래 파일명을 약한 라벨로 쓸 수 있는지 확인
SELECT lower(detail->>'filename') AS fn, COUNT(*) FROM security_logs
WHERE action = 'DRAWING_WIZARD_ASSET_ADDED' GROUP BY 1 ORDER BY 2 DESC LIMIT 50;

-- (C) 전달 시점 버전 스냅샷 수
SELECT COUNT(*) AS snapshots, COUNT(DISTINCT o.id) AS orders
FROM orders o
CROSS JOIN LATERAL jsonb_array_elements(o.structured_data->'drawing_wizard'->'versions') v
WHERE jsonb_typeof(o.structured_data->'drawing_wizard'->'versions') = 'array';

-- (D) 전달된 합본 PNG 수와 실측 사진 수
SELECT category,
       COUNT(*) FILTER (WHERE storage_key LIKE 'orders/%/drawing_wizard/exports/%') AS wizard_png,
       COUNT(*) AS total
FROM order_attachments
WHERE deleted_at IS NULL AND category IN ('drawing','measurement','measure_photo','photo')
GROUP BY category;
```

## 4. PoC 실측 (2026-10-22, 사용자 승인 후)
- 환경: 세션 scratchpad 의 별도 가상환경(FOMS 개발 환경과 분리). onnxruntime 1.31.0 · scikit-learn 1.9.1 · opencv-python-headless 5.0.0.93 · rapidocr 3.10.0. 이 판들은 FOMS 고정값 numpy==1.26.4 와 함께 설치되지 않았다(pip 충돌 → numpy 2.x 필요) — 서버에 넣으려면 numpy 올리기가 따로 필요, 브라우저 실행이면 무관.
- 모델(내려받기만, 그림은 어디에도 안 올림): onnx-community/dinov2-small (fp32 88MB · int8 24MB), onnx-community/siglip2-base-patch16-224-ONNX 시각 부분 int8 95MB.
- 자료: 도면 14장 · 그림 조각 80장(사진 11 · 정면 내부 13 · 정면 도어 5 · 입체 내부 5 · 입체 도어 13 · 평면/상판 8 · 서랍 단면 10 · 부품 상세 15). 정답은 총괄이 붙임(1번 시트 부품 6개는 처음에 정면으로 잘못 붙였다가 그림을 보고 입체로 고침).
- 평가: 시트 하나씩 빼고 나머지 13장으로 가르친 뒤 뺀 시트를 맞힘(14번). 분류기 설정(C=2)은 미리 정하고 시험 결과로 고치지 않음. 전처리는 흰 여백으로 정사각형 → 224.
- 결과(8종 모두 맞아야 정답):
  - DINOv2-small int8 + 로지스틱 회귀 68/80(85%) · fp32 83.8% · 가장 가까운 3장 80% · SigLIP2 70% · 규칙만 58/80(72.5%)
  - 처음 보는 3장(1·2·3번, 규칙 다듬을 때 안 씀) 18조각: AI 18/18 · 규칙 10/18
  - 규칙을 다듬은 9장 39조각: AI 36 · 규칙 36 / 주방 2장 23조각: AI 14 · 규칙 12
  - 일 별: 사진/그림 100% · 큰 그림/상세 97%(규칙 84%) · 정면/입체 97%(규칙 100%) · 내부/도어 78%(규칙 75%) · 서랍 단면/부품 88%(규칙 52%)
  - AI가 종류를 고르고 정면/입체만 규칙으로 덮으면 86.3%
- 대조군: 정답을 섞어 가르치면 13%(가장 흔한 답 찍기 18.8%) → 새는 곳 없음. '그림 아님'(제목칸·아래 표·로고·빈 곳 56조각): 확신 점수 문턱·가까운 그림 닮음 문턱은 0% 거름 → '그림 아님' 칸을 함께 가르치면 94.6% 거름(제목칸·표·로고 14/14, 빈 곳 11/14), 진짜 그림 잘못 거름 2/80.
- 한국어 OCR: RapidOCR params `Rec.lang_type=LangRec.KOREAN, Rec.ocr_version=OCRVersion.PPOCRV5, Rec.model_type=ModelType.MOBILE`(small 은 미지원 오류). 자재표 3개 44줄 중 43줄(ㄴ→L 정리 필요, 1줄 깨짐), 한 덩어리 0.6~1.1초.
- 속도(이 PC CPU): DINOv2 int8 64ms/장 · fp32 80ms/장 · SigLIP2 77ms/장.
- 한계: 자료 80장·14장이라 오차 폭이 크다. 주방 예시가 적어 키큰장 정면↔평면, 회색 도어↔내부 혼동. 정답을 한 사람이 붙임.


## 5. 운영 자료로 다시 잰 값 (2026-10-22, 사용자 1회 허락 · 읽기 전용)
- 출처: 운영 DB(읽기 전용 세션, 지문 확인 FOMS-PRODUCTION · yamanote)에서 도면 마법사 시트의 그림 key·시트 이름만 읽음 → R2 GetObject 로 낱장 그림만 받음. 고객 정보는 읽지 않음. 접속 정보 파일은 받자마자 지우고 링크 해제, 그림·작업 파일은 실험 뒤 삭제(숫자 결과만 남김). 캔버스에는 운영 그림을 올리지 않음.
- 운영 전체: 마법사 시트 295장 · 낱장 그림 1,025장(9/11~10/22) · 합친 도면 첨부 1,746장. 받은 것: 주방류 시트 그림 211장 전부 + 나머지 주문 단위 95장 = 306장(주문 51건).
- 정답: 80장으로 가르친 AI가 먼저 짐작 → 사람이 묶음 사진으로 검토, 헷갈린 30장은 크게 다시 봄. AI 짐작이 이미 맞은 비율 89.2%(33장만 고침 — 주로 흰·회색 도어 주방 입체를 내부로, 주방 평면을 정면으로).
- 다시 가르친 뒤(조각 386 + 그림 아님 56, 주문·시트 단위 10조각 교차 시험): 전체 92.2% · 운영 그림 94.8% · 처음 80장 82.5% · 주방 91.2%(80장일 때 61%) · 주방 내부/도어 85.3% · 그 밖 내부/도어 96.2% · 그림 아님 거름 94.6%.
- 종류별: 사진 77/77 · 정면·내부 67/70 · 정면·도어 15/22 · 입체·내부 20/21 · 입체·도어 67/75 · 평면·상판 45/48 · 서랍 단면 35/35 · 부품 상세 30/37. 많이 헷갈린 것: [['입체·도어→입체·내부', 7], ['정면·도어→평면·상판', 4], ['정면·도어→정면·내부', 3], ['부품 상세→평면·상판', 3]].
- 학습 곡선: 34장 81.3% · 85장 87.3% · 174장 90.3% · 262장 92.6% · 347장 92.2% — 260장 넘으면 92~93%에서 멈춤.
- 확신 문턱별 자동 배치: 문턱 0.0: 자동 100% / 맞음 92.7% · 문턱 0.5: 자동 75% / 맞음 98.3% · 문턱 0.6: 자동 61% / 맞음 99.6% · 문턱 0.7: 자동 43% / 맞음 100.0% · 문턱 0.8: 자동 26% / 맞음 100.0%. 확신 0.5 이상만 자동으로 넣으면 4장 중 3장이 저절로, 그중 98% 맞음.


## 6. 헷갈리는 그림 더 모으기 · 자재표 자동 입력 시험 (2026-10-22, 운영 2차 읽기 · 사용자 허락)
- 운영 낱장 그림 1,026장을 모두 받아(1차 306장은 같은 고르기 규칙으로 되살림 — 확인용 12장 중 10장이 기록과 일치, 그사이 운영에서 바뀐 4장(#144~147)은 다시 보고 정답을 붙임), 나머지 720장을 80+306 정답으로 가르친 AI가 짐작.
- 도어·내부·평면으로 짐작했고 확신 0.7 미만이거나 드문 종류(정면 도어·입체 내부·평면)인 185장을 사람이 확인: 15장 고침, 애매한 2장 뺌 → 어려운 그림에서도 AI 짐작 91.8% 맞음.
- 더하기 전·후(시험 그림 = 처음 80+1차 306, 주문 단위 10조각, 같은 조각): 전체 92.2% → 92.0%, 도어/내부 90.0% → 88.4% — 효과 없음. 마법사 주방 그림은 1차에서 이미 전부 썼고(마법사 9/11부터), 2차는 대부분 붙박이장이라 주방 혼동을 못 줄였다.
- 그림 크기: 사람 확인 정답 569장 교차 시험에서 224px 91.9%(도어/내부 92.5%, 78ms/장) → 448px 92.8%(도어/내부 93.9%, 297ms/장). 규칙 특징을 붙이면 오히려 낮아짐(224 90.3%, 448 90.5%).
- 자재표 자동 입력: 운영 drawing_wizard.pending(전달 대기) PNG 중 마법사 저장 시각 ≤ PNG 시각인 100장(저장 글자=그림 글자 보장) → 자재표 글자 있는 98장. 내보내기 = 스테이지 1478×1040 의 2배(2956×2080)라 글자 객체 x·y·size 로 칸을 잘라 한국어 OCR.
  - 줄 1,329개: 전체 97.8% · 크기·수량 줄 99.5% · 숫자 줄(가로*세로=개수) 99.3% · 머리글 93.7% · 글자 틀림 1.2% · 한 글자도 안 틀린 시트 71/98 · 0.97초/장.
  - 머리글 오류 대부분은 [마이다]→[그어](크기를 바꿔도 불안정 — 모델 버릇). 머리글은 마법사 PRESETS 이름표라 목록에서 고르면 된다. 줄긋기(----)는 자료가 아니라 비교에서 뺐다.
- 남은 큰 자료: 옛 합친 도면 첨부 1,746장(3월~) — 자동 자르기로 주방 조각을 모을 수 있다. 받은 그림·작업 파일·접속 정보는 실험 뒤 삭제.

## 7. 옛 주방 도면 · 채널톡 도면방으로 주방 조각 모으기 (2026-10-22, 운영 3차 읽기 · 채널톡 Open API 읽기 · 사용자 요청)
- 자료: 운영 옛 합친 도면 중 주방 248장(주문 119건, 마법사 시험 주문과 겹침 0건) + 채널톡 도면방(팀챗 230331) 주방 47장. 도면방은 도면 크기 그림 31,894장인데 달마다 1장 표본 47장 중 주방 1장(약 2%) — 파일 이름·글에 주방 낱말이 있는 201장을 미리보기 + 제품명 칸 한국어 OCR로 걸러 46장. 어사이드 브라우저는 채널톡 로그인 계정이 없어 못 씀(가입은 하지 않음), Open API(웹 서비스 키)로 읽음.
- 자동 자르기(규칙, 4개 동시): 295장 실패 0, 조각 1,369(사진 202 · 그림 1,167), 26분.
- AI 짐작 → 헷갈리는 종류(도어·내부·평면, 확신 0.8 미만) 818 + 무작위 40 = 858 검토. 검토 5명 분담, 총괄이 직접 붙인 103칸과 대조해 92칸 같음 — 다른 칸 대부분은 총괄이 '깊이 치수만 있는 빗금 띠 = 평면·상판'(마법사 정답의 다수 기준)을 정면·내부로 본 것. AI 첫 짐작 정확도: 헷갈리는 쪽 82% · 무작위 87%. 뺀 것 59(돌아간 그림·잘린 조각·두 그림 섞임).
- 효과(마법사 주방 그림 211장, 주문 단위 10조각, 같은 시험): 주방 전체 94.3% → 94.3%(새 조각 무게 0.5면 95.3%) · 주방 도어/내부 90.4% → 92.6% · 전체 95.0% → 95.0~96.0%. 2장 차이라 흔들림 안일 수 있음. 남은 실수는 입체·도어→입체·내부(끝판 빗금 있는 닫힌 하부장, 도어/내부 짝의 도어판)와 평면↔정면.
- 결론: 자료 양은 더 이상 가장 큰 막힘이 아니다. 다음은 (1) 정답 기준 통일(마법사 정답에도 빗금 띠 평면을 정면·내부로 붙인 것 1장), (2) 같은 자리 도어/내부 짝이면 빗금 많은 쪽 = 내부 규칙과 함께 쓰기, (3) 확신 낮으면 미분류.
- 받은 운영·채널톡 그림·조각·작업 파일은 결과를 낸 뒤 삭제, railway 링크 없음 확인. 캔버스 R6 보드(숫자만).

## 8. 모든 제품으로 넓혀 다시 재기 (2026-10-23, 운영 4차 읽기 · 채널톡 도면방 처음부터 끝까지 · 사용자 요청)
- 사용자 요청: "운영에서 다시 받아, 주방 말고 냉장고나 각종 커스텀 장, 기본장도 같이 학습" + "도면방에서 위로 스크롤해 가면서 수집". 스크롤은 Open API cursor 로 끝까지 넘김(도면 크기 그림 31,908장 · 47달, 2022-12~) — 어사이드 브라우저는 채널톡 계정이 없어 불가.
- 자료: 운영 마법사 낱장 1,044장 전부(붙박이장 656 · 그 밖 장 177 · 주방 144 · 냉장고장 67, 시트 이름 기준) → 검토 6명이 전부 확인해 정답 1,040(빼기 4). 처음 80장만 가르친 AI 첫 짐작 94.6%. 옛 합친 도면(마법사 안 쓴 주문) 종류마다 60장 = 240 + 도면방 달마다 고르게 282 → 자동 자르기 조각 2,043, 헷갈리는 837 + 무작위 40 = 877 검토, 840 사용. 조각의 AI 첫 짐작은 74%.
- 대조: 총괄 직접 정답 37칸(마법사 27 · 조각 10)과 검토 결과 모두 같음.
- 결과(마법사 정답, 주문 단위 10조각): 조각 전 전체 95.6% · 도어/내부 94.4% · 붙박이장 98.8 · 냉장고장 97.0 · 그 밖 장 92.0 · 주방 84.7 → 조각 후 95.8% · 94.1% · 98.8 · 91.0 · 93.7 · 86.8. 조각은 효과 없음(무게 0.5도 같음). 가장 큰 실수 입체·도어→입체·내부 18장(조각 후 25장).
- 짝 규칙(같은 시트·같은 보기로 짐작한 그림이 둘이면 빗금 많은 쪽 = 내부): 모든 제품에 쓰면 95.8%(냉장고장·붙박이장 내려감), 주방 시트에만 쓰면 전체 96.3% · 도어/내부 95.6% · 주방 89.6%. 같은 자료로 고른 규칙이라 조금 낙관적.
- 결론: 자료 모으기는 끝. 붙박이장·냉장고장은 바로 쓸 수준, 주방은 짝 규칙 + 확신 낮으면 미분류. 다음 = 마법사에 붙이는 Spec.
- 받은 운영·채널톡 그림·조각·작업 파일은 결과를 낸 뒤 삭제, 접속 파일 즉시 삭제, railway 링크 없음 확인. 캔버스 R7 보드(숫자만).

## 9. 자재표 계산식 찾기 (2026-10-22, 운영 5차 읽기 · 사용자 요청 "학습한 도면 전체를 대상으로 계산식")
- 자료: 마법사 시트 309(자재표 303, 주문 209) 글자 그대로 + 학습에 쓴 옛 도면 380 · 채널톡 도면방 481 을 그림 글자 읽기(RapidOCR 한국어)로 → 자재표를 찾은 것 옛 253 · 채널톡 118. 같은 자재표는 한 번만 세어 670장.
- 방법: 자재표에 모듈 폭이 없어서, 같은 시트 두 줄의 차이를 모두 세고 가장 많은 차이를 규칙으로 봄(다른 시트와 짝지은 대조군과 비교). 맞음(±1)·여유(+2~20)·짧게(−2~−20)·그 밖으로 나눔. 50 단위 모듈 잣대를 둘째로.
- 결과는 설계서 `docs/plans/2026-10-23-drawing-part-label-feedback-spec.md` §3.3 표. 핵심: 여닫이 문 폭은 제품 이름이 아니라 **손잡이**로 갈림(피닉스바 (모듈−34)÷2·외짝 −30, 그 밖 (모듈−8)÷2·외짝 −4), 슬라이딩 문 = 모듈, 옷봉 모듈−35, 마이다 모듈−5, 피닉스바 개수 문÷2 올림 96%, SR 위 (위 틈−30) 10 단위 올림(무몰딩 60), 측판 EP 깊이+10·길이 2440, 문 높이 몰딩 100 단위 표준·무몰딩 천장−45.
- 못 찾은 것: 옆벽 SR·SR 수량·보조목·주방/냉장고장 문 높이·예외 문·EP 41 띠.
- 받은 자료는 결과를 낸 뒤 삭제, 접속 파일 즉시 삭제, railway 링크 없음 확인.

## 10. 1단계 구현용 분류기 h1 (2026-10-22, 운영 6차 읽기 · 사용자 승인 '설계서 승인, 1단계 만들기')
- 운영 마법사 낱장 1,071장(붙박이장 673 · 그 밖 장 182 · 주방 149 · 냉장고장 67)을 다시 받아 처음 80장 모델로 선짐작(94.7%) → 검토 6명 → 정답 1,065.
- 주문 단위 10조각: 전체 96.0% · 문/내부 95.5% · 확신 0.5 이상 자동 93.7%(그중 98.2% 정확) · 붙박이장 99.1 · 냉장고장 100 · 그 밖 장 90.5 · 주방 86.5.
- 내보낸 것: `static/js/drawing/part-head.json`(9×768 가중치 + 편향, 57KB, 1,201장으로 학습). 브라우저(캔버스 224 축소) 확신이 파이썬(PIL bicubic)과 견본 5장에서 ±0.07 안, 종류는 모두 같음.
- 받은 그림·검토 묶음·특징은 내보낸 뒤 삭제, railway 링크 없음 확인.
