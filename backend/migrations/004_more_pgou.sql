-- ============================================================
-- Migration 004 — four additional PGOU tables: Rincón de la Victoria,
-- Vélez-Málaga, Antequera, Alhaurín de la Torre.
--
-- Same shape as migrations 001 / 003: table, HNSW + GIN indexes,
-- RLS policies, match_* RPC, storage.objects SELECT policy.
--
-- Run once in the Supabase SQL editor. Idempotent.
-- ============================================================

-- 1. Tables
-- ------------------------------------------------------------

create table if not exists public.pgou_rincon (
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

create table if not exists public.pgou_velez_malaga (
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

create table if not exists public.pgou_antequera (
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

create table if not exists public.pgou_alhaurin_de_la_torre (
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


-- 2. Indexes
-- ------------------------------------------------------------

create index if not exists pgou_rincon_embedding_hnsw_idx
    on public.pgou_rincon using hnsw (embedding vector_cosine_ops);
create index if not exists pgou_rincon_fts_gin_idx
    on public.pgou_rincon using gin (fts);

create index if not exists pgou_velez_malaga_embedding_hnsw_idx
    on public.pgou_velez_malaga using hnsw (embedding vector_cosine_ops);
create index if not exists pgou_velez_malaga_fts_gin_idx
    on public.pgou_velez_malaga using gin (fts);

create index if not exists pgou_antequera_embedding_hnsw_idx
    on public.pgou_antequera using hnsw (embedding vector_cosine_ops);
create index if not exists pgou_antequera_fts_gin_idx
    on public.pgou_antequera using gin (fts);

create index if not exists pgou_alhaurin_de_la_torre_embedding_hnsw_idx
    on public.pgou_alhaurin_de_la_torre using hnsw (embedding vector_cosine_ops);
create index if not exists pgou_alhaurin_de_la_torre_fts_gin_idx
    on public.pgou_alhaurin_de_la_torre using gin (fts);


-- 3. Row-level security — authenticated reads + writes.
-- ------------------------------------------------------------

do $$
declare
    tbl text;
begin
    foreach tbl in array array[
        'pgou_rincon', 'pgou_velez_malaga',
        'pgou_antequera', 'pgou_alhaurin_de_la_torre'
    ] loop
        execute format('alter table public.%I enable row level security', tbl);

        execute format('drop policy if exists "%s_read"   on public.%I', tbl, tbl);
        execute format('drop policy if exists "%s_insert" on public.%I', tbl, tbl);
        execute format('drop policy if exists "%s_update" on public.%I', tbl, tbl);
        execute format('drop policy if exists "%s_delete" on public.%I', tbl, tbl);

        execute format('create policy "%s_read"   on public.%I for select to authenticated using (true)', tbl, tbl);
        execute format('create policy "%s_insert" on public.%I for insert to authenticated with check (true)', tbl, tbl);
        execute format('create policy "%s_update" on public.%I for update to authenticated using (true) with check (true)', tbl, tbl);
        execute format('create policy "%s_delete" on public.%I for delete to authenticated using (true)', tbl, tbl);
    end loop;
end $$;


-- 4. match_* RPCs — written out explicitly (see migration 003 note on
--    why we don't loop over these).
-- ------------------------------------------------------------

create or replace function public.match_pgou_rincon(
    query_embedding   vector(1536),
    match_count       int     default 8,
    match_threshold   float   default 0.25,
    search_query      text    default null
)
returns table (
    id uuid, content text, source_file text, source_bucket text,
    section_title text, page_number int, metadata jsonb, similarity float
)
language plpgsql stable
as $$
begin
    if search_query is null or length(trim(search_query)) = 0 then
        return query
        select t.id, t.content, t.source_file, t.source_bucket, t.section_title,
               t.page_number, t.metadata,
               (1 - (t.embedding <=> query_embedding))::float as similarity
        from public.pgou_rincon t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
        order by t.embedding <=> query_embedding asc
        limit match_count;
    else
        return query
        select t.id, t.content, t.source_file, t.source_bucket, t.section_title,
               t.page_number, t.metadata,
               ((1 - (t.embedding <=> query_embedding)) * 0.7
                + coalesce(ts_rank(t.fts, plainto_tsquery('spanish', search_query)), 0) * 0.3
               )::float as similarity
        from public.pgou_rincon t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
           or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;

create or replace function public.match_pgou_velez_malaga(
    query_embedding   vector(1536),
    match_count       int     default 8,
    match_threshold   float   default 0.25,
    search_query      text    default null
)
returns table (
    id uuid, content text, source_file text, source_bucket text,
    section_title text, page_number int, metadata jsonb, similarity float
)
language plpgsql stable
as $$
begin
    if search_query is null or length(trim(search_query)) = 0 then
        return query
        select t.id, t.content, t.source_file, t.source_bucket, t.section_title,
               t.page_number, t.metadata,
               (1 - (t.embedding <=> query_embedding))::float as similarity
        from public.pgou_velez_malaga t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
        order by t.embedding <=> query_embedding asc
        limit match_count;
    else
        return query
        select t.id, t.content, t.source_file, t.source_bucket, t.section_title,
               t.page_number, t.metadata,
               ((1 - (t.embedding <=> query_embedding)) * 0.7
                + coalesce(ts_rank(t.fts, plainto_tsquery('spanish', search_query)), 0) * 0.3
               )::float as similarity
        from public.pgou_velez_malaga t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
           or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;

create or replace function public.match_pgou_antequera(
    query_embedding   vector(1536),
    match_count       int     default 8,
    match_threshold   float   default 0.25,
    search_query      text    default null
)
returns table (
    id uuid, content text, source_file text, source_bucket text,
    section_title text, page_number int, metadata jsonb, similarity float
)
language plpgsql stable
as $$
begin
    if search_query is null or length(trim(search_query)) = 0 then
        return query
        select t.id, t.content, t.source_file, t.source_bucket, t.section_title,
               t.page_number, t.metadata,
               (1 - (t.embedding <=> query_embedding))::float as similarity
        from public.pgou_antequera t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
        order by t.embedding <=> query_embedding asc
        limit match_count;
    else
        return query
        select t.id, t.content, t.source_file, t.source_bucket, t.section_title,
               t.page_number, t.metadata,
               ((1 - (t.embedding <=> query_embedding)) * 0.7
                + coalesce(ts_rank(t.fts, plainto_tsquery('spanish', search_query)), 0) * 0.3
               )::float as similarity
        from public.pgou_antequera t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
           or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;

create or replace function public.match_pgou_alhaurin_de_la_torre(
    query_embedding   vector(1536),
    match_count       int     default 8,
    match_threshold   float   default 0.25,
    search_query      text    default null
)
returns table (
    id uuid, content text, source_file text, source_bucket text,
    section_title text, page_number int, metadata jsonb, similarity float
)
language plpgsql stable
as $$
begin
    if search_query is null or length(trim(search_query)) = 0 then
        return query
        select t.id, t.content, t.source_file, t.source_bucket, t.section_title,
               t.page_number, t.metadata,
               (1 - (t.embedding <=> query_embedding))::float as similarity
        from public.pgou_alhaurin_de_la_torre t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
        order by t.embedding <=> query_embedding asc
        limit match_count;
    else
        return query
        select t.id, t.content, t.source_file, t.source_bucket, t.section_title,
               t.page_number, t.metadata,
               ((1 - (t.embedding <=> query_embedding)) * 0.7
                + coalesce(ts_rank(t.fts, plainto_tsquery('spanish', search_query)), 0) * 0.3
               )::float as similarity
        from public.pgou_alhaurin_de_la_torre t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
           or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;


-- 5. Storage RLS — let authenticated users list + download each bucket.
-- ------------------------------------------------------------

drop policy if exists "Auth read bucket PGOU Rincon"               on storage.objects;
drop policy if exists "Auth read bucket PGOU Velez-Malaga"         on storage.objects;
drop policy if exists "Auth read bucket PGOU Antequera"            on storage.objects;
drop policy if exists "Auth read bucket PGOU Alhaurin de la Torre" on storage.objects;

create policy "Auth read bucket PGOU Rincon"
    on storage.objects for select to authenticated
    using (bucket_id = 'PGOU Rincon');

create policy "Auth read bucket PGOU Velez-Malaga"
    on storage.objects for select to authenticated
    using (bucket_id = 'PGOU Velez-Malaga');

create policy "Auth read bucket PGOU Antequera"
    on storage.objects for select to authenticated
    using (bucket_id = 'PGOU Antequera');

create policy "Auth read bucket PGOU Alhaurin de la Torre"
    on storage.objects for select to authenticated
    using (bucket_id = 'PGOU Alhaurin de la Torre');


-- 6. Verify. Run this separately after the migration:
--
--     select table_name from information_schema.tables
--      where table_schema = 'public'
--        and table_name like 'pgou_%'
--      order by table_name;
--
-- Expected (12 total):
--     pgou_alhaurin_de_la_torre
--     pgou_antequera
--     pgou_benalmadena
--     pgou_estepona
--     pgou_fuengirola
--     pgou_malaga
--     pgou_marbella
--     pgou_mijas
--     pgou_nerja
--     pgou_rincon
--     pgou_torremolinos
--     pgou_velez_malaga
