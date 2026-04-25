#!/usr/bin/env python3
"""
One-time indexing script for CTE documents (Código Técnico de la Edificación).

Downloads PDFs from the `CTE` Supabase Storage bucket, chunks them with
section-aware splitting tuned for the CTE structure (DB-SE, DB-SI, DB-SUA,
DB-HS, DB-HR, DB-HE, plus their Documentos de Apoyo), generates embeddings
via OpenAI, and stores everything in the `documents` table with
category='cte' for RAG retrieval.

Usage:
    cd backend
    source venv/bin/activate
    python -m scripts.index_cte

Requirements in .env:
    SUPABASE_URL, SUPABASE_KEY (anon key — RLS INSERT policy allows writes),
    OPENAI_API_KEY,
    INDEXER_EMAIL, INDEXER_PASSWORD (for an authenticated session)

Storage prerequisite:
    The authenticated user must be able to SELECT rows in storage.objects
    where bucket_id='CTE'. Create the policy in the SQL editor if needed:

        create policy "Authenticated users can read CTE bucket"
            on storage.objects for select
            to authenticated
            using (bucket_id = 'CTE');
"""

import io
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import tiktoken
from openai import OpenAI
from pypdf import PdfReader
from supabase import create_client

# ── Configuration ──────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Load .env
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

BUCKET_NAME = "CTE"
# Dedicated table after migration 001.
TABLE_NAME = "cte"
EMBEDDING_MODEL = "text-embedding-3-small"
CATEGORY = "cte"

# Chunking parameters — same as PGOU (consistent retrieval behaviour)
TARGET_CHUNK_TOKENS = 500
MAX_CHUNK_TOKENS = 800
OVERLAP_TOKENS = 100
MIN_CHUNK_TOKENS = 50

# Embedding batch size (OpenAI limit is 2048)
EMBEDDING_BATCH_SIZE = 100

