-- ============================================================================
-- NutriSense — Push Notifications
-- Run this in Supabase SQL Editor AFTER 001_initial_schema.sql.
-- ============================================================================

-- ============================================================================
-- DEVICE_TOKENS
-- One row per (device, app install). A user can have several rows (phone +
-- tablet + web). `token` is globally unique — if the same physical device
-- token gets re-registered under a different user (e.g. someone signs out
-- and a different person signs in on the same device), upserting on
-- `token` reassigns it rather than leaving two rows pointing at the same
-- device.
-- ============================================================================
create table device_tokens (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references users(id) on delete cascade,
    token text not null unique,
    platform text not null check (platform in ('android', 'ios', 'web')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index idx_device_tokens_user_id on device_tokens(user_id);

-- ============================================================================
-- USERS.notification_prefs
-- Per-category opt-in/out, checked before sending a push (the in-app
-- `notifications` feed row is still written either way so nothing is lost
-- if someone has push muted but still wants to see it in-app).
-- ============================================================================
alter table users
    add column if not exists notification_prefs jsonb not null default
        '{"meal_reminders": true, "achievement_alerts": true, "coach_tips": true, "streak_warnings": true}'::jsonb;
