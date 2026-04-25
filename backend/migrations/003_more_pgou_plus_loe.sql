-- ============================================================
-- Migration 003 — six additional PGOU tables (Torremolinos,
-- Fuengirola, Mijas, Estepona, Nerja, Benalmádena) plus a dedicated
-- `loe` table for the Ley de Ordenación de la Edificación.
--
-- Also adds storage.objects SELECT policies for the seven buckets so
-- the indexer can list files inside each (download-by-path already
-- works, but .list() currently returns [] without a bucket-specific
-- policy — same asymmetry we hit on PGOM Marbella and CTE).
--
-- Run once in the Supabase SQL editor. Idempotent.
-- ============================================================

-- 1. Tables — same shape as pgou_malaga / cte (see migration 001).
-- ------------------------------------------------------------

create table if not exists public.pgou_torremolinos (
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

create table if not exists public.pgou_fuengirola (
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

create table if not exists public.pgou_mijas (
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

create table if not exists public.pgou_estepona (
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

create table if not exists public.pgou_nerja (
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

create table if not exists public.pgou_benalmadena (
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

create table if not exists public.loe (
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


-- 2. Indexes — HNSW for vector similarity, GIN for full-text.
-- ------------------------------------------------------------

create index if not exists pgou_torremolinos_embedding_hnsw_idx
    on public.pgou_torremolinos using hnsw (embedding vector_cosine_ops);
create index if not exists pgou_torremolinos_fts_gin_idx
    on public.pgou_torremolinos using gin (fts);

create index if not exists pgou_fuengirola_embedding_hnsw_idx
    on public.pgou_fuengirola using hnsw (embedding vector_cosine_ops);
create index if not exists pgou_fuengirola_fts_gin_idx
    on public.pgou_fuengirola using gin (fts);

create index if not exists pgou_mijas_embedding_hnsw_idx
    on public.pgou_mijas using hnsw (embedding vector_cosine_ops);
create index if not exists pgou_mijas_fts_gin_idx
    on public.pgou_mijas using gin (fts);

create index if not exists pgou_estepona_embedding_hnsw_idx
    on public.pgou_estepona using hnsw (embedding vector_cosine_ops);
create index if not exists pgou_estepona_fts_gin_idx
    on public.pgou_estepona using gin (fts);

create index if not exists pgou_nerja_embedding_hnsw_idx
    on public.pgou_nerja using hnsw (embedding vector_cosine_ops);
create index if not exists pgou_nerja_fts_gin_idx
    on public.pgou_nerja using gin (fts);

create index if not exists pgou_benalmadena_embedding_hnsw_idx
    on public.pgou_benalmadena using hnsw (embedding vector_cosine_ops);
create index if not exists pgou_benalmadena_fts_gin_idx
    on public.pgou_benalmadena using gin (fts);

create index if not exists loe_embedding_hnsw_idx
    on public.loe using hnsw (embedding vector_cosine_ops);
create index if not exists loe_fts_gin_idx
    on public.loe using gin (fts);


-- 3. Row-level security — authenticated reads + writes, anon blocked.
-- ------------------------------------------------------------

do $$
declare
    tbl text;
begin
    foreach tbl in array array[
        'pgou_torremolinos', 'pgou_fuengirola', 'pgou_mijas',
        'pgou_estepona', 'pgou_nerja', 'pgou_benalmadena', 'loe'
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


-- 4. match_* RPCs — identical signature to migration 001's, one per table.
--    Written out explicitly instead of via a DO-loop with format(), so
--    the inner `as $$ … $$` function bodies don't ambiguously close the
--    outer DO block's dollar-quoting.
-- ------------------------------------------------------------

create or replace function public.match_pgou_torremolinos(
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
        from public.pgou_torremolinos t
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
        from public.pgou_torremolinos t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
           or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;

create or replace function public.match_pgou_fuengirola(
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
        from public.pgou_fuengirola t
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
        from public.pgou_fuengirola t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
           or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;

create or replace function public.match_pgou_mijas(
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
        from public.pgou_mijas t
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
        from public.pgou_mijas t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
           or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;

create or replace function public.match_pgou_estepona(
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
        from public.pgou_estepona t
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
        from public.pgou_estepona t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
           or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;

create or replace function public.match_pgou_nerja(
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
        from public.pgou_nerja t
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
        from public.pgou_nerja t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
           or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;

create or replace function public.match_pgou_benalmadena(
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
        from public.pgou_benalmadena t
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
        from public.pgou_benalmadena t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
           or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;

create or replace function public.match_loe(
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
        from public.loe t
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
        from public.loe t
        where (1 - (t.embedding <=> query_embedding)) > match_threshold
           or t.fts @@ plainto_tsquery('spanish', search_query)
        order by similarity desc
        limit match_count;
    end if;
end;
$$;


-- 5. Storage RLS — let authenticated users list + download each new bucket.
-- ------------------------------------------------------------
--
-- Without these, storage.from_(bucket).list('') silently returns [] for
-- authenticated users even when the bucket has files (the same
-- asymmetry we hit on 'CTE' and 'PGOM Marbella').
--
-- Policy names are identifiers, not string literals — that's why this
-- is easier to write out explicitly than via format(%I, …) inside a
-- DO-loop.

drop policy if exists "Auth read bucket PGOU Torremolinos"  on storage.objects;
drop policy if exists "Auth read bucket PGOU Fuengirola"    on storage.objects;
drop policy if exists "Auth read bucket PGOU Mijas"         on storage.objects;
drop policy if exists "Auth read bucket PGOU Estepona"      on storage.objects;
drop policy if exists "Auth read bucket PGOU Nerja"         on storage.objects;
drop policy if exists "Auth read bucket PGOU Benalmadena"   on storage.objects;
drop policy if exists "Auth read bucket LOE"                on storage.objects;

create policy "Auth read bucket PGOU Torremolinos"
    on storage.objects for select to authenticated
    using (bucket_id = 'PGOU Torremolinos');

create policy "Auth read bucket PGOU Fuengirola"
    on storage.objects for select to authenticated
    using (bucket_id = 'PGOU Fuengirola');

create policy "Auth read bucket PGOU Mijas"
    on storage.objects for select to authenticated
    using (bucket_id = 'PGOU Mijas');

create policy "Auth read bucket PGOU Estepona"
    on storage.objects for select to authenticated
    using (bucket_id = 'PGOU Estepona');

create policy "Auth read bucket PGOU Nerja"
    on storage.objects for select to authenticated
    using (bucket_id = 'PGOU Nerja');

create policy "Auth read bucket PGOU Benalmadena"
    on storage.objects for select to authenticated
    using (bucket_id = 'PGOU Benalmadena');

create policy "Auth read bucket LOE"
    on storage.objects for select to authenticated
    using (bucket_id = 'LOE');


-- 6. Verify. Run this separately after the migration:
--
--     select table_name, 0 as rows from information_schema.tables
--     where table_schema = 'public'
--       and table_name in (
--         'pgou_malaga','pgou_marbella','pgou_torremolinos','pgou_fuengirola',
--         'pgou_mijas','pgou_estepona','pgou_nerja','pgou_benalmadena','cte','loe'
--       );
