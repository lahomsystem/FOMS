"""이미지 여백 트림 헬퍼 계약 (도면 마법사 에셋 업로드가 쓰는 순수 함수).

핵심은 "자르는 것"보다 **안 자르는 조건**이다 — 실측 사진처럼 여백이 아닌 이미지를
깎으면 원본이 사라지므로, 판정이 서지 않으면 항상 None(원본 유지)이어야 한다.
"""
from __future__ import annotations

import io

from PIL import Image

from foms.services.image_margin_trim import MIN_SIDE, trim_uniform_margins


def _png_bytes(image: Image.Image) -> bytes:
    """PIL 이미지를 PNG 바이트로."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _white_canvas_with_block(canvas=(600, 400), block=(200, 150), at=(150, 100)) -> Image.Image:
    """흰 배경 가운데에 검은 사각형 하나(스케치업 렌더 PNG 모양)."""
    img = Image.new("RGB", canvas, (255, 255, 255))
    img.paste(Image.new("RGB", block, (10, 10, 10)), at)
    return img


def test_trims_white_border_down_to_content() -> None:
    """네 모서리가 같은 흰색이면 그 색을 배경으로 보고 내용 경계까지 자른다."""
    result = trim_uniform_margins(_png_bytes(_white_canvas_with_block()), ext=".png")

    assert result is not None
    assert (result.width, result.height) == (200, 150)
    assert (result.original_width, result.original_height) == (600, 400)
    with Image.open(io.BytesIO(result.data)) as trimmed:
        assert trimmed.size == (200, 150)


def test_trims_transparent_border_when_alpha_present() -> None:
    """알파가 있으면 투명 영역을 여백으로 본다(배경색 판정보다 우선)."""
    img = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (120, 90), (200, 30, 30, 255)), (60, 70))

    result = trim_uniform_margins(_png_bytes(img), ext=".png")

    assert result is not None
    assert (result.width, result.height) == (120, 90)


def test_keeps_photo_with_mismatched_corners() -> None:
    """모서리 색이 제각각이면(사진) 배경이라 부를 단색이 없으므로 자르지 않는다."""
    img = Image.new("RGB", (300, 300), (255, 255, 255))
    img.paste(Image.new("RGB", (150, 150), (20, 60, 200)), (0, 0))
    img.paste(Image.new("RGB", (150, 150), (200, 180, 40)), (150, 150))

    assert trim_uniform_margins(_png_bytes(img), ext=".png") is None


def test_keeps_image_without_meaningful_margin() -> None:
    """테두리 2px 만 흰색이면 잘라도 원본의 98% 이상이 남아 손대지 않는다."""
    img = Image.new("RGB", (400, 400), (255, 255, 255))
    img.paste(Image.new("RGB", (396, 396), (30, 30, 30)), (2, 2))

    assert trim_uniform_margins(_png_bytes(img), ext=".png") is None


def test_keeps_blank_image() -> None:
    """전부 배경이면(내용 없음) 자르지 않는다 — 빈 bbox 로 0px 이 되면 안 된다."""
    assert trim_uniform_margins(_png_bytes(Image.new("RGB", (300, 200), (255, 255, 255))), ext=".png") is None


def test_keeps_when_content_smaller_than_min_side() -> None:
    """내용이 최소 크기 미만이면 배경 오판으로 보고 원본을 유지한다."""
    img = Image.new("RGB", (400, 400), (255, 255, 255))
    small = MIN_SIDE - 8
    img.paste(Image.new("RGB", (small, small), (0, 0, 0)), (100, 100))

    assert trim_uniform_margins(_png_bytes(img), ext=".png") is None


def test_skips_gif_and_unknown_extensions() -> None:
    """GIF(애니메이션 프레임)와 미지원 확장자는 대상이 아니다."""
    data = _png_bytes(_white_canvas_with_block())

    assert trim_uniform_margins(data, ext=".gif") is None
    assert trim_uniform_margins(data, ext=".txt") is None


def test_returns_none_on_broken_bytes() -> None:
    """열 수 없는 바이트는 예외 대신 None — 업로드는 원본으로 이어져야 한다."""
    assert trim_uniform_margins(b"not-an-image", ext=".png") is None
    assert trim_uniform_margins(b"", ext=".png") is None


def test_jpeg_keeps_jpeg_format() -> None:
    """JPEG 은 JPEG 으로 다시 인코딩한다(포맷 교체로 확장자와 어긋나면 안 된다)."""
    buf = io.BytesIO()
    _white_canvas_with_block().save(buf, format="JPEG", quality=95)

    result = trim_uniform_margins(buf.getvalue(), ext=".jpg")

    assert result is not None
    with Image.open(io.BytesIO(result.data)) as trimmed:
        assert trimmed.format == "JPEG"
