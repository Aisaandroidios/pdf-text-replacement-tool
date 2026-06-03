from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from statistics import median

from PIL import Image, ImageDraw, ImageFont

from server.pdf_service import Replacement


IMAGE_MEDIA_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "TIFF": "image/tiff",
    "WEBP": "image/webp",
}
IMAGE_EXTENSION_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".webp": "WEBP",
}
LATIN_FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
]
CJK_FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
]


def export_image_with_replacements(
    image_bytes: bytes,
    replacements: list[Replacement],
    pdf_page_size: tuple[float, float],
    output_format: str | None = None,
) -> bytes:
    source = Image.open(BytesIO(image_bytes))
    image_format = _normalize_image_format(output_format or source.format or "PNG")
    image = source.convert("RGB")
    x_scale, y_scale = _image_scale(image.size, pdf_page_size)
    draw = ImageDraw.Draw(image)

    for replacement in replacements:
        if replacement.page_index != 0:
            raise ValueError("图片上传只支持单页替换。")

        rect = _scale_bbox(replacement.bbox, x_scale, y_scale, image.size)
        if _empty_rect(rect):
            continue

        background = _sample_background_color(image, rect)
        foreground = _sample_foreground_color(image, rect, background, replacement.color)
        font = _font_for_text(replacement.new_text, _font_size_for_rect(rect))
        erase_rect = _expanded_rect(rect, image.size, padding=max(2, int((rect[3] - rect[1]) * 0.12)))
        draw.rectangle(erase_rect, fill=background)
        _draw_text(draw, replacement, rect, x_scale, y_scale, font, foreground)

    stream = BytesIO()
    save_kwargs = {"format": image_format}
    if image_format in {"JPEG", "WEBP"}:
        save_kwargs.update({"quality": 95})
    image.save(stream, **save_kwargs)
    return stream.getvalue()


