"""
Shared achievement-unlock logic.

Several routes (food_logs, scan, tracking) can trigger the same
achievement. Upserting `user_achievements` directly from each call site
worked, but had no way to tell "this is the first time it unlocked" from
"it was already unlocked and we just upserted it again" — which meant a
push notification placed next to that upsert would fire on every single
matching event (e.g. every healthy food log), not just the first.

`unlock_achievement` centralizes that check-then-upsert and returns
whether this call is the one that newly unlocked it, so callers know
whether to notify.
"""
from datetime import datetime
from app.services import push_service


def unlock_achievement(
    supabase,
    user_id: str,
    achievement_id: str,
    progress: float = 1.0,
) -> bool:
    """Marks an achievement unlocked (idempotent) and sends a push the
    first time it transitions to unlocked. Returns True on that first
    transition, False if it was already unlocked."""
    existing = (
        supabase.table("user_achievements")
        .select("is_unlocked")
        .eq("user_id", user_id)
        .eq("achievement_id", achievement_id)
        .limit(1)
        .execute()
    )
    already_unlocked = bool(existing.data and existing.data[0].get("is_unlocked"))

    supabase.table("user_achievements").upsert({
        "user_id": user_id,
        "achievement_id": achievement_id,
        "is_unlocked": True,
        "progress": progress,
        "unlocked_at": datetime.utcnow().isoformat(),
    }, on_conflict="user_id,achievement_id").execute()

    if not already_unlocked:
        catalog = (
            supabase.table("achievements")
            .select("title,description,icon")
            .eq("id", achievement_id)
            .limit(1)
            .execute()
        )
        if catalog.data:
            a = catalog.data[0]
            push_service.notify(
                user_id=user_id,
                title=f"{a['icon']} Achievement unlocked: {a['title']}",
                body=a["description"],
                category="achievement_alerts",
                data={"type": "achievement", "achievement_id": achievement_id},
                supabase=supabase,
            )

    return not already_unlocked


def update_progress(supabase, user_id: str, achievement_id: str, progress: float) -> None:
    """Updates progress toward a not-yet-unlocked achievement (no push)."""
    supabase.table("user_achievements").upsert({
        "user_id": user_id,
        "achievement_id": achievement_id,
        "progress": progress,
    }, on_conflict="user_id,achievement_id").execute()
