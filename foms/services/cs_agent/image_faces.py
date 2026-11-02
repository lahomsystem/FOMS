"""얼굴 거르기 — OpenCV YuNet 으로 그림 속 얼굴을 센다. 하나라도 있으면 그 그림은 보내지 않는다(설계서 17.11 (a) · D89).

학습 폴더의 시범(D58)과 같은 값: 점수 문턱 :data:`SCORE` (놓치지 않는 쪽), 두 크기(긴 변 :data:`SIDES`)에서 본 얼굴 수
가운데 큰 값. 거르기가 고장(패키지 없음 · 모델 파일 없음 · 읽기 오류)이면 :class:`FaceCheckError` — 부르는 쪽은 **보내지
않는다**(막는 쪽). 모델 파일은 ``assets/face_detection_yunet_2023mar.onnx``(MIT — 옆의 ``YUNET_LICENSE.txt``). opencv 는
부를 때 가져온다 — 앱 import 가 opencv 에 묶이지 않는다. 거르기는 그림을 Claude 로 보내는 곳(WORKER)에서만 돈다.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

__all__ = ["MODEL_PATH", "SCORE", "SIDES", "FaceCheckError", "count_faces"]

MODEL_PATH = Path(__file__).resolve().parent / "assets" / "face_detection_yunet_2023mar.onnx"
SCORE = 0.6
SIDES: tuple[int, ...] = (640, 1280)
_NMS, _TOP_K = 0.3, 5000
_MAX_UPSCALE = 1.5
_lock = threading.Lock()


class FaceCheckError(RuntimeError):
    """얼굴 거르기를 못 했다(까닭 코드만) — 그 그림은 보내지 않는다."""


def _detector(width: int, height: int) -> Any:
    """그 크기의 YuNet 찾기 도구(부를 때마다 새로 — 크기가 바뀌고 한 장씩 보니 묶어 둘 이득이 작다)."""
    try:
        import cv2  # noqa: PLC0415 — 부를 때만(앱 import 를 opencv 에 묶지 않는다)
    except ImportError:
        raise FaceCheckError("no_opencv") from None
    if not MODEL_PATH.is_file():
        raise FaceCheckError("no_model")
    try:
        return cv2.FaceDetectorYN.create(str(MODEL_PATH), "", (width, height), SCORE, _NMS, _TOP_K)
    except cv2.error:
        raise FaceCheckError("model_load") from None


def count_faces(image: Any) -> int:
    """BGR 픽셀 배열(numpy, 세로 × 가로 × 3)의 얼굴 수 — 두 크기 가운데 큰 값.

    Raises:
        FaceCheckError: 패키지 · 모델 파일이 없거나 배열 꼴이 틀리거나 찾기가 실패했다(막는 쪽).
    """
    shape = getattr(image, "shape", None)
    if not shape or len(shape) != 3 or shape[2] != 3 or min(shape[:2]) < 1:
        raise FaceCheckError("bad_image")
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        raise FaceCheckError("no_opencv") from None
    height, width = int(shape[0]), int(shape[1])
    best = 0
    with _lock:  # 한 장씩(WORKER 메모리 · opencv 스레드)
        for side in SIDES:
            scale = side / max(height, width)
            if scale > _MAX_UPSCALE:
                continue
            size = (max(1, int(width * scale)), max(1, int(height * scale)))
            try:
                small = cv2.resize(image, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
                detector = _detector(*size)
                _, found = detector.detect(small)
            except cv2.error:
                raise FaceCheckError("detect_failed") from None
            best = max(best, 0 if found is None else len(found))
    if best == 0 and min(SIDES) / max(height, width) > _MAX_UPSCALE:  # 작은 그림 — 제 크기로 한 번 본다
        try:
            _, found = _detector(width, height).detect(image)
        except cv2.error:
            raise FaceCheckError("detect_failed") from None
        best = 0 if found is None else len(found)
    return best
