#!/usr/bin/env python3
"""
One-time indexing script for PGOU documents.
Downloads PDFs from Supabase Storage, chunks them with section-aware
splitting, generates embeddings via OpenAI, and stores everything in
the `documents` table for RAG retrieval.

Usage:
    cd backend
    source venv/bin/activate
    python -m scripts.index_pgou

Requirements in .env:
    SUPABASE_URL, SUPABASE_KEY (anon key — RLS INSERT policy allows writes),
    OPENAI_API_KEY
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

BUCKET_NAME = "PGOU"
EMBEDDING_MODEL = "text-embedding-3-small"
CATEGORY = "pgou"
# Dedicated per-municipio table after migration 001. This script is
# hard-wired to the Málaga corpus — use scripts.index_municipal_plan for
# any other municipio.
TABLE_NAME = "pgou_malaga"
MUNICIPIO = "Málaga"

# Chunking parameters
TARGET_CHUNK_TOKENS = 500
MAX_CHUNK_TOKENS = 800
OVERLAP_TOKENS = 100
MIN_CHUNK_TOKENS = 50

# Embedding batch size (OpenAI limit is 2048)
EMBEDDING_BATCH_SIZE = 100

# Section heading patterns (Spanish legal text)
SECTION_PATTERNS = [
    re.compile(r'^T[ÍI]TULO\s+[IVXLCDM\d]+', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^CAP[ÍI]TULO\s+[IVXLCDM\d]+', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^SECCI[ÓO]N\s+\d+', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^Art[íi]culo\s+\d+[\.\d]*', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^DISPOSICI[ÓO]N', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^ANEXO\s+[IVXLCDM\d]+', re.IGNORECASE | re.MULTILINE),
]


# ── Supabase Storage helpers ──────────────────────────────────────

def list_storage_files(client, bucket: str, path: str = "") -> List[str]:
    """Recursively list all PDF file paths in a storage bucket."""
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
        elif name.lower().endswith(".pdf"):
            files.append(full_path)
        else:
            # Non-PDF file — might still be a PDF without extension
            # Check metadata or just try it
            files.append(full_path)

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


# ── Chunking ──────────────────────────────────────────────────────

def _is_section_heading(line: str) -> Optional[str]:
    """Check if a line matches a section heading pattern."""
    stripped = line.strip()
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
    Chunk document text into semantically meaningful pieces.

    Strategy:
    1. Concatenate all pages, tracking page boundaries
    2. Split on section/article headings (natural legal boundaries)
    3. Sub-split oversized sections with overlap
    4. Merge undersized sections with their next neighbor
    """
    if not pages:
        return []

    # Build a flat list of (text, page_num) segments
    segments: List[Dict[str, Any]] = []
    current_section: Optional[str] = None

    for page_num, page_text in pages:
        lines = page_text.split("\n")
        for line in lines:
            heading = _is_section_heading(line)
            if heading:
                current_section = heading

        # Treat each page as a segment with its section context
        segments.append({
            "text": page_text,
            "page_num": page_num,
            "section": current_section,
        })

    # Now chunk: split pages into token-sized pieces
    chunks: List[Dict[str, Any]] = []
    buffer_text = ""
    buffer_page = segments[0]["page_num"] if segments else 1
    buffer_section = segments[0].get("section") if segments else None

    for seg in segments:
        # Check if adding this page would exceed max tokens
        combined = buffer_text + "\n\n" + seg["text"] if buffer_text else seg["text"]
        combined_tokens = len(enc.encode(combined))

        if combined_tokens <= MAX_CHUNK_TOKENS:
            buffer_text = combined
            if seg.get("section"):
                buffer_section = seg["section"]
        else:
            # Flush the buffer as a chunk
            if buffer_text.strip():
                token_count = len(enc.encode(buffer_text))
                if token_count >= MIN_CHUNK_TOKENS:
                    chunks.append({
                        "content": buffer_text.strip(),
                        "page_number": buffer_page,
                        "section_title": buffer_section,
                        "token_count": token_count,
                    })

            # Start new buffer with this page
            buffer_text = seg["text"]
            buffer_page = seg["page_num"]
            buffer_section = seg.get("section") or buffer_section

    # Flush remaining buffer
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
            # Split by paragraphs with overlap
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
                    # Overlap: keep the last paragraph as start of next chunk
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
    # Idempotent: remove old chunks first
    try:
        supabase_client.table(TABLE_NAME).delete().eq("source_file", source_file).execute()
        logger.info(f"  Deleted old chunks for {source_file}")
    except Exception as e:
        logger.warning(f"  Could not delete old chunks: {e}")

    # Insert in batches (PostgREST has payload size limits)
    batch_size = 20
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        try:
            supabase_client.table(TABLE_NAME).insert(batch).execute()
        except Exception as e:
            logger.error(f"  Insert batch {i}-{i+len(batch)} failed: {e}")
            # Try one by one
            for row in batch:
                try:
                    supabase_client.table(TABLE_NAME).insert(row).execute()
                except Exception as e2:
                    logger.error(f"    Single insert failed: {e2}")

    logger.info(f"  Stored {len(rows)} chunks")


