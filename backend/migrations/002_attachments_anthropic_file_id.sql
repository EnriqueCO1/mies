-- ============================================================
-- Migration 002 — add anthropic_file_id to attachments.
--
-- Anthropic's Files API lets us upload an attachment once and reference
-- it by ID on subsequent requests instead of re-inlining base64 on
-- every turn. Per turn savings: ~3-8s latency + ~15-25k input tokens
-- per PDF / image attached to earlier messages.
--
-- Run once in the Supabase SQL editor. Idempotent.
-- ============================================================

alter table public.attachments
    add column if not exists anthropic_file_id text;

-- Partial index — only attachments that have been uploaded carry a value,
-- so this stays tiny (and lookups during chat use it for cache hits).
create index if not exists attachments_anthropic_file_id_idx
    on public.attachments (anthropic_file_id)
    where anthropic_file_id is not null;
