-- ============================================================
-- Migration 001 — split the `documents` RAG table into three
-- per-corpus tables, each with its own HNSW index and match_* RPC.
--
-- Run once in the Supabase SQL editor (as postgres). Idempotent —
-- every statement uses IF NOT EXISTS / CREATE OR REPLACE, so re-
-- running won't damage anything.
--
-- The old `public.documents` table is left intact so you can verify
-- the new tables before dropping it. When you're ready:
--
--     drop table public.documents;
-- ============================================================

-- 1. Tables (identical shape to documents, plus the stored `fts`
--    tsvector used for hybrid search).
-- ------------------------------------------------------------

create table if not exists public.pgou_malaga (
    id              uuid         primary key default gen_random_uuid(),
    content         text         not null,
    embedding       vector(1536) not null,
    source_file     text,
    source_bucket   text,
    section_title   text,
    page_number     int,
    chunk_index     int,
    category        text,
    metadata        jsonb        not null default '{}'::jsonb,
    token_count     int,
    created_at      timestamptz  not null default now(),
    fts             tsvector generated always as
                        (to_tsvector('spanish', coalesce(content, ''))) stored
);

create table if not exists public.pgou_marbella (
    id              uuid         primary key default gen_random_uuid(),
    content         text         not null,
    embedding       vector(1536) not null,
    source_file     text,
    source_bucket   text,
    section_title   text,
    page_number     int,
    chunk_index     int,
    category        text,
    metadata        jsonb        not null default '{}'::jsonb,
    token_count     int,
    created_at      timestamptz  not null default now(),
    fts             tsvector generated always as
                        (to_tsvector('spanish', coalesce(content, ''))) stored
);

create table if not exists public.cte (
    id              uuid         primary key default gen_random_uuid(),
    content         text         not null,
    embedding       vector(1536) not null,
    source_file     text,
    source_bucket   text,
    section_title   text,
    page_number     int,
    chunk_index     int,
    category        text,
    metadata        jsonb        not null default '{}'::jsonb,
    token_count     int,
    created_at      timestamptz  not null default now(),
    fts             tsvector generated always as
                        (to_tsvector('spanish', coalesce(content, ''))) stored
);


-- 2. Indexes (HNSW for vector similarity, GIN for full-text).
-- ------------------------------------------------------------

create index if not exists pgou_malaga_embedding_hnsw_idx
    on public.pgou_malaga using hnsw (embedding vector_cosine_ops);
create index if not exists pgou_malaga_fts_gin_idx
    on public.pgou_malaga using gin (fts);

create index if not exists pgou_marbella_embedding_hnsw_idx
    on public.pgou_marbella using hnsw (embedding vector_cosine_ops);
create index if not exists pgou_marbella_fts_gin_idx
    on public.pgou_marbella using gin (fts);

create index if not exists cte_embedding_hnsw_idx
    on public.cte using hnsw (embedding vector_cosine_ops);
create index if not exists cte_fts_gin_idx
    on public.cte using gin (fts);


-- 3. Row-level security — authenticated users read + write; anon blocked.
-- ------------------------------------------------------------

alter table public.pgou_malaga   enable row level security;
alter table public.pgou_marbella enable row level security;
alter table public.cte           enable row level security;

-- pgou_malaga
drop policy if exists "pgou_malaga_read"   on public.pgou_malaga;
drop policy if exists "pgou_malaga_insert" on public.pgou_malaga;
drop policy if exists "pgou_malaga_update" on public.pgou_malaga;
drop policy if exists "pgou_malaga_delete" on public.pgou_malaga;
create policy "pgou_malaga_read"   on public.pgou_malaga for select to authenticated using (true);
create policy "pgou_malaga_insert" on public.pgou_malaga for insert to authenticated with check (true);
create policy "pgou_malaga_update" on public.pgou_malaga for update to authenticated using (true) with check (true);
create policy "pgou_malaga_delete" on public.pgou_malaga for delete to authenticated using (true);

-- pgou_marbella
drop policy if exists "pgou_marbella_read"   on public.pgou_marbella;
drop policy if exists "pgou_marbella_insert" on public.pgou_marbella;
drop policy if exists "pgou_marbella_update" on public.pgou_marbella;
drop policy if exists "pgou_marbella_delete" on public.pgou_marbella;
create policy "pgou_marbella_read"   on public.pgou_marbella for select to authenticated using (true);
create policy "pgou_marbella_insert" on public.pgou_marbella for insert to authenticated with check (true);
create policy "pgou_marbella_update" on public.pgou_marbella for update to authenticated using (true) with check (true);
create policy "pgou_marbella_delete" on public.pgou_marbella for delete to authenticated using (true);

-- cte
drop policy if exists "cte_read"   on public.cte;
drop policy if exists "cte_insert" on public.cte;
drop policy if exists "cte_update" on public.cte;
drop policy if exists "cte_delete" on public.cte;
create policy "cte_read"   on public.cte for select to authenticated using (true);
create policy "cte_insert" on public.cte for insert to authenticated with check (true);
create policy "cte_update" on public.cte for update to authenticated using (true) with check (true);
create policy "cte_delete" on public.cte for delete to authenticated using (true);


-- 4. Match RPCs — one per table, identical signature.
--    Vector search always; adds tsvector hybrid ranking when
--    `search_query` is supplied (used for article/section refs).
-- ------------------------------------------------------------