# Section heading patterns tuned for CTE documents.
# Order matters — most specific first.
SECTION_PATTERNS = [
    # CTE Documento Básico marker, e.g. "DB-HE", "DB-SI 6"
    re.compile(r'^DB[\s\-]*(?:SE|SI|SUA|HS|HR|HE)(?:[\s\-]+\d+)?\b', re.IGNORECASE | re.MULTILINE),
    # "Parte I / Parte II"
    re.compile(r'^PARTE\s+[IVXLCDM]+\b', re.IGNORECASE | re.MULTILINE),
    # Spanish legal structure already used in PGOU
    re.compile(r'^T[ÍI]TULO\s+[IVXLCDM\d]+', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^CAP[ÍI]TULO\s+[IVXLCDM\d]+', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^SECCI[ÓO]N\s+[A-Z]*\s*\d+', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^SUBSECCI[ÓO]N\s+\d+', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^Art[íi]culo\s+\d+[\.\d]*', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^DISPOSICI[ÓO]N', re.IGNORECASE | re.MULTILINE),
    # CTE-specific appendices and reference tables
    re.compile(r'^AP[ÉE]NDICE\s+[A-Z]\b', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^ANEJO\s+[A-Z0-9]+', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^ANEXO\s+[A-Z0-9IVXLCDM]+', re.IGNORECASE | re.MULTILINE),
    # Documentos de Apoyo have DA-DB-xx-N labelling
    re.compile(r'^DA[\s\-]*DB[\s\-]*(?:SE|SI|SUA|HS|HR|HE)[\s\-]*\d*', re.IGNORECASE | re.MULTILINE),
    # Numeric subsections like "1", "1.1", "2.3.4"
    re.compile(r'^\d+(?:\.\d+){0,3}\s+[A-ZÁÉÍÓÚÑ][^\n]{2,}$', re.MULTILINE),
]

# Map a folder / file name to a Documento Básico code so we can surface it
# as metadata and improve retrieval. Structural (DB-SE) has sub-codes for
# each material (A acero, AE acciones en la edificación, C cimentaciones,
# F fábrica, M madera). Order matters — the more specific code wins, which
# is why the SE sub-codes are checked BEFORE bare "DB-SE".
DB_CODES = [
    "DB-SE-AE",
    "DB-SE-A",
    "DB-SE-C",
    "DB-SE-F",
    "DB-SE-M",
    "DB-SE",
    "DB-SUA",
    "DB-SI",
    "DB-HS",
    "DB-HR",
    "DB-HE",
]


# ── Supabase Storage helpers ──────────────────────────────────────

def list_storage_files(client, bucket: str, path: str = "") -> List[str]:
    """
    Recursively list file paths in a storage bucket that look like PDFs.
    We accept a file if any of:
      * its name ends with .pdf (case insensitive)
      * its metadata mimetype is application/pdf
      * its metadata contentLength is > 0 and the name has no extension
        (Supabase often accepts extensionless uploads, e.g. 'Parte I').
    Non-candidates are logged at debug level so we can diagnose misses.
    """
    files = []
    try:
        items = client.storage.from_(bucket).list(path, {"limit": 1000})
    except Exception as e:
        logger.warning(f"Could not list {bucket}/{path}: {e}")
        return files

    for item in items:
        name = item.get("name", "")
        item_id = item.get("id")
        full_path = f"{path}/{name}".lstrip("/") if path else name

        if item_id is None:
            # It's a folder — recurse
            files.extend(list_storage_files(client, bucket, full_path))
            continue

        meta = item.get("metadata") or {}
        mimetype = (meta.get("mimetype") or "").lower()
        lower_name = name.lower()
        _, ext = os.path.splitext(name)

        looks_like_pdf = (
            lower_name.endswith(".pdf")
            or mimetype == "application/pdf"
            or (not ext and meta.get("contentLength", 0) > 0)
        )

        if looks_like_pdf:
            files.append(full_path)
        else:
            logger.info(
                f"  Skipping non-PDF file: {full_path} "
                f"(mimetype={mimetype or 'unknown'})"
            )

    return files


def download_file(client, bucket: str, path: str) -> bytes:
    """Download a file from Supabase Storage."""
    return client.storage.from_(bucket).download(path)


# ── Text extraction ───────────────────────────────────────────────

def extract_text_with_pages(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    """Extract text from a PDF, returning (page_number, text) pairs."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        logger.error(f"Failed to read PDF: {e}")
        return []

    pages = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            pages.append((i + 1, text.strip()))
    return pages


# ── Metadata helpers ──────────────────────────────────────────────

def infer_db_code(source_file: str) -> Optional[str]:
    """
    Detect the CTE Documento Básico this file belongs to, from its path or
    name. Works for both main DBs (DB-HE.pdf, DB-SI 6/DB-SI.pdf) and
    Documentos de Apoyo (DA-DB-HE-1.pdf).
    """
    upper = source_file.upper().replace("_", "-").replace(" ", "-")
    for code in DB_CODES:
        if code in upper:
            return code
    # Documentos de Apoyo sometimes use DA-DB-xx(-sub)
    m = re.search(r"DA-?DB-?(SE(?:-[A-Z]{1,2})?|SUA|SI|HS|HR|HE)", upper)
    if m:
        return f"DB-{m.group(1)}"
    # DAs occasionally drop the "DB-" prefix and go straight to the DB code,
    # e.g. DA_SUA_Adecuacion.pdf, DA-DBHR-1.pdf. Normalise the dash after the
    # DA and look again.
    m = re.search(r"\bDA-?(?:DB)?-?(SE(?:-[A-Z]{1,2})?|SUA|SI|HS|HR|HE)\b", upper)
    if m:
        return f"DB-{m.group(1)}"
    return None


def is_support_document(source_file: str) -> bool:
    """
    True if this looks like a Documento de Apoyo (DA) rather than the main
    Documento Básico itself.
    """
    upper = source_file.upper()
    if "DOCUMENTO" in upper and "APOYO" in upper:
        return True
    if re.search(r"\bDA[-_\s]?DB", upper):
        return True
    return False


# ── Chunking ──────────────────────────────────────────────────────

def _is_section_heading(line: str) -> Optional[str]:
    """Check if a line matches a section heading pattern."""
    stripped = line.strip()
    if len(stripped) < 2 or len(stripped) > 160:
        return None
    for pattern in SECTION_PATTERNS:
        if pattern.match(stripped):
            return stripped
    return None


def chunk_document(
    pages: List[Tuple[int, str]],
    enc: tiktoken.Encoding,
    source_file: str,
) -> List[Dict[str, Any]]:
    """
    Chunk CTE document text into semantically meaningful pieces.

    Strategy (same shape as the PGOU indexer for consistency):
    1. Walk pages, tracking the most recently seen section heading.
    2. Accumulate page text into a buffer while it fits under
       MAX_CHUNK_TOKENS. When it would overflow, flush the buffer.
    3. Any chunk that still exceeds MAX_CHUNK_TOKENS gets re-split by
       paragraph, still carrying the section title + starting page.
    """
    if not pages:
        return []

    segments: List[Dict[str, Any]] = []
    current_section: Optional[str] = None

    for page_num, page_text in pages:
        lines = page_text.split("\n")
        for line in lines:
            heading = _is_section_heading(line)
            if heading:
                current_section = heading

        segments.append({
            "text": page_text,
            "page_num": page_num,
            "section": current_section,
        })

    chunks: List[Dict[str, Any]] = []
    buffer_text = ""
    buffer_page = segments[0]["page_num"] if segments else 1
    buffer_section = segments[0].get("section") if segments else None

    for seg in segments:
        combined = buffer_text + "\n\n" + seg["text"] if buffer_text else seg["text"]
        combined_tokens = len(enc.encode(combined))

        if combined_tokens <= MAX_CHUNK_TOKENS:
            buffer_text = combined
            if seg.get("section"):
                buffer_section = seg["section"]
        else:
            if buffer_text.strip():
                token_count = len(enc.encode(buffer_text))
                if token_count >= MIN_CHUNK_TOKENS:
                    chunks.append({
                        "content": buffer_text.strip(),
                        "page_number": buffer_page,
                        "section_title": buffer_section,
                        "token_count": token_count,
                    })

            buffer_text = seg["text"]
            buffer_page = seg["page_num"]
            buffer_section = seg.get("section") or buffer_section

    if buffer_text.strip():
        token_count = len(enc.encode(buffer_text))
        if token_count >= MIN_CHUNK_TOKENS:
            chunks.append({
                "content": buffer_text.strip(),
                "page_number": buffer_page,
                "section_title": buffer_section,
                "token_count": token_count,
            })

    # Sub-split any chunks that are still too large
    final_chunks: List[Dict[str, Any]] = []
    for chunk in chunks:
        if chunk["token_count"] <= MAX_CHUNK_TOKENS:
            final_chunks.append(chunk)
        else:
            paragraphs = chunk["content"].split("\n\n")
            sub_buffer = ""
            for para in paragraphs:
                test = sub_buffer + "\n\n" + para if sub_buffer else para
                if len(enc.encode(test)) <= TARGET_CHUNK_TOKENS:
                    sub_buffer = test
                else:
                    if sub_buffer.strip():
                        tc = len(enc.encode(sub_buffer))
                        if tc >= MIN_CHUNK_TOKENS:
                            final_chunks.append({
                                "content": sub_buffer.strip(),
                                "page_number": chunk["page_number"],
                                "section_title": chunk["section_title"],
                                "token_count": tc,
                            })
                    sub_buffer = para
            if sub_buffer.strip():
                tc = len(enc.encode(sub_buffer))
                if tc >= MIN_CHUNK_TOKENS:
                    final_chunks.append({
                        "content": sub_buffer.strip(),
                        "page_number": chunk["page_number"],
                        "section_title": chunk["section_title"],
                        "token_count": tc,
                    })

    return final_chunks


# ── Embeddings ────────────────────────────────────────────────────

def generate_embeddings_batch(
    openai_client: OpenAI,
    texts: List[str],
) -> List[List[float]]:
    """Generate embeddings for a batch of texts."""
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


# ── Storage ───────────────────────────────────────────────────────

def store_chunks(
    supabase_client,
    rows: List[Dict[str, Any]],
    source_file: str,
):
    """Delete existing chunks for this file, then insert new ones."""
    try:
        supabase_client.table(TABLE_NAME).delete().eq("source_file", source_file).execute()
        logger.info(f"  Deleted old chunks for {source_file}")
    except Exception as e:
        logger.warning(f"  Could not delete old chunks: {e}")

    batch_size = 20
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        try:
            supabase_client.table(TABLE_NAME).insert(batch).execute()
        except Exception as e:
            logger.error(f"  Insert batch {i}-{i+len(batch)} failed: {e}")
            for row in batch:
                try:
                    supabase_client.table(TABLE_NAME).insert(row).execute()
                except Exception as e2:
                    logger.error(f"    Single insert failed: {e2}")

    logger.info(f"  Stored {len(rows)} chunks")


# ── Main ──────────────────────────────────────────────────────────

def main():
    logger.info("=== CTE Indexing Script ===")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    enc = tiktoken.get_encoding("cl100k_base")

    AUTH_EMAIL = os.getenv("INDEXER_EMAIL", "arq.test45@gmail.com")
    AUTH_PASSWORD = os.getenv("INDEXER_PASSWORD", "Test-Arq-123!")
    try:
        auth_resp = supabase.auth.sign_in_with_password(
            {"email": AUTH_EMAIL, "password": AUTH_PASSWORD}
        )
        token = auth_resp.session.access_token
        supabase.postgrest.auth(token)
        logger.info(f"Authenticated as {AUTH_EMAIL}")
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        logger.error(
            "The script needs an authenticated user for RLS INSERT. "
            "Set INDEXER_EMAIL and INDEXER_PASSWORD in .env."
        )
        sys.exit(1)

    logger.info(f"Listing files in bucket '{BUCKET_NAME}'...")
    file_paths = list_storage_files(supabase, BUCKET_NAME)

    if not file_paths:
        logger.error(
            f"No files found in the '{BUCKET_NAME}' bucket!\n"
            "Checklist:\n"
            f"  1. The bucket '{BUCKET_NAME}' exists\n"
            f"  2. PDFs have been uploaded to it\n"
            f"  3. storage.objects has a SELECT policy that lets authenticated\n"
            f"     users read bucket_id='{BUCKET_NAME}'.\n"
            "     If not, run this in the SQL editor:\n"
            f"\n"
            f"     create policy \"Authenticated users can read CTE bucket\"\n"
            f"       on storage.objects for select\n"
            f"       to authenticated\n"
            f"       using (bucket_id = '{BUCKET_NAME}');\n"
        )
        sys.exit(1)

    logger.info(f"Found {len(file_paths)} files")
    for fp in file_paths:
        logger.info(f"  - {fp}")

    total_chunks = 0
    for file_path in file_paths:
        logger.info(f"\nProcessing: {file_path}")

        try:
            pdf_bytes = download_file(supabase, BUCKET_NAME, file_path)
            logger.info(f"  Downloaded {len(pdf_bytes):,} bytes")
        except Exception as e:
            logger.error(f"  Download failed: {e}")
            continue

        pages = extract_text_with_pages(pdf_bytes)
        if not pages:
            logger.warning(f"  No text extracted — skipping")
            continue
        logger.info(f"  Extracted text from {len(pages)} pages")

        chunks = chunk_document(pages, enc, file_path)
        logger.info(f"  Generated {len(chunks)} chunks")
        if not chunks:
            continue

        all_texts = [c["content"] for c in chunks]
        all_embeddings: List[List[float]] = []

        for i in range(0, len(all_texts), EMBEDDING_BATCH_SIZE):
            batch = all_texts[i : i + EMBEDDING_BATCH_SIZE]
            logger.info(
                f"  Embedding batch {i+1}-{i+len(batch)} of {len(all_texts)}..."
            )
            try:
                embeddings = generate_embeddings_batch(openai_client, batch)
                all_embeddings.extend(embeddings)
            except Exception as e:
                logger.error(f"  Embedding failed: {e}")
                all_embeddings.extend([None] * len(batch))
            time.sleep(0.5)

        db_code = infer_db_code(file_path)
        is_support = is_support_document(file_path)

        rows = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, all_embeddings)):
            if embedding is None:
                continue
            rows.append({
                "content": chunk["content"],
                "embedding": embedding,
                "source_file": file_path,
                "source_bucket": BUCKET_NAME,
                "section_title": chunk.get("section_title"),
                "page_number": chunk.get("page_number"),
                "chunk_index": idx,
                "category": CATEGORY,
                "metadata": {
                    "db_code": db_code,
                    "is_support_document": is_support,
                },
                "token_count": chunk.get("token_count"),
            })

        if rows:
            store_chunks(supabase, rows, file_path)
            total_chunks += len(rows)

    logger.info(f"\n=== Done! Total CTE chunks indexed: {total_chunks} ===")


if __name__ == "__main__":
    main()
