"""
Layout-aware PDF text extraction shared across indexers.

PyMuPDF (fitz) is the primary engine — it honours column layouts, rotated
text, and typical Spanish normativa structure significantly better than
pypdf. We fall back to pypdf if PyMuPDF fails on a specific page (rare,
but some PDFs with broken content streams only parse under pypdf).

Why we can't just use pypdf for multi-column PDFs
-------------------------------------------------
pypdf walks the content stream roughly in glyph-paint order. On a
3-column layout that means line 1 of col 1 → line 1 of col 2 → line 1
of col 3 → line 2 of col 1 → …, which shreds sentences and ruins both
embeddings and section-heading regex.

PyMuPDF returns text as blocks with bounding boxes. We cluster block
x-midpoints per page to auto-detect the column count (1-4), then walk
each column top-to-bottom, left-to-right. Pages with full-width
figures / tables fall back to a single column automatically because the
cluster count collapses to 1.
"""
from __future__ import annotations

import io
import logging
import shutil
from typing import List, Optional, Tuple

import fitz  # PyMuPDF
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Minimum horizontal gap (in points) between column midpoints for them to
# count as separate columns. A4 is 595pt wide, so ~80pt is a comfortable
# gutter threshold; anything closer than that collapses into one column.
MIN_COLUMN_GAP_PT = 80.0
# Ignore blocks narrower than this — usually stray glyphs / page numbers.
MIN_BLOCK_WIDTH_PT = 20.0
# Round block tops to this grid when sorting so near-aligned blocks
# (e.g. footnote markers vs. body text) stay in the same "row".
TOP_BUCKET_PT = 6.0

# ── OCR configuration (for scanned / image-only PDFs) ──────────────
# A page is considered "scanned" — and thus sent to OCR — when its
# PyMuPDF-extracted text is shorter than this. 50 chars comfortably
# catches headers / footers that repeat on pure-image pages without
# misclassifying real content pages.
OCR_MIN_CHARS_PER_PAGE = 50
# 300 dpi is the sweet spot for typewritten 20th-century documents:
# enough to resolve serifs and accented vowels, without blowing up
# render + OCR time to minutes per page.
OCR_DPI = 300
# Tesseract language model. `spa` is the Spanish model installed by
# `brew install tesseract-lang`; `spa+eng` helps on pages that mix
# English terms (rare in normativa but harmless).
OCR_LANG = "spa"
# Tesseract page-segmentation mode. PSM 1 = "automatic page segmentation
# with orientation + script detection"; works well for the multi-column
# + heading layouts typical of Spanish normativa from the 70s–80s.
OCR_PSM = 1

_TESSERACT_AVAILABLE: Optional[bool] = None


def _tesseract_available() -> bool:
    """
    Return True once we've confirmed the `tesseract` binary is installed
    and importable via pytesseract. Cached across calls so we don't re-
    probe 70 times per document.
    """
    global _TESSERACT_AVAILABLE
    if _TESSERACT_AVAILABLE is not None:
        return _TESSERACT_AVAILABLE
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        logger.warning("pytesseract not installed — OCR fallback disabled.")
        _TESSERACT_AVAILABLE = False
        return False
    if not shutil.which("tesseract"):
        logger.warning(
            "`tesseract` binary not found on PATH — OCR fallback disabled. "
            "Install with `brew install tesseract tesseract-lang`."
        )
        _TESSERACT_AVAILABLE = False
        return False
    _TESSERACT_AVAILABLE = True
    return True


