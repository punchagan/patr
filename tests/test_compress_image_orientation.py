"""compress_image() must honor the EXIF Orientation tag.

Phone/camera JPEGs are often stored as raw sensor pixels plus an Orientation
tag saying how to rotate/flip them for display. Viewers (Windows Photos,
browsers) apply the tag; compress_image() re-encodes the pixels and drops
the tag, so unless it bakes the rotation in first, the uploaded copy shows
the raw, sideways pixels.
"""

import pytest
from patr.content import compress_image
from PIL import Image

RED = (255, 0, 0)
BLUE = (0, 0, 255)

# Raw image: 60x30, red block at raw top-left, blue block at raw bottom-right.
# Per the EXIF spec: (displayed size, corner where red lands, corner where blue lands)
EXPECTED_DISPLAY = {
    1: ((60, 30), "TL", "BR"),  # normal
    2: ((60, 30), "TR", "BL"),  # mirrored horizontally
    3: ((60, 30), "BR", "TL"),  # rotated 180
    4: ((60, 30), "BL", "TR"),  # mirrored vertically
    5: ((30, 60), "TL", "BR"),  # transposed
    6: ((30, 60), "TR", "BL"),  # rotate 90 CW (typical phone portrait)
    7: ((30, 60), "BR", "TL"),  # transversed
    8: ((30, 60), "BL", "TR"),  # rotate 270 CW
}


def _raw_image():
    img = Image.new("RGB", (60, 30), (255, 255, 255))
    img.paste(RED, (0, 0, 15, 10))
    img.paste(BLUE, (45, 20, 60, 30))
    return img


def _corner_xy(img, corner):
    w, h = img.size
    return {
        "TL": (2, 2),
        "TR": (w - 3, 2),
        "BL": (2, h - 3),
        "BR": (w - 3, h - 3),
    }[corner]


def _is_color(px, color):
    return sum(abs(a - b) for a, b in zip(px, color, strict=True)) < 120


@pytest.mark.parametrize("orientation", sorted(EXPECTED_DISPLAY))
def test_compress_image_applies_exif_orientation(tmp_path, orientation):
    size, red_corner, blue_corner = EXPECTED_DISPLAY[orientation]
    exif = Image.Exif()
    exif[0x0112] = orientation
    src = tmp_path / "src.jpg"
    _raw_image().save(src, "JPEG", quality=95, exif=exif)
    dest = tmp_path / "out.jpg"

    assert compress_image(src, dest) is True

    with Image.open(dest) as out:
        assert out.size == size
        assert _is_color(out.getpixel(_corner_xy(out, red_corner)), RED)
        assert _is_color(out.getpixel(_corner_xy(out, blue_corner)), BLUE)
