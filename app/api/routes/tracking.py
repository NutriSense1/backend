from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from app.core.deps import require_onboarded_user, CurrentUser
from app.db.supabase_client import get_supabase
from app.schemas.schemas import (
    WeightLogCreate, WeightLogResponse,
    WaterLogCreate, WaterLogResponse,
    StepSyncRequest,
)

router = APIRouter(tags=["tracking"])


# ─── Weight ─────────────────────────────────────────────────────────────────

@router.post("/weight-logs", response_model=WeightLogResponse, status_code=201)
async def log_weight(
    payload: WeightLogCreate,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    result = supabase.table("weight_logs").insert({
        "user_id": current_user.id,
        "weight_kg": payload.weight_kg,
        "note": payload.note,
    }).execute()

    # Keep the user's current weight in sync
    supabase.table("users").update({
        "weight_kg": payload.weight_kg,
        "xp": current_user.db_user["xp"] + 8,
    }).eq("id", current_user.id).execute()

    # Achievement progress: weight_log_10
    count = (
        supabase.table("weight_logs")
        .select("id", count="exact")
        .eq("user_id", current_user.id)
        .execute()
    )
    total_logs = count.count or 0
    if total_logs >= 10:
        supabase.table("user_achievements").upsert({
            "user_id": current_user.id,
            "achievement_id": "weight_log_10",
            "is_unlocked": True,
            "progress": 1.0,
            "unlocked_at": datetime.utcnow().isoformat(),
        }, on_conflict="user_id,achievement_id").execute()
    else:
        supabase.table("user_achievements").upsert({
            "user_id": current_user.id,
            "achievement_id": "weight_log_10",
            "progress": round(total_logs / 10, 2),
        }, on_conflict="user_id,achievement_id").execute()

    return result.data[0]


@router.get("/weight-logs", response_model=list[WeightLogResponse])
async def get_weight_logs(
    days: int = 30,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    result = (
        supabase.table("weight_logs")
        .select("*")
        .eq("user_id", current_user.id)
        .gte("logged_at", cutoff)
        .order("logged_at")
        .execute()
    )
    return result.data


# ─── Water ──────────────────────────────────────────────────────────────────

@router.post("/water-logs", response_model=WaterLogResponse, status_code=201)
async def log_water(
    payload: WaterLogCreate,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    result = supabase.table("water_logs").insert({
        "user_id": current_user.id,
        "amount_liters": payload.amount_liters,
    }).execute()

    supabase.table("users").update({
        "xp": current_user.db_user["xp"] + 3,
    }).eq("id", current_user.id).execute()

    return result.data[0]


@router.get("/water-logs/today")
async def get_today_water(current_user: CurrentUser = Depends(require_onboarded_user)):
    supabase = get_supabase()
    today_start = datetime.utcnow().strftime("%Y-%m-%dT00:00:00")
    result = (
        supabase.table("water_logs")
        .select("amount_liters")
        .eq("user_id", current_user.id)
        .gte("logged_at", today_start)
        .execute()
    )
    total = sum(r["amount_liters"] for r in result.data)
    return {"total_liters": total, "goal_liters": current_user.db_user["water_goal_liters"]}


# ─── Steps ──────────────────────────────────────────────────────────────────

@router.post("/step-logs/sync", status_code=201)
async def sync_steps(
    payload: StepSyncRequest,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    """
    Upserts the day's step count, called whenever the Flutter app syncs
    from Health Connect (Android) or HealthKit (iOS).
    """
    supabase = get_supabase()
    result = supabase.table("step_logs").upsert({
        "user_id": current_user.id,
        "steps": payload.steps,
        "distance_km": payload.distance_km,
        "calories_burned": payload.calories_burned,
        "date": payload.date.isoformat(),
    }, on_conflict="user_id,date").execute()

    if payload.steps >= 10000:
        supabase.table("user_achievements").upsert({
            "user_id": current_user.id,
            "achievement_id": "steps_10k",
            "is_unlocked": True,
            "progress": 1.0,
            "unlocked_at": datetime.utcnow().isoformat(),
        }, on_conflict="user_id,achievement_id").execute()

    return result.data[0]
