-- ============================================================================
-- NutriSense — Complete Database Schema
-- Run this in Supabase SQL Editor (Project > SQL Editor > New Query)
-- ============================================================================

-- Enable UUID generation
create extension if not exists "uuid-ossp";

-- ============================================================================
-- USERS
-- Note: Firebase handles auth identity. This table stores the app profile,
-- keyed by firebase_uid (the `uid` from the decoded Firebase ID token).
-- ============================================================================
create table users (
    id uuid primary key default uuid_generate_v4(),
    firebase_uid text unique not null,
    email text unique not null,
    name text not null,
    avatar_url text,
    age integer not null check (age between 10 and 120),
    gender text not null check (gender in ('Male', 'Female')),
    height_cm numeric(5,2) not null check (height_cm > 0),
    weight_kg numeric(5,2) not null check (weight_kg > 0),
    goal_weight_kg numeric(5,2) not null check (goal_weight_kg > 0),
    activity_level text not null check (activity_level in
        ('Sedentary', 'Lightly Active', 'Moderately Active', 'Very Active', 'Extremely Active')),
    goal text not null check (goal in
        ('Lose Weight', 'Maintain Weight', 'Gain Weight', 'Build Muscle', 'Improve Health', 'Eat Healthier')),
    dietary_preferences text[] default '{}',
    allergies text[] default '{}',
    water_goal_liters numeric(4,2) not null default 2.5,
    daily_calorie_target numeric(6,2) not null,
    daily_protein_target numeric(5,2) not null,
    daily_carbs_target numeric(5,2) not null,
    daily_fat_target numeric(5,2) not null,
    is_premium boolean not null default false,
    premium_expires_at timestamptz,
    total_scans integer not null default 0,
    xp integer not null default 0,
    level integer not null default 1,
    current_streak integer not null default 0,
    longest_streak integer not null default 0,
    last_active_date date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index idx_users_firebase_uid on users(firebase_uid);
create index idx_users_email on users(email);

-- ============================================================================
-- SCAN_HISTORY
-- Every AI food scan result, independent of whether it was logged to a meal.
-- ============================================================================
create table scan_history (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references users(id) on delete cascade,
    image_url text,
    product_name text not null,
    brand text,
    food_type text not null,
    ingredients text[] default '{}',
    detected_additives text[] default '{}',
    detected_allergens text[] default '{}',
    nutrition_info jsonb not null,           -- {calories, protein, carbs, fat, fiber, sugar, ...}
    serving_size numeric(7,2) not null default 100,
    serving_unit text not null default 'g',
    health_score numeric(5,2) not null check (health_score between 0 and 100),
    health_score_label text not null,
    ai_verdict text not null,
    positives text[] default '{}',
    negatives text[] default '{}',
    recommendations text[] default '{}',
    is_ultra_processed boolean not null default false,
    confidence text not null check (confidence in ('high', 'medium', 'low')),
    barcode text,
    off_product_code text,                    -- Open Food Facts product code, if matched
    scanned_at timestamptz not null default now()
);

create index idx_scan_history_user_id on scan_history(user_id);
create index idx_scan_history_scanned_at on scan_history(scanned_at desc);

-- ============================================================================
-- FOOD_LOGS
-- Food items logged against a specific meal/day. May reference a scan.
-- ============================================================================
create table food_logs (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references users(id) on delete cascade,
    scan_id uuid references scan_history(id) on delete set null,
    product_name text not null,
    brand text,
    image_url text,
    meal_type text not null check (meal_type in ('Breakfast', 'Lunch', 'Dinner', 'Snack')),
    serving_size numeric(7,2) not null default 100,
    serving_unit text not null default 'g',
    servings_consumed numeric(5,2) not null default 1.0,
    nutrition_info jsonb not null,
    health_score numeric(5,2) not null,
    logged_at timestamptz not null default now()
);

create index idx_food_logs_user_id on food_logs(user_id);
create index idx_food_logs_logged_at on food_logs(logged_at desc);
create index idx_food_logs_user_date on food_logs(user_id, logged_at);

-- ============================================================================
-- WATER_LOGS
-- ============================================================================
create table water_logs (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references users(id) on delete cascade,
    amount_liters numeric(4,2) not null check (amount_liters != 0),
    logged_at timestamptz not null default now()
);

create index idx_water_logs_user_id on water_logs(user_id);
create index idx_water_logs_user_date on water_logs(user_id, logged_at);

-- ============================================================================
-- WEIGHT_LOGS
-- ============================================================================
create table weight_logs (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references users(id) on delete cascade,
    weight_kg numeric(5,2) not null check (weight_kg > 0),
    note text,
    logged_at timestamptz not null default now()
);

create index idx_weight_logs_user_id on weight_logs(user_id);
create index idx_weight_logs_user_date on weight_logs(user_id, logged_at desc);

-- ============================================================================
-- STEP_LOGS
-- One row per user per day, synced from Health Connect / Apple Health.
-- ============================================================================
create table step_logs (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references users(id) on delete cascade,
    steps integer not null default 0,
    distance_km numeric(6,2) not null default 0,
    calories_burned numeric(6,2) not null default 0,
    date date not null,
    synced_at timestamptz not null default now(),
    unique(user_id, date)
);

create index idx_step_logs_user_id on step_logs(user_id);

-- ============================================================================
-- GOALS
-- Historical record of goal changes (so targets can shift over time
-- without losing the audit trail used by analytics).
-- ============================================================================
create table goals (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references users(id) on delete cascade,
    goal_type text not null check (goal_type in
        ('Lose Weight', 'Maintain Weight', 'Gain Weight', 'Build Muscle', 'Improve Health', 'Eat Healthier')),
    target_weight_kg numeric(5,2),
    daily_calorie_target numeric(6,2) not null,
    daily_protein_target numeric(5,2) not null,
    daily_carbs_target numeric(5,2) not null,
    daily_fat_target numeric(5,2) not null,
    is_active boolean not null default true,
    started_at timestamptz not null default now(),
    ended_at timestamptz
);

create index idx_goals_user_id on goals(user_id);

-- ============================================================================
-- ACHIEVEMENTS (catalog) + USER_ACHIEVEMENTS (unlock state)
-- ============================================================================
create table achievements (
    id text primary key,                      -- e.g. 'first_scan', 'streak_7'
    title text not null,
    description text not null,
    icon text not null,
    xp_reward integer not null,
    category text not null check (category in ('streak', 'scan', 'nutrition', 'weight', 'water'))
);

create table user_achievements (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references users(id) on delete cascade,
    achievement_id text not null references achievements(id) on delete cascade,
    progress numeric(3,2) not null default 0 check (progress between 0 and 1),
    is_unlocked boolean not null default false,
    unlocked_at timestamptz,
    unique(user_id, achievement_id)
);

create index idx_user_achievements_user_id on user_achievements(user_id);

-- Seed default achievements
insert into achievements (id, title, description, icon, xp_reward, category) values
    ('first_scan', 'First Scan!', 'Scan your first food item', '🔍', 50, 'scan'),
    ('scan_10', 'Food Explorer', 'Scan 10 food items', '🍽️', 100, 'scan'),
    ('scan_50', 'Nutrition Nerd', 'Scan 50 food items', '🧪', 250, 'scan'),
    ('streak_7', 'Week Warrior', '7-day logging streak', '🔥', 200, 'streak'),
    ('streak_30', 'Monthly Master', '30-day logging streak', '🏆', 500, 'streak'),
    ('water_goal', 'Hydration Hero', 'Reach water goal 7 days in a row', '💧', 150, 'water'),
    ('protein_goal', 'Protein Pro', 'Hit protein goal 5 days in a row', '💪', 150, 'nutrition'),
    ('weight_log_10', 'Scale Tracker', 'Log weight 10 times', '⚖️', 100, 'weight'),
    ('health_score_80', 'Clean Eater', 'Log a food with health score 80+', '🥗', 75, 'nutrition'),
    ('steps_10k', '10K Steps', 'Walk 10,000 steps in a day', '👟', 100, 'streak');

-- ============================================================================
-- NOTIFICATIONS
-- ============================================================================
create table notifications (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references users(id) on delete cascade,
    type text not null check (type in
        ('reminder', 'achievement', 'ai_insight', 'streak_warning', 'system')),
    title text not null,
    body text not null,
    is_read boolean not null default false,
    created_at timestamptz not null default now()
);

create index idx_notifications_user_id on notifications(user_id);
create index idx_notifications_user_unread on notifications(user_id, is_read);

-- ============================================================================
-- AI_INSIGHTS
-- Generated daily/weekly reviews and tips from the AI coach pipeline.
-- ============================================================================
create table ai_insights (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references users(id) on delete cascade,
    type text not null check (type in ('daily', 'weekly', 'tip', 'alert')),
    title text not null,
    content text not null,
    action_label text,
    action_route text,
    is_read boolean not null default false,
    created_at timestamptz not null default now()
);

create index idx_ai_insights_user_id on ai_insights(user_id);
create index idx_ai_insights_created_at on ai_insights(created_at desc);

-- ============================================================================
-- AI_COACH_MESSAGES
-- Chat history with the AI coach, for context continuity.
-- ============================================================================
create table ai_coach_messages (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references users(id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    created_at timestamptz not null default now()
);

create index idx_ai_coach_messages_user_id on ai_coach_messages(user_id, created_at);

-- ============================================================================
-- updated_at auto-touch trigger for users table
-- ============================================================================
create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger trg_users_updated_at
before update on users
for each row execute function set_updated_at();

-- ============================================================================
-- Row Level Security
-- The backend uses the Supabase service_role key (bypasses RLS) for all
-- writes, since FastAPI is the trusted intermediary and Firebase handles
-- auth. RLS is enabled here as defense-in-depth in case the anon/public
-- key is ever exposed to a client directly.
-- ============================================================================
alter table users enable row level security;
alter table scan_history enable row level security;
alter table food_logs enable row level security;
alter table water_logs enable row level security;
alter table weight_logs enable row level security;
alter table step_logs enable row level security;
alter table goals enable row level security;
alter table user_achievements enable row level security;
alter table notifications enable row level security;
alter table ai_insights enable row level security;
alter table ai_coach_messages enable row level security;

-- No public policies are defined — only the service_role key (used
-- exclusively by the FastAPI backend) can read/write. This blocks any
-- direct client-to-Supabase access using the anon key.