def extract_text_with_pages(
    pdf_bytes: bytes,
    *,
    enable_ocr: bool = True,
) -> List[Tuple[int, str]]:
    """
    Extract text from a PDF as [(page_number, text), ...].

    Cascading strategy per page:
      1. PyMuPDF with column-aware block extraction (born-digital PDFs
         with a text layer, single- or multi-column).
      2. pypdf flat extraction (rare rescue for PDFs with broken content
         streams PyMuPDF can't parse).
      3. Tesseract OCR on a rendered page image (scanned PDFs without
         any text layer at all).

    Pass `enable_ocr=False` to skip the OCR step — useful in tests and
    when you want to fail loudly rather than silently paying the
    minute-per-page OCR cost. OCR is also skipped automatically when the
    tesseract binary isn't on PATH.
    """
    out: List[Tuple[int, str]] = []
    pypdf_reader = None  # lazy — only built if we need a fallback
    ocr_pages_done = 0

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.warning(f"PyMuPDF could not open PDF: {e} — falling back to pypdf")
        return _extract_with_pypdf(pdf_bytes)

    for page_index, page in enumerate(doc):
        text = ""
        try:
            text = _extract_page_layout_aware(page)
        except Exception as e:
            logger.warning(f"PyMuPDF page {page_index + 1} failed: {e}")
            text = ""

        # Step 2: pypdf fallback if PyMuPDF returned nothing useful.
        if len(text.strip()) < OCR_MIN_CHARS_PER_PAGE:
            if pypdf_reader is None:
                try:
                    pypdf_reader = PdfReader(io.BytesIO(pdf_bytes))
                except Exception:
                    pypdf_reader = False
            if pypdf_reader:
                try:
                    pypdf_text = (pypdf_reader.pages[page_index].extract_text() or "").strip()
                    if len(pypdf_text) > len(text.strip()):
                        text = pypdf_text
                except Exception:
                    pass

        # Step 3: OCR fallback for scanned pages. Triggered only when
        # both text-layer paths came up essentially empty — a strong
        # signal the page is an image.
        if enable_ocr and len(text.strip()) < OCR_MIN_CHARS_PER_PAGE and _tesseract_available():
            try:
                ocr_text = _ocr_page(page)
                if len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    ocr_pages_done += 1
            except Exception as e:
                logger.warning(f"OCR failed on page {page_index + 1}: {e}")

        if text.strip():
            out.append((page_index + 1, text.strip()))

    if ocr_pages_done:
        logger.info(f"OCR used on {ocr_pages_done}/{doc.page_count} pages")

    doc.close()
    return out


def _ocr_page(page: "fitz.Page") -> str:
    """Render a PDF page at OCR_DPI and run tesseract on it."""
    import pytesseract
    from PIL import Image

    pix = page.get_pixmap(dpi=OCR_DPI, alpha=False)
    # Pixmap → PIL.Image via the raw samples buffer; avoids round-tripping
    # through PNG bytes (saves ~20% per page on a 73-page doc).
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(
        img,
        lang=OCR_LANG,
        config=f"--psm {OCR_PSM}",
    )


def _extract_page_layout_aware(page: "fitz.Page") -> str:
    """
    Extract a single page's text with column awareness.

    Strategy:
      1. Ask PyMuPDF for text blocks (each is a rect + multi-line string).
      2. Filter out graphical / tiny blocks.
      3. Cluster blocks by x-midpoint gaps → column count for this page.
      4. Sort blocks inside each column top-to-bottom; emit columns
         left-to-right.
    """
    raw_blocks = page.get_text("blocks") or []
    # Each item: (x0, y0, x1, y1, text, block_no, block_type)
    text_blocks = [
        b for b in raw_blocks
        if len(b) >= 7
        and b[6] == 0  # 0 = text block, 1 = image
        and (b[2] - b[0]) >= MIN_BLOCK_WIDTH_PT
        and (b[4] or "").strip()
    ]
    if not text_blocks:
        return ""

    # ── Detect columns via 1-D clustering on x-midpoints ──
    mids = sorted((b[0] + b[2]) / 2 for b in text_blocks)
    columns: List[Tuple[float, float]] = []  # [(lo, hi), ...] of x-midpoint
    cluster_start = mids[0]
    cluster_prev = mids[0]
    for m in mids[1:]:
        if m - cluster_prev > MIN_COLUMN_GAP_PT:
            columns.append((cluster_start, cluster_prev))
            cluster_start = m
        cluster_prev = m
    columns.append((cluster_start, cluster_prev))

    # Single-column fast path — preserve natural reading order from PyMuPDF.
    if len(columns) == 1:
        text_blocks.sort(key=lambda b: (round(b[1] / TOP_BUCKET_PT), b[0]))
        return "\n\n".join(b[4].strip() for b in text_blocks)

    # ── Assign each block to a column by midpoint proximity ──
    assigned: List[List[tuple]] = [[] for _ in columns]
    for b in text_blocks:
        mid = (b[0] + b[2]) / 2
        best = min(
            range(len(columns)),
            key=lambda i: abs(mid - (columns[i][0] + columns[i][1]) / 2),
        )
        assigned[best].append(b)

    # Within each column: top-to-bottom, tie-break on x0
    parts: List[str] = []
    for col_blocks in assigned:
        col_blocks.sort(key=lambda b: (round(b[1] / TOP_BUCKET_PT), b[0]))
        parts.append("\n\n".join(b[4].strip() for b in col_blocks))
    return "\n\n".join(parts)


def _extract_with_pypdf(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    """Full-document fallback when PyMuPDF can't open the file at all."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        logger.error(f"Both PyMuPDF and pypdf failed to open PDF: {e}")
        return []
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""
        if text:
            pages.append((i + 1, text))
    return pages
