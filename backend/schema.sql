-- ============================================
-- 45Labs Database Schema
-- Run this in your Supabase SQL Editor
-- ============================================

-- Profiles table (extends Supabase auth.users)
create table if not exists public.profiles (
    id uuid references auth.users(id) on delete cascade primary key,
    email text not null,
    name text not null,
    year text not null,
    subjects text[] not null default '{}',
    created_at timestamptz default now()
);

-- Conversations table
create table if not exists public.conversations (
    id uuid default gen_random_uuid() primary key,
    user_id uuid references public.profiles(id) on delete cascade not null,
    title text not null default 'New conversation',
    pinned boolean default false,
    created_at timestamptz default now()
);

-- Messages table
create table if not exists public.messages (
    id uuid default gen_random_uuid() primary key,
    conversation_id uuid references public.conversations(id) on delete cascade not null,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    sources jsonb default '[]'::jsonb,
    created_at timestamptz default now()
);

-- Indexes
create index if not exists idx_conversations_user_id on public.conversations(user_id);
create index if not exists idx_messages_conversation_id on public.messages(conversation_id);
create index if not exists idx_messages_created_at on public.messages(created_at);

-- Row Level Security
alter table public.profiles enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;

-- Profiles: users can only read/update their own profile
create policy "Users can view own profile"
    on public.profiles for select
    using (auth.uid() = id);

create policy "Users can update own profile"
    on public.profiles for update
    using (auth.uid() = id);

-- Conversations: users can only access their own
create policy "Users can view own conversations"
    on public.conversations for select
    using (auth.uid() = user_id);

create policy "Users can create conversations"
    on public.conversations for insert
    with check (auth.uid() = user_id);

create policy "Users can update own conversations"
    on public.conversations for update
    using (auth.uid() = user_id);

create policy "Users can delete own conversations"
    on public.conversations for delete
    using (auth.uid() = user_id);

-- Messages: users can access messages in their conversations
create policy "Users can view messages in own conversations"
    on public.messages for select
    using (
        conversation_id in (
            select id from public.conversations where user_id = auth.uid()
        )
    );

create policy "Users can create messages in own conversations"
    on public.messages for insert
    with check (
        conversation_id in (
            select id from public.conversations where user_id = auth.uid()
        )
    );

create policy "Users can delete messages in own conversations"
    on public.messages for delete
    using (
        conversation_id in (
            select id from public.conversations where user_id = auth.uid()
        )
    );
