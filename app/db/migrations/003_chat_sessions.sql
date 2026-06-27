-- ============================================================================
-- NutriSense — Migration 003: Agentic Chat Sessions
-- Run in Supabase SQL Editor
-- ============================================================================

-- Chat sessions (like Claude/ChatGPT conversation threads)
create table if not exists chat_sessions (
    id          uuid        primary key default uuid_generate_v4(),
    user_id     uuid        not null references users(id) on delete cascade,
    title       text        not null default 'New Chat',
    preview     text        not null default '',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index idx_chat_sessions_user
    on chat_sessions(user_id, updated_at desc);

-- Add session_id + actions columns to existing messages table
alter table ai_coach_messages
    add column if not exists session_id uuid references chat_sessions(id) on delete cascade,
    add column if not exists actions    jsonb not null default '[]'::jsonb;

create index if not exists idx_ai_coach_messages_session
    on ai_coach_messages(session_id, created_at);

-- RLS
alter table chat_sessions enable row level security;

create policy "Users can manage own sessions"
    on chat_sessions for all
    using (user_id = (
        select id from users where firebase_uid = auth.uid()::text
    ));

-- Auto-touch updated_at on sessions
create trigger touch_chat_sessions_updated_at
    before update on chat_sessions
    for each row execute function set_updated_at();
