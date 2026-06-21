from fastapi import APIRouter, Depends, HTTPException
from app.core.deps import require_onboarded_user, CurrentUser
from app.db.supabase_client import get_supabase
from app.schemas.schemas import (
    DeviceTokenCreate, DeviceTokenDelete, NotificationPrefsUpdate,
)
from app.services import push_service

router = APIRouter(prefix="/notifications", tags=["notifications"])

DEFAULT_PREFS = {
    "meal_reminders": True,
    "achievement_alerts": True,
    "coach_tips": True,
    "streak_warnings": True,
}


# ─── Device tokens ────────────────────────────────────────────────────────────

@router.post("/device-token", status_code=201)
async def register_device_token(
    payload: DeviceTokenCreate,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    """
    Called once after sign-in (and again whenever Firebase rotates the
    token via onTokenRefresh). Upserts on `token` rather than
    (user_id, token) — if the same physical device was previously
    registered to a different account (shared device, account switch),
    this correctly reassigns it instead of leaving a stale duplicate
    pointed at the old user.
    """
    supabase = get_supabase()
    supabase.table("device_tokens").upsert({
        "user_id": current_user.id,
        "token": payload.token,
        "platform": payload.platform,
    }, on_conflict="token").execute()
    return {"status": "registered"}


@router.delete("/device-token", status_code=204)
async def remove_device_token(
    payload: DeviceTokenDelete,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    """Call on sign-out so a shared/borrowed device stops receiving this
    user's pushes once they've logged out of it."""
    supabase = get_supabase()
    supabase.table("device_tokens").delete().eq("token", payload.token).eq(
        "user_id", current_user.id
    ).execute()


# ─── Preferences ────────────────────────────────────────────────────────────

@router.get("/preferences")
async def get_preferences(current_user: CurrentUser = Depends(require_onboarded_user)):
    return {**DEFAULT_PREFS, **(current_user.db_user.get("notification_prefs") or {})}


@router.patch("/preferences")
async def update_preferences(
    payload: NotificationPrefsUpdate,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    current = {**DEFAULT_PREFS, **(current_user.db_user.get("notification_prefs") or {})}
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    merged = {**current, **updates}
    supabase.table("users").update({"notification_prefs": merged}).eq(
        "id", current_user.id
    ).execute()
    return merged


# ─── In-app feed ────────────────────────────────────────────────────────────

@router.get("")
async def list_notifications(
    limit: int = 50,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    result = (
        supabase.table("notifications")
        .select("*")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


@router.post("/read-all")
async def mark_all_read(current_user: CurrentUser = Depends(require_onboarded_user)):
    supabase = get_supabase()
    supabase.table("notifications").update({"is_read": True}).eq(
        "user_id", current_user.id
    ).eq("is_read", False).execute()
    return {"status": "ok"}


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    result = (
        supabase.table("notifications")
        .update({"is_read": True})
        .eq("id", notification_id)
        .eq("user_id", current_user.id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Notification not found")
    return result.data[0]


# ─── Test push ──────────────────────────────────────────────────────────────

@router.post("/test-push")
async def send_test_push(current_user: CurrentUser = Depends(require_onboarded_user)):
    """Lets the Notifications settings screen offer a 'Send test notification'
    button so users (and you, while QA-ing this) can confirm push actually
    reaches the device — bypasses the category preference check since it's
    an explicit user action, not an automated category."""
    supabase = get_supabase()
    push_service.notify(
        user_id=current_user.id,
        title="🔔 Test notification",
        body="If you can see this, push notifications are working.",
        category=None,
        data={"type": "test"},
        supabase=supabase,
    )
    has_token = (
        supabase.table("device_tokens")
        .select("id", count="exact")
        .eq("user_id", current_user.id)
        .execute()
    )
    if not (has_token.count or 0):
        return {
            "status": "no_device_registered",
            "message": "No device token is registered for this account yet — "
                       "open the app on your phone first so it can register one.",
        }
    return {"status": "sent"}
