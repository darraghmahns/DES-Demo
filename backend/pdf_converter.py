"""PDF to base64 image conversion for neural OCR input."""

import base64
import io
import os
import sys
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
        # Attempt a minimal conversion to verify poppler is accessible
        import shutil
        return shutil.which("pdftoppm") is not None
    except Exception:
        return False


def pdf_to_images(pdf_path: str, dpi: int = 200) -> list[Image.Image]:
    """Convert a PDF file to a list of PIL Images, one per page.

    Args:
        pdf_path: Path to the PDF file.
        dpi: Resolution for rendering. 200 is a good balance of quality and token cost.

    Returns:
        List of PIL Image objects.
    """
    if convert_from_path is None:
        print("ERROR: pdf2image is not installed. Run: pip install pdf2image", file=sys.stderr)
        sys.exit(1)

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not path.suffix.lower() == ".pdf":
        raise ValueError(f"Expected a PDF file, got: {path.suffix}")

    images = convert_from_path(str(path), dpi=dpi)
    return images


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

    # Count pages by converting (lightweight — only counts, doesn't render at high DPI)
    if convert_from_path is not None:
        try:
            pages = len(convert_from_path(str(path), dpi=72, first_page=1, last_page=1))
            # To get actual page count we need pdfinfo or a full convert
            from pdf2image.pdf2image import pdfinfo_from_path
            info = pdfinfo_from_path(str(path))
            page_count = info.get("Pages", 1)
        except Exception:
            page_count = 1
    else:
        page_count = 1

    return {
        "name": path.name,
        "size_bytes": size,
        "size_human": size_human,
        "pages": page_count,
    }
