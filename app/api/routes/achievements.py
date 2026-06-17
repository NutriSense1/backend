from fastapi import APIRouter, Depends
from app.core.deps import require_onboarded_user, CurrentUser
from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("")
async def get_achievements(current_user: CurrentUser = Depends(require_onboarded_user)):
    """
    Returns the full achievement catalog merged with this user's
    unlock state and progress.
    """
    supabase = get_supabase()

    catalog = supabase.table("achievements").select("*").execute().data
    user_progress = (
        supabase.table("user_achievements")
        .select("*")
        .eq("user_id", current_user.id)
        .execute()
    ).data
    progress_by_id = {p["achievement_id"]: p for p in user_progress}

    merged = []
    for a in catalog:
        p = progress_by_id.get(a["id"], {})
        merged.append({
            **a,
            "is_unlocked": p.get("is_unlocked", False),
            "progress": p.get("progress", 0),
            "unlocked_at": p.get("unlocked_at"),
        })
    return merged
