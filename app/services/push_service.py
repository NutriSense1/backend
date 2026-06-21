"""
Push notification sending.

Two things happen every time `notify()` is called:
  1. A row is always written to the `notifications` table (the in-app
     notification feed / bell icon) — regardless of the user's push
     preference, so nothing is lost if they've muted push for that
     category but still want to see it next time they open the app.
  2. An actual FCM push is sent to the user's registered devices, but
     ONLY if `category` is enabled in their `notification_prefs`
     (or `category` is None, used for things like the "send me a test
     push" button where a category toggle wouldn't make sense).

Invalid/uninstalled-app tokens are pruned from `device_tokens` automatically
when Firebase reports them as unregistered.
"""
import logging
from firebase_admin import messaging
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE_BY_CATEGORY = {
    "meal_reminders": "reminder",
    "achievement_alerts": "achievement",
    "coach_tips": "ai_insight",
    "streak_warnings": "streak_warning",
}


def notify(
    user_id: str,
    title: str,
    body: str,
    category: str | None = None,
    data: dict | None = None,
    supabase=None,
) -> None:
    supabase = supabase or get_supabase()

    # 1. Always log to the in-app feed.
    supabase.table("notifications").insert({
        "user_id": user_id,
        "type": NOTIFICATION_TYPE_BY_CATEGORY.get(category, "system"),
        "title": title,
        "body": body,
    }).execute()

    # 2. Check opt-in before sending an actual push.
    if category is not None:
        user = (
            supabase.table("users")
            .select("notification_prefs")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        prefs = (user.data[0]["notification_prefs"] if user.data else {}) or {}
        if prefs.get(category) is False:
            return

    tokens_result = (
        supabase.table("device_tokens")
        .select("token")
        .eq("user_id", user_id)
        .execute()
    )
    tokens = [r["token"] for r in tokens_result.data]
    if not tokens:
        return

    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
        tokens=tokens,
    )

    try:
        response = messaging.send_each_for_multicast(message)
    except Exception:
        logger.exception(f"Push send failed for user {user_id}")
        return

    # Prune tokens Firebase says are no longer valid (app uninstalled,
    # token rotated, etc.) so future sends don't keep retrying them.
    dead_tokens = []
    for token, result in zip(tokens, response.responses):
        if not result.success:
            code = getattr(result.exception, "code", "")
            if code in ("UNREGISTERED", "INVALID_ARGUMENT"):
                dead_tokens.append(token)
    if dead_tokens:
        supabase.table("device_tokens").delete().in_("token", dead_tokens).execute()