create or replace function public.match_pgou_malaga(
    query_embedding   vector(1536),
    match_count       int     default 8,
    match_threshold   float   default 0.25,
    search_query      text    default null
)
returns table (
    id              uuid,
    content         text,
    source_file     text,
    source_bucket   text,
    section_title   text,
    page_number     int,
    metadata        jsonb,
    similarity      float
)
language plpgsql stable
as $$
begin
    if search_query is null or length(trim(search_query)) = 0 then
        return query
        select
            t.id, t.content, t.source_file, t.source_bucket, t.section_title,
            t.page_number, t.metadata,
            (1 - (t.embedding <=> query_embedding))::float as similarity
        from public.pgou_malaga t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
        order by t.embedding <=> query_embedding asc
        limit match_count;
    else
        return query
        select
            t.id, t.content, t.source_file, t.source_bucket, t.section_title,
            t.page_number, t.metadata,
            ((1 - (t.embedding <=> query_embedding)) * 0.7
             + coalesce(ts_rank(t.fts, plainto_tsquery('spanish', search_query)), 0) * 0.3
            )::float as similarity
        from public.pgou_malaga t
        where
            (1 - (t.embedding <=> query_embedding)) > match_threshold
            or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;

create or replace function public.match_pgou_marbella(
    query_embedding   vector(1536),
    match_count       int     default 8,
    match_threshold   float   default 0.25,
    search_query      text    default null
)
returns table (
    id              uuid,
    content         text,
    source_file     text,
    source_bucket   text,
    section_title   text,
    page_number     int,
    metadata        jsonb,
    similarity      float
)
language plpgsql stable
as $$
begin
    if search_query is null or length(trim(search_query)) = 0 then
        return query
        select
            t.id, t.content, t.source_file, t.source_bucket, t.section_title,
            t.page_number, t.metadata,
            (1 - (t.embedding <=> query_embedding))::float as similarity
        from public.pgou_marbella t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
        order by t.embedding <=> query_embedding asc
        limit match_count;
    else
        return query
        select
            t.id, t.content, t.source_file, t.source_bucket, t.section_title,
            t.page_number, t.metadata,
            ((1 - (t.embedding <=> query_embedding)) * 0.7
             + coalesce(ts_rank(t.fts, plainto_tsquery('spanish', search_query)), 0) * 0.3
            )::float as similarity
        from public.pgou_marbella t
        where
            (1 - (t.embedding <=> query_embedding)) > match_threshold
            or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;

create or replace function public.match_cte(
    query_embedding   vector(1536),
    match_count       int     default 8,
    match_threshold   float   default 0.25,
    search_query      text    default null
)
returns table (
    id              uuid,
    content         text,
    source_file     text,
    source_bucket   text,
    section_title   text,
    page_number     int,
    metadata        jsonb,
    similarity      float
)
language plpgsql stable
as $$
begin
    if search_query is null or length(trim(search_query)) = 0 then
        return query
        select
            t.id, t.content, t.source_file, t.source_bucket, t.section_title,
            t.page_number, t.metadata,
            (1 - (t.embedding <=> query_embedding))::float as similarity
        from public.cte t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
        order by t.embedding <=> query_embedding asc
        limit match_count;
    else
        return query
        select
            t.id, t.content, t.source_file, t.source_bucket, t.section_title,
            t.page_number, t.metadata,
            ((1 - (t.embedding <=> query_embedding)) * 0.7
             + coalesce(ts_rank(t.fts, plainto_tsquery('spanish', search_query)), 0) * 0.3
            )::float as similarity
        from public.cte t
        where
            (1 - (t.embedding <=> query_embedding)) > match_threshold
            or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;


-- 5. Copy existing rows from public.documents into the new tables.
--    `on conflict do nothing` so the migration stays idempotent.
-- ------------------------------------------------------------

insert into public.pgou_malaga (
    id, content, embedding, source_file, source_bucket, section_title,
    page_number, chunk_index, category, metadata, token_count, created_at
)
select id, content, embedding, source_file, source_bucket, section_title,
       page_number, chunk_index, category, metadata, token_count, created_at
from public.documents
where source_bucket = 'PGOU'
on conflict (id) do nothing;

insert into public.pgou_marbella (
    id, content, embedding, source_file, source_bucket, section_title,
    page_number, chunk_index, category, metadata, token_count, created_at
)
select id, content, embedding, source_file, source_bucket, section_title,
       page_number, chunk_index, category, metadata, token_count, created_at
from public.documents
where source_bucket = 'PGOM Marbella'
on conflict (id) do nothing;

insert into public.cte (
    id, content, embedding, source_file, source_bucket, section_title,
    page_number, chunk_index, category, metadata, token_count, created_at
)
select id, content, embedding, source_file, source_bucket, section_title,
       page_number, chunk_index, category, metadata, token_count, created_at
from public.documents
where source_bucket = 'CTE'
on conflict (id) do nothing;


-- 6. Verify row counts match what you had in `documents`.
-- Run this query on its own after the migration completes:
--
--     select 'pgou_malaga'   as t, count(*) from public.pgou_malaga
--     union all select 'pgou_marbella', count(*) from public.pgou_marbella
--     union all select 'cte',           count(*) from public.cte
--     union all select 'documents',     count(*) from public.documents;
--
-- Expected:
--     pgou_malaga    1445
--     pgou_marbella   362
--     cte            1114
--     documents      2921   (unchanged until you drop it manually)
