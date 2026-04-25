#!/usr/bin/env python3
"""
Indexer for any municipal-plan corpus (PGOU, PGOM, NNSS, POM, etc.).

One script, many municipalities. Every chunk is stored with:
    category             = 'pgou'
    source_bucket        = the Supabase bucket it came from
    metadata.municipio   = the municipality the plan governs

So the chat's `search_normativa` tool can filter semantic results to the
municipio of the current project. PGOU de Málaga and PGOM de Marbella
live side by side without polluting each other's results.

Usage:
    cd backend
    source venv/bin/activate
    python -m scripts.index_municipal_plan --bucket "PGOM Marbella" --municipio "Marbella"

The indexer uses the PyMuPDF-based layout-aware extractor from
`scripts._extract`, so 1-column and multi-column PDFs both come out
correctly — critical for PGOM Marbella which is laid out in 3 columns.

Requirements in .env:
    SUPABASE_URL, SUPABASE_KEY,
    OPENAI_API_KEY,
    INDEXER_EMAIL, INDEXER_PASSWORD

Storage prerequisite (per bucket, one-time):
    Authenticated users must be able to SELECT rows in storage.objects
    for the target bucket. Example for 'PGOM Marbella':

        create policy "Authenticated read — PGOM Marbella"
            on storage.objects for select
            to authenticated
            using (bucket_id = 'PGOM Marbella');
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client

from scripts._extract import extract_text_with_pages

# ── Configuration ──────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_CATEGORY = "pgou"  # default; override via --category

# Chunking — same shape as index_pgou / index_cte for retrieval parity
TARGET_CHUNK_TOKENS = 500
MAX_CHUNK_TOKENS = 800
MIN_CHUNK_TOKENS = 50
EMBEDDING_BATCH_SIZE = 100

# Spanish legal-text section patterns — covers PGOU, PGOM, NNSS, ordenanzas
SECTION_PATTERNS = [
    re.compile(r"^T[ÍI]TULO\s+[IVXLCDM\d]+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^CAP[ÍI]TULO\s+[IVXLCDM\d]+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^SECCI[ÓO]N\s+[A-Z]*\s*\d+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Art[íi]culo\s+\d+[\.\d]*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^DISPOSICI[ÓO]N", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^AP[ÉE]NDICE\s+[A-Z]\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^ANEJO\s+[A-Z0-9]+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^ANEXO\s+[IVXLCDM\d]+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^NORMA\s+\d+", re.IGNORECASE | re.MULTILINE),
    # Common numeric subsections: "12.2.55", "4.1", "Art. 12.2.55"
    re.compile(r"^\d+(?:\.\d+){1,3}\b\s*[A-ZÁÉÍÓÚÑ]?", re.MULTILINE),
]


# ── Storage helpers ───────────────────────────────────────────────

def list_storage_files(client, bucket: str, path: str = "") -> List[str]:
    """Recursively list PDF-looking file paths inside a Supabase bucket."""
    files: List[str] = []
    try:
        items = client.storage.from_(bucket).list(path, {"limit": 1000})
    except Exception as e:
        logger.warning(f"Could not list {bucket!r}/{path!r}: {e}")
        return files

    for item in items:
        name = item.get("name", "")
        item_id = item.get("id")
        full_path = f"{path}/{name}".lstrip("/") if path else name

        if item_id is None:
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
            logger.info(f"  Skipping non-PDF: {full_path} (mime={mimetype or 'unknown'})")
    return files


def download_file(client, bucket: str, path: str) -> bytes:
    return client.storage.from_(bucket).download(path)


# ── Chunking ──────────────────────────────────────────────────────

def _is_section_heading(line: str) -> Optional[str]:
    stripped = line.strip()
    if len(stripped) < 2 or len(stripped) > 160:
        return None
    for pat in SECTION_PATTERNS:
        if pat.match(stripped):
            return stripped
    return None


def chunk_document(
    pages: List[Tuple[int, str]],
    enc: tiktoken.Encoding,
) -> List[Dict[str, Any]]:
    """Token-bounded, section-aware chunking. Same shape as other indexers."""
    if not pages:
        return []

    segments: List[Dict[str, Any]] = []
    current_section: Optional[str] = None
    for page_num, page_text in pages:
        for line in page_text.split("\n"):
            heading = _is_section_heading(line)
            if heading:
                current_section = heading
        segments.append(
            {"text": page_text, "page_num": page_num, "section": current_section}
        )

    # Accumulate up to MAX_CHUNK_TOKENS per chunk, carrying section + start page
    chunks: List[Dict[str, Any]] = []
    buf = ""
    buf_page = segments[0]["page_num"]
    buf_section = segments[0].get("section")

    for seg in segments:
        combined = buf + "\n\n" + seg["text"] if buf else seg["text"]
        if len(enc.encode(combined)) <= MAX_CHUNK_TOKENS:
            buf = combined
            buf_section = seg.get("section") or buf_section
        else:
            if buf.strip():
                tc = len(enc.encode(buf))
                if tc >= MIN_CHUNK_TOKENS:
                    chunks.append(
                        {
                            "content": buf.strip(),
                            "page_number": buf_page,
                            "section_title": buf_section,
                            "token_count": tc,
                        }
                    )
            buf = seg["text"]
            buf_page = seg["page_num"]
            buf_section = seg.get("section") or buf_section

    if buf.strip():
        tc = len(enc.encode(buf))
        if tc >= MIN_CHUNK_TOKENS:
            chunks.append(
                {
                    "content": buf.strip(),
                    "page_number": buf_page,
                    "section_title": buf_section,
                    "token_count": tc,
                }
            )

    # Re-split any chunks that remain over MAX by paragraph
    final: List[Dict[str, Any]] = []
    for chunk in chunks:
        if chunk["token_count"] <= MAX_CHUNK_TOKENS:
            final.append(chunk)
            continue
        paragraphs = chunk["content"].split("\n\n")
        sub = ""
        for para in paragraphs:
            test = sub + "\n\n" + para if sub else para
            if len(enc.encode(test)) <= TARGET_CHUNK_TOKENS:
                sub = test
            else:
                if sub.strip():
                    tc = len(enc.encode(sub))
                    if tc >= MIN_CHUNK_TOKENS:
                        final.append(
                            {
                                "content": sub.strip(),
                                "page_number": chunk["page_number"],
                                "section_title": chunk["section_title"],
                                "token_count": tc,
                            }
                        )
                sub = para
        if sub.strip():
            tc = len(enc.encode(sub))
            if tc >= MIN_CHUNK_TOKENS:
                final.append(
                    {
                        "content": sub.strip(),
                        "page_number": chunk["page_number"],
                        "section_title": chunk["section_title"],
                        "token_count": tc,
                    }
                )
    return final


# ── Embeddings + storage ─────────────────────────────────────────

def embed_batch(oa: OpenAI, texts: List[str]) -> List[List[float]]:
    resp = oa.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def store_chunks(
    client,
    table: str,
    rows: List[Dict[str, Any]],
    source_file: str,
) -> None:
    try:
        client.table(table).delete().eq("source_file", source_file).execute()
        logger.info(f"  Deleted old chunks in {table!r} for {source_file}")
    except Exception as e:
        logger.warning(f"  Could not delete old chunks: {e}")

    for i in range(0, len(rows), 20):
        batch = rows[i : i + 20]
        try:
            client.table(table).insert(batch).execute()
        except Exception as e:
            logger.error(f"  Insert batch {i}-{i+len(batch)} failed: {e}")
            for row in batch:
                try:
                    client.table(table).insert(row).execute()
                except Exception as e2:
                    logger.error(f"    Single insert failed: {e2}")
    logger.info(f"  Stored {len(rows)} chunks into {table!r}")


def _slug_municipio(value: str) -> str:
    """
    Turn a free-form municipio string into a canonical PostgreSQL-safe
    slug: lowercase, accents stripped, non-alphanum collapsed to `_`.
    Used to derive the default table name (`pgou_<slug>`).
    """
    import unicodedata
    folded = unicodedata.normalize("NFD", value.strip())
    ascii_only = "".join(c for c in folded if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_only).strip("_").lower()
    return slug or "unknown"


# ── Main ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index a municipal urbanism-plan bucket as category='pgou'",
    )
    parser.add_argument(
        "--bucket",
        required=True,
        help="Supabase storage bucket name (e.g. 'PGOU', 'PGOM Marbella').",
    )
    parser.add_argument(
        "--municipio",
        required=False,
        default=None,
        help=(
            "Municipality name to stamp on every chunk's "
            "metadata.municipio (e.g. 'Marbella'). Omit for national-"
            "level corpora like LOE."
        ),
    )
    parser.add_argument(
        "--category",
        default=DEFAULT_CATEGORY,
        help=(
            "Logical category stored on every chunk (default: 'pgou'). "
            "Use 'loe' for the Ley de Ordenación de la Edificación, "
            "'cte' for Código Técnico, etc."
        ),
    )
    parser.add_argument(
        "--files",
        nargs="+",
        default=None,
        help=(
            "Optional explicit list of file paths inside the bucket. "
            "Bypasses .list() — useful when storage.objects has an RLS "
            "policy that allows downloads but not listing. Example:\n"
            "  --files '2 Normativa urbanistica.pdf'"
        ),
    )
    parser.add_argument(
        "--table",
        default=None,
        help=(
            "Override the target table name. By default inferred as "
            "`pgou_<slug(municipio)>` — e.g. --municipio 'Marbella' "
            "writes to `pgou_marbella`. Use this if your corpus lives "
            "in a table whose name doesn't follow that pattern."
        ),
    )
    args = parser.parse_args()

    # Table name inference:
    #   --table <x>               → use <x>
    #   --municipio <m>           → pgou_<slug(m)>
    #   (neither)                 → need --table or --municipio
    if args.table:
        table_name = args.table
    elif args.municipio:
        table_name = f"pgou_{_slug_municipio(args.municipio)}"
    else:
        logger.error(
            "Either --table or --municipio must be provided. "
            "Examples:\n"
            "  --bucket 'PGOU Mijas'       --municipio 'Mijas'\n"
            "  --bucket 'LOE' --table loe  --category loe"
        )
        sys.exit(1)

    logger.info(
        f"=== Corpus indexer: bucket={args.bucket!r}  "
        f"municipio={args.municipio!r}  category={args.category!r}  "
        f"table={table_name!r} ==="
    )

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    oa = OpenAI(api_key=OPENAI_API_KEY)
    enc = tiktoken.get_encoding("cl100k_base")

    auth_email = os.getenv("INDEXER_EMAIL", "arq.test45@gmail.com")
    auth_password = os.getenv("INDEXER_PASSWORD", "Test-Arq-123!")
    try:
        resp = supabase.auth.sign_in_with_password(
            {"email": auth_email, "password": auth_password}
        )
        supabase.postgrest.auth(resp.session.access_token)
        logger.info(f"Authenticated as {auth_email}")
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)

    if args.files:
        file_paths = list(args.files)
        logger.info(f"Using explicit file list ({len(file_paths)} files) — skipping .list()")
    else:
        file_paths = list_storage_files(supabase, args.bucket)
        if not file_paths:
            logger.error(
                f"No files found in bucket {args.bucket!r}. Check:\n"
                f"  1. The bucket name is exact (case sensitive).\n"
                f"  2. Files are uploaded.\n"
                f"  3. storage.objects has a SELECT policy for bucket_id='{args.bucket}' "
                f"for the `authenticated` role.\n"
                f"  4. If downloads work but listing is blocked, re-run with "
                f"--files '<exact file path>'."
            )
            sys.exit(1)

    logger.info(f"Found {len(file_paths)} file(s):")
    for fp in file_paths:
        logger.info(f"  - {fp}")

    total_chunks = 0
    for file_path in file_paths:
        logger.info(f"\nProcessing: {file_path}")
        try:
            pdf_bytes = download_file(supabase, args.bucket, file_path)
            logger.info(f"  Downloaded {len(pdf_bytes):,} bytes")
        except Exception as e:
            logger.error(f"  Download failed: {e}")
            continue

        pages = extract_text_with_pages(pdf_bytes)
        if not pages:
            logger.warning("  No text extracted — skipping")
            continue
        logger.info(f"  Extracted text from {len(pages)} pages (layout-aware)")

        chunks = chunk_document(pages, enc)
        logger.info(f"  Generated {len(chunks)} chunks")
        if not chunks:
            continue

        all_texts = [c["content"] for c in chunks]
        all_embeddings: List[Optional[List[float]]] = []
        for i in range(0, len(all_texts), EMBEDDING_BATCH_SIZE):
            batch = all_texts[i : i + EMBEDDING_BATCH_SIZE]
            logger.info(f"  Embedding batch {i + 1}-{i + len(batch)} of {len(all_texts)}")
            try:
                all_embeddings.extend(embed_batch(oa, batch))
            except Exception as e:
                logger.error(f"  Embedding failed: {e}")
                all_embeddings.extend([None] * len(batch))
            time.sleep(0.5)

        rows = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, all_embeddings)):
            if embedding is None:
                continue
            rows.append(
                {
                    "content": chunk["content"],
                    "embedding": embedding,
                    "source_file": file_path,
                    "source_bucket": args.bucket,
                    "section_title": chunk.get("section_title"),
                    "page_number": chunk.get("page_number"),
                    "chunk_index": idx,
                    "category": args.category,
                    # Only tag the municipio when it's provided — omit
                    # the key entirely for national-level corpora like
                    # LOE so metadata stays honest.
                    "metadata": (
                        {"municipio": args.municipio}
                        if args.municipio else {}
                    ),
                    "token_count": chunk.get("token_count"),
                }
            )

        if rows:
            store_chunks(supabase, table_name, rows, file_path)
            total_chunks += len(rows)

    logger.info(
        f"\n=== Done! {total_chunks} chunks indexed into {table_name!r} "
        f"(bucket={args.bucket!r}, municipio={args.municipio!r}) ==="
    )


if __name__ == "__main__":
    main()
