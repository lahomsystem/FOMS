from foms.services.file_utils import allowed_erp_media_file, allowed_file


def test_allowed_file_accepts_excel_extensions_case_insensitively() -> None:
    """Excel uploads should accept configured extensions regardless of case."""
    assert allowed_file("orders.xlsx") is True
    assert allowed_file("orders.XLS") is True


def test_allowed_file_rejects_missing_or_invalid_extension() -> None:
    """Excel uploads should reject missing or unsupported extensions."""
    assert allowed_file("orders") is False
    assert allowed_file("orders.csv") is False


def test_allowed_erp_media_file_accepts_supported_media_extensions() -> None:
    """ERP media uploads should accept configured image and video extensions."""
    assert allowed_erp_media_file("photo.jpg") is True
    assert allowed_erp_media_file("video.MP4") is True


def test_allowed_erp_media_file_rejects_invalid_media_extension() -> None:
    """ERP media uploads should reject extensions outside the allowed set."""
    assert allowed_erp_media_file("document.pdf") is False
