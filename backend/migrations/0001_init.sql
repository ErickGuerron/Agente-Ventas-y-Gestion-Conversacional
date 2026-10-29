-- Initial schema for the conversational sales bot (architecture section 8).
-- Apply once with a role that can CREATE tables (the Supabase SQL Editor or a direct
-- postgres connection). The read-only role used by MCP tools cannot run this file.
--
-- RLS is enabled on every table with no policies: the publishable/anon key cannot read
-- or write them. The backend connects with its own DATABASE_URL, so it is not affected.

create extension if not exists pgcrypto;

create table if not exists public.operators (
    id uuid primary key default gen_random_uuid(),
    display_name text not null,
    role text not null check (role in ('admin', 'operator')),
    created_at timestamptz not null default now()
);

create table if not exists public.conversations (
    id uuid primary key default gen_random_uuid(),
    channel text not null,
    external_chat_id text not null,
    status text not null default 'AI_ACTIVE'
        check (status in ('AI_ACTIVE', 'HUMAN_ACTIVE')),
    owner_id uuid references public.operators(id),
    version integer not null default 1 check (version >= 1),
    created_at timestamptz not null default now(),
    unique (channel, external_chat_id)
);

create table if not exists public.messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references public.conversations(id) on delete cascade,
    external_message_id text not null,
    sender_type text not null check (sender_type in ('user', 'ai', 'operator')),
    content text not null,
    created_at timestamptz not null default now(),
    unique (conversation_id, external_message_id)
);
create index if not exists messages_conversation_created_idx
    on public.messages (conversation_id, created_at);

create table if not exists public.leads (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references public.conversations(id) on delete cascade,
    name text,
    interested_course text,
    stage text not null default 'INTERESADO'
        check (stage in ('INTERESADO', 'DUDOSO', 'FRUSTRADO', 'LEAD_CALIENTE')),
    created_at timestamptz not null default now()
);

create table if not exists public.conversation_analysis (
    id uuid primary key default gen_random_uuid(),
    message_id uuid not null references public.messages(id) on delete cascade,
    intent text,
    lead_status text
        check (lead_status is null or lead_status in ('INTERESADO', 'DUDOSO', 'FRUSTRADO', 'LEAD_CALIENTE')),
    latency_ms integer check (latency_ms is null or latency_ms >= 0),
    token_usage integer check (token_usage is null or token_usage >= 0),
    created_at timestamptz not null default now()
);

create table if not exists public.conversation_events (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references public.conversations(id) on delete cascade,
    type text not null,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
create index if not exists conversation_events_conversation_created_idx
    on public.conversation_events (conversation_id, created_at);

create table if not exists public.jobs (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references public.conversations(id) on delete cascade,
    status text not null default 'PENDING'
        check (status in ('PENDING', 'RUNNING', 'DONE', 'FAILED')),
    attempt_count integer not null default 0 check (attempt_count >= 0),
    available_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);
create index if not exists jobs_status_available_idx
    on public.jobs (status, available_at);

alter table public.operators enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.leads enable row level security;
alter table public.conversation_analysis enable row level security;
alter table public.conversation_events enable row level security;
alter table public.jobs enable row level security;
