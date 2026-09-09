"""업로드 이미지의 균일 여백(투명·단색 테두리)을 잘라내는 순수 헬퍼.

스케치업 렌더 PNG 는 구조물 주변에 넓은 흰 여백을 안고 나온다. 도면 마법사는 이미지를
원본 크기 그대로 객체로 놓기 때문에(``natural_w/h`` 비율 상자) 여백까지 클릭·선택·리사이즈
영역이 되어, 그림을 두 장 이상 놓으면 서로 겹쳐 잡힌다. 업로드 시점에 여백을 잘라
저장하면 이후 배치·크기조절이 실제 그림 경계로만 동작한다.

판정은 보수적이다 — 실측 사진처럼 여백이 아닌 이미지를 깎으면 원본 손실이므로:

* 알파 채널이 있으면 **투명 영역**만 여백으로 본다.
* 알파가 없으면 **네 모서리 색이 서로 같을 때만** 그 색을 배경으로 인정한다.
* 잘라도 원본의 :data:`MAX_KEEP_RATIO` 이상이 남으면 여백이 아니라고 보고 그만둔다.
* 결과가 :data:`MIN_SIDE` 보다 작으면 그만둔다.

어느 단계든 판단이 서지 않으면 ``None`` 을 돌려 호출측이 **원본을 그대로** 쓰게 한다.
"""
from __future__ import annotations

import io
import logging
from typing import NamedTuple, Optional

try:  # Pillow 는 requirements 에 있으나, 없더라도 업로드 자체는 살아야 한다.
    from PIL import Image, ImageChops

    PILLOW_AVAILABLE = True
except ImportError:  # pragma: no cover - 배포 환경엔 항상 있다
    PILLOW_AVAILABLE = False

logger = logging.getLogger(__name__)

__all__ = ["TrimResult", "trim_uniform_margins", "MIN_SIDE", "MAX_KEEP_RATIO"]

#: 잘라낸 결과의 최소 한 변(px). 이보다 작아지면 배경 오판으로 보고 원본을 유지한다.
MIN_SIDE = 32

#: 잘라낸 넓이가 원본의 이 비율 이상이면 "여백이 없다"고 보고 원본을 유지한다.
MAX_KEEP_RATIO = 0.98

#: 네 모서리 색이 같다고 볼 채널별 허용 오차(0-255). JPEG 재압축 잡티를 흡수한다.
CORNER_TOLERANCE = 6

#: 배경색과의 차이가 이 값 이하인 픽셀은 배경으로 본다(0-255).
BACKGROUND_TOLERANCE = 10

#: 알파가 이 값 이하인 픽셀은 투명(여백)으로 본다(0-255).
ALPHA_TOLERANCE = 8

#: 트림 대상 확장자. GIF 는 애니메이션 프레임이 있어 제외한다.
TRIMMABLE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')

_FORMAT_BY_EXT = {
    '.png': 'PNG',
    '.jpg': 'JPEG',
    '.jpeg': 'JPEG',
    '.webp': 'WEBP',
}


class TrimResult(NamedTuple):
    """트림 결과.

    Attributes:
        data: 잘라낸 이미지 바이트(원본과 같은 포맷).
        width: 잘라낸 뒤 가로 픽셀.
        height: 잘라낸 뒤 세로 픽셀.
        original_width: 원본 가로 픽셀.
        original_height: 원본 세로 픽셀.
    """

    data: bytes
    width: int
    height: int
    original_width: int
    original_height: int


def _alpha_bbox(image: "Image.Image") -> Optional[tuple]:
    """알파 채널 기준 내용 bbox. 알파가 없으면 None."""
    if image.mode not in ('RGBA', 'LA') and 'transparency' not in image.info:
        return None
    rgba = image.convert('RGBA')
    alpha = rgba.getchannel('A')
    if alpha.getextrema()[0] > ALPHA_TOLERANCE:
        return None  # 전부 불투명 = 알파로는 여백을 못 가린다(단색 판정으로 넘긴다)
    mask = alpha.point(lambda a: 255 if a > ALPHA_TOLERANCE else 0)
    return mask.getbbox()


def _uniform_background_bbox(image: "Image.Image") -> Optional[tuple]:
    """네 모서리가 같은 색일 때 그 색을 배경으로 보고 내용 bbox 를 구한다."""
    rgb = image.convert('RGB')
    width, height = rgb.size
    if width < 2 or height < 2:
        return None
    corners = [
        rgb.getpixel((0, 0)),
        rgb.getpixel((width - 1, 0)),
        rgb.getpixel((0, height - 1)),
        rgb.getpixel((width - 1, height - 1)),
    ]
    for channel in range(3):
        values = [c[channel] for c in corners]
        if max(values) - min(values) > CORNER_TOLERANCE:
            return None  # 모서리가 제각각 = 배경이라 부를 단색이 없다
    background = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
    diff = ImageChops.difference(rgb, Image.new('RGB', rgb.size, background))
    mask = diff.convert('L').point(lambda v: 255 if v > BACKGROUND_TOLERANCE else 0)
    return mask.getbbox()


def _encode(image: "Image.Image", fmt: str, original: "Image.Image") -> bytes:
    """잘라낸 이미지를 원본 포맷으로 다시 인코딩한다."""
    buffer = io.BytesIO()
    if fmt == 'JPEG':
        image.convert('RGB').save(buffer, format='JPEG', quality=92, optimize=True)
    elif fmt == 'WEBP':
        image.save(buffer, format='WEBP', quality=92)
    else:
        save_kwargs = {}
        if original.mode == 'P' and 'transparency' in original.info:
            save_kwargs['transparency'] = original.info['transparency']
        image.save(buffer, format='PNG', optimize=True, **save_kwargs)
    return buffer.getvalue()


def trim_uniform_margins(data: bytes, *, ext: str) -> Optional[TrimResult]:
    """이미지 테두리의 균일 여백을 잘라낸다.

    Args:
        data: 원본 이미지 바이트.
        ext: 소문자 확장자(``.png`` 등). 트림 대상 판별에 쓴다.

    Returns:
        잘라낸 :class:`TrimResult`. 여백이 없거나 판정이 서지 않으면 ``None``
        (호출측은 원본을 그대로 저장해야 한다).
    """
    if not PILLOW_AVAILABLE or not data:
        return None
    ext = (ext or '').lower()
    if ext not in TRIMMABLE_EXTENSIONS:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            original_width, original_height = image.size
            if original_width <= 0 or original_height <= 0:
                return None

            bbox = _alpha_bbox(image)
            if bbox is None:
                bbox = _uniform_background_bbox(image)
            if not bbox:
                return None  # None(판정 불가) 과 빈 bbox(전부 배경) 둘 다 원본 유지

            left, top, right, bottom = bbox
            width, height = right - left, bottom - top
            if width < MIN_SIDE or height < MIN_SIDE:
                return None
            area_ratio = (width * height) / float(original_width * original_height)
            if area_ratio >= MAX_KEEP_RATIO:
                return None  # 여백이라 부를 만큼 잘리지 않는다

            fmt = _FORMAT_BY_EXT.get(ext, 'PNG')
            encoded = _encode(image.crop(bbox), fmt, image)
    except Exception:
        logger.warning("image margin trim failed (원본 유지)", exc_info=True)
        return None

    return TrimResult(
        data=encoded,
        width=width,
        height=height,
        original_width=original_width,
        original_height=original_height,
    )