def save_image_with_replacements(
    image_bytes: bytes,
    replacements: list[Replacement],
    original_filename: str,
    output_dir: Path,
    pdf_page_size: tuple[float, float],
    output_format: str | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    image_format = _format_for_filename(original_filename, output_format)
    output_bytes = export_image_with_replacements(
        image_bytes,
        replacements,
        pdf_page_size,
        image_format,
    )
    output_path = _unique_image_output_path(output_dir, original_filename, image_format)
    output_path.write_bytes(output_bytes)
    return output_path


def image_media_type(image_format: str | None) -> str:
    return IMAGE_MEDIA_TYPES.get(_normalize_image_format(image_format or "PNG"), "image/png")


def image_format_for_extension(extension: str) -> str:
    return IMAGE_EXTENSION_FORMATS.get(extension.lower(), "PNG")


def _image_scale(image_size: tuple[int, int], pdf_page_size: tuple[float, float]) -> tuple[float, float]:
    pdf_width, pdf_height = pdf_page_size
    if pdf_width <= 0 or pdf_height <= 0:
        raise ValueError("图片页面尺寸无效。")
    return image_size[0] / pdf_width, image_size[1] / pdf_height


def _scale_bbox(
    bbox: list[float],
    x_scale: float,
    y_scale: float,
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = [float(value) for value in bbox]
    width, height = image_size
    return (
        _clamp_int(x0 * x_scale, 0, width),
        _clamp_int(y0 * y_scale, 0, height),
        _clamp_int(x1 * x_scale, 0, width),
        _clamp_int(y1 * y_scale, 0, height),
    )


def _empty_rect(rect: tuple[int, int, int, int]) -> bool:
    return rect[2] <= rect[0] or rect[3] <= rect[1]


def _expanded_rect(
    rect: tuple[int, int, int, int],
    image_size: tuple[int, int],
    padding: int,
) -> tuple[int, int, int, int]:
    width, height = image_size
    return (
        max(0, rect[0] - padding),
        max(0, rect[1] - padding),
        min(width, rect[2] + padding),
        min(height, rect[3] + padding),
    )


def _sample_background_color(image: Image.Image, rect: tuple[int, int, int, int]) -> tuple[int, int, int]:
    padded = _expanded_rect(rect, image.size, padding=max(4, int((rect[3] - rect[1]) * 0.25)))
    pixels: list[tuple[int, int, int]] = []
    step = max(1, int((rect[3] - rect[1]) / 12))

    for y in range(padded[1], padded[3], step):
        for x in range(padded[0], padded[2], step):
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                continue
            pixels.append(_rgb(image.getpixel((x, y))))

    if not pixels:
        pixels = [
            _rgb(image.getpixel((max(0, rect[0] - 1), max(0, rect[1] - 1)))),
            _rgb(image.getpixel((min(image.width - 1, rect[2]), max(0, rect[1] - 1)))),
            _rgb(image.getpixel((max(0, rect[0] - 1), min(image.height - 1, rect[3])))),
            _rgb(image.getpixel((min(image.width - 1, rect[2]), min(image.height - 1, rect[3])))),
        ]

    return _median_color(pixels)


def _sample_foreground_color(
    image: Image.Image,
    rect: tuple[int, int, int, int],
    background: tuple[int, int, int],
    fallback: str | None,
) -> tuple[int, int, int]:
    pixels: list[tuple[int, int, int]] = []
    step = max(1, int((rect[3] - rect[1]) / 20))

    for y in range(rect[1], rect[3], step):
        for x in range(rect[0], rect[2], step):
            pixel = _rgb(image.getpixel((x, y)))
            if _color_distance(pixel, background) >= 35:
                pixels.append(pixel)

    if pixels:
        return _median_color(pixels)

    return _hex_to_rgb255(fallback)


def _font_for_text(text: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    paths = CJK_FONT_PATHS if _needs_cjk_font(text) else LATIN_FONT_PATHS
    for path in paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _font_size_for_rect(rect: tuple[int, int, int, int]) -> int:
    height = max(1, rect[3] - rect[1])
    return max(6, int(round(height * 1.05)))


def _draw_text(
    draw: ImageDraw.ImageDraw,
    replacement: Replacement,
    rect: tuple[int, int, int, int],
    x_scale: float,
    y_scale: float,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    color: tuple[int, int, int],
) -> None:
    if replacement.origin and len(replacement.origin) == 2:
        point = (int(round(replacement.origin[0] * x_scale)), int(round(replacement.origin[1] * y_scale)))
    else:
        point = (rect[0], rect[3])

    try:
        draw.text(point, replacement.new_text, fill=color, font=font, anchor="ls")
    except TypeError:
        draw.text((rect[0], rect[1]), replacement.new_text, fill=color, font=font)


def _format_for_filename(original_filename: str, output_format: str | None = None) -> str:
    if output_format:
        return _normalize_image_format(output_format)
    return image_format_for_extension(Path(original_filename).suffix)


def _normalize_image_format(image_format: str) -> str:
    normalized = image_format.upper()
    if normalized == "JPG":
        return "JPEG"
    if normalized in IMAGE_MEDIA_TYPES:
        return normalized
    return "PNG"


def _unique_image_output_path(output_dir: Path, original_filename: str, image_format: str) -> Path:
    source = Path(original_filename or f"edited.{_extension_for_format(image_format)}")
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", source.stem).strip(" .") or "edited"
    extension = _extension_for_format(image_format, source.suffix)
    candidate = output_dir / f"{stem}-edited{extension}"
    index = 2

    while candidate.exists():
        candidate = output_dir / f"{stem}-edited-{index}{extension}"
        index += 1

    return candidate


def _extension_for_format(image_format: str, original_suffix: str | None = None) -> str:
    suffix = (original_suffix or "").lower()
    if suffix in IMAGE_EXTENSION_FORMATS and IMAGE_EXTENSION_FORMATS[suffix] == image_format:
        return suffix
    return {
        "JPEG": ".jpg",
        "PNG": ".png",
        "TIFF": ".tiff",
        "WEBP": ".webp",
    }.get(image_format, ".png")


def _needs_cjk_font(text: str) -> bool:
    try:
        text.encode("latin-1")
        return False
    except UnicodeEncodeError:
        return True


def _hex_to_rgb255(value: str | None) -> tuple[int, int, int]:
    if not value:
        return (0, 0, 0)
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
    if not match:
        return (0, 0, 0)
    raw = match.group(1)
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def _median_color(pixels: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    return tuple(int(median(channel)) for channel in zip(*pixels))


def _color_distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    return sum((left - right) ** 2 for left, right in zip(first, second)) ** 0.5


def _rgb(pixel: int | tuple[int, ...]) -> tuple[int, int, int]:
    if isinstance(pixel, int):
        return (pixel, pixel, pixel)
    return (int(pixel[0]), int(pixel[1]), int(pixel[2]))


def _clamp_int(value: float, lower: int, upper: int) -> int:
    return int(max(lower, min(upper, round(value))))
