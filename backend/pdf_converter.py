"""PDF to base64 image conversion for neural OCR input."""

import base64
import io
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image

# Ensure Homebrew binaries (including poppler) are discoverable
_HOMEBREW_BIN = "/opt/homebrew/bin"
if _HOMEBREW_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _HOMEBREW_BIN + ":" + os.environ.get("PATH", "")

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None


def check_poppler_installed() -> bool:
    """Check if poppler-utils is available for pdf2image."""
    if convert_from_path is None:
        return False
    try:
        import shutil
        return shutil.which("pdftoppm") is not None
    except OSError:
        return False


MAX_PAGES = 20  # Safety limit for memory — most purchase agreements are <20 pages


def _validate_pdf(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {path.suffix}")


def _get_pdf_page_count(path: Path) -> int:
    if convert_from_path is None:
        return 1
    try:
        from pdf2image.pdf2image import pdfinfo_from_path
        info = pdfinfo_from_path(str(path))
        return info.get("Pages", 1)
    except (OSError, ValueError, KeyError):
        return 1


def _enforce_page_limit(path: Path, max_pages: int) -> int:
    page_count = _get_pdf_page_count(path)
    if max_pages and page_count > max_pages:
        raise ValueError(
            f"PDF has {page_count} pages, exceeding the {max_pages}-page limit. "
            f"Please use a shorter document."
        )
    return page_count


def pdf_to_images(pdf_path: str, dpi: int = 150, max_pages: int = MAX_PAGES) -> list[Image.Image]:
    """Convert a PDF file to a list of PIL Images, one per page.

    Args:
        pdf_path: Path to the PDF file.
        dpi: Resolution for rendering. 150 reduces peak memory on small
            deployment instances without materially changing extraction quality.
        max_pages: Maximum pages to convert (0 = unlimited). Protects against
            large PDFs consuming excessive memory.

    Returns:
        List of PIL Image objects.

    Raises:
        ValueError: If the PDF exceeds *max_pages*.
    """
    if convert_from_path is None:
        print("ERROR: pdf2image is not installed. Run: pip install pdf2image", file=sys.stderr)
        sys.exit(1)

    path = Path(pdf_path)
    _validate_pdf(path)
    _enforce_page_limit(path, max_pages)

    images = convert_from_path(str(path), dpi=dpi)
    return images


def pdf_to_base64_images(
    pdf_path: str,
    dpi: int = 150,
    max_pages: int = MAX_PAGES,
    max_size: tuple[int, int] = (2048, 2048),
) -> list[str]:
    """Convert a PDF to base64 PNG pages without holding all PIL pages in memory."""
    if convert_from_path is None:
        print("ERROR: pdf2image is not installed. Run: pip install pdf2image", file=sys.stderr)
        sys.exit(1)

    path = Path(pdf_path)
    _validate_pdf(path)
    _enforce_page_limit(path, max_pages)

    try:
        with tempfile.TemporaryDirectory(prefix="des_pdf_pages_") as temp_dir:
            image_paths = convert_from_path(
                str(path),
                dpi=dpi,
                output_folder=temp_dir,
                fmt="png",
                paths_only=True,
            )
            encoded_images: list[str] = []
            for image_path in image_paths:
                with Image.open(image_path) as image:
                    encoded_images.append(image_to_base64(image, max_size=max_size))
            return encoded_images
    except TypeError:
        images = pdf_to_images(pdf_path, dpi=dpi, max_pages=max_pages)
        try:
            return [image_to_base64(image, max_size=max_size) for image in images]
        finally:
            for image in images:
                try:
                    image.close()
                except Exception:
                    pass


def image_to_base64(image: Image.Image, max_size: tuple[int, int] = (2048, 2048)) -> str:
    """Convert a PIL Image to a base64-encoded PNG string for the OpenAI API.

    Resizes if needed to stay within GPT-4o Vision token limits.

    Args:
        image: PIL Image to encode.
        max_size: Maximum dimensions (width, height).

    Returns:
        Base64-encoded PNG string.
    """
    image = image.copy()
    image.thumbnail(max_size, Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def get_pdf_info(pdf_path: str) -> dict:
    """Get basic info about a PDF file.

    Returns:
        Dict with 'name', 'size_bytes', 'size_human', and 'pages'.
    """
    path = Path(pdf_path)
    size = path.stat().st_size

    if size < 1024:
        size_human = f"{size} B"
    elif size < 1024 * 1024:
        size_human = f"{size / 1024:.1f} KB"
    else:
        size_human = f"{size / (1024 * 1024):.1f} MB"

    page_count = _get_pdf_page_count(path)

    return {
        "name": path.name,
        "size_bytes": size,
        "size_human": size_human,
        "pages": page_count,
    }