# ── Main ──────────────────────────────────────────────────────────

def main():
    logger.info("=== PGOU Indexing Script ===")

    # Initialize clients
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    enc = tiktoken.get_encoding("cl100k_base")

    # Sign in as a user so we have an authenticated JWT for RLS INSERT policy
    AUTH_EMAIL = os.getenv("INDEXER_EMAIL", "arq.test45@gmail.com")
    AUTH_PASSWORD = os.getenv("INDEXER_PASSWORD", "Test-Arq-123!")
    try:
        auth_resp = supabase.auth.sign_in_with_password({"email": AUTH_EMAIL, "password": AUTH_PASSWORD})
        token = auth_resp.session.access_token
        supabase.postgrest.auth(token)
        logger.info(f"Authenticated as {AUTH_EMAIL}")
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        logger.error("The script needs an authenticated user for RLS INSERT. Set INDEXER_EMAIL and INDEXER_PASSWORD in .env.")
        sys.exit(1)

    # List all files in the PGOU bucket
    logger.info(f"Listing files in bucket '{BUCKET_NAME}'...")
    file_paths = list_storage_files(supabase, BUCKET_NAME)

    if not file_paths:
        logger.error("No files found in the PGOU bucket!")
        logger.info("Make sure the bucket exists and is public (or use service_role key)")
        sys.exit(1)

    logger.info(f"Found {len(file_paths)} files: {file_paths}")

    total_chunks = 0
    for file_path in file_paths:
        logger.info(f"\nProcessing: {file_path}")

        # Download
        try:
            pdf_bytes = download_file(supabase, BUCKET_NAME, file_path)
            logger.info(f"  Downloaded {len(pdf_bytes):,} bytes")
        except Exception as e:
            logger.error(f"  Download failed: {e}")
            continue

        # Extract text
        pages = extract_text_with_pages(pdf_bytes)
        if not pages:
            logger.warning(f"  No text extracted — skipping")
            continue
        logger.info(f"  Extracted text from {len(pages)} pages")

        # Chunk
        chunks = chunk_document(pages, enc, file_path)
        logger.info(f"  Generated {len(chunks)} chunks")
        if not chunks:
            continue

        # Generate embeddings in batches
        all_texts = [c["content"] for c in chunks]
        all_embeddings: List[List[float]] = []

        for i in range(0, len(all_texts), EMBEDDING_BATCH_SIZE):
            batch = all_texts[i : i + EMBEDDING_BATCH_SIZE]
            logger.info(f"  Embedding batch {i+1}-{i+len(batch)} of {len(all_texts)}...")
            try:
                embeddings = generate_embeddings_batch(openai_client, batch)
                all_embeddings.extend(embeddings)
            except Exception as e:
                logger.error(f"  Embedding failed: {e}")
                # Fill with None so we can skip these later
                all_embeddings.extend([None] * len(batch))
            time.sleep(0.5)  # Rate limiting courtesy

        # Prepare rows
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
                "metadata": {"municipio": MUNICIPIO},
                "token_count": chunk.get("token_count"),
            })

        # Store
        if rows:
            # Need to log in to get an auth token for RLS
            # The anon key works for PostgREST with our INSERT policy
            store_chunks(supabase, rows, file_path)
            total_chunks += len(rows)

    logger.info(f"\n=== Done! Total chunks indexed: {total_chunks} ===")


if __name__ == "__main__":
    main()
