from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.deps import require_onboarded_user, CurrentUser
from app.db.supabase_client import get_supabase
from app.schemas.schemas import (
    WeightLogCreate, WeightLogResponse,
    WaterLogCreate, WaterLogResponse,
    StepSyncRequest,
)
from app.services import achievements_service

router = APIRouter(tags=["tracking"])


# ─── Weight ──────────────────────────────────────────────────────────────────

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

    supabase.table("users").update({
        "weight_kg": payload.weight_kg,
        "xp": current_user.db_user["xp"] + 8,
    }).eq("id", current_user.id).execute()

    count = (
        supabase.table("weight_logs")
        .select("id", count="exact")
        .eq("user_id", current_user.id)
        .execute()
    )
    total_logs = count.count or 0
    if total_logs >= 10:
        achievements_service.unlock_achievement(supabase, current_user.id, "weight_log_10")
    else:
        achievements_service.update_progress(
            supabase, current_user.id, "weight_log_10", round(total_logs / 10, 2)
        )

    return result.data[0]


@router.get("/weight-logs", response_model=list[WeightLogResponse])
async def get_weight_logs(
    days: int = 90,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    query = (
        supabase.table("weight_logs")
        .select("*")
        .eq("user_id", current_user.id)
        .order("logged_at", desc=True)
    )
    # days=0 means fetch all
    if days > 0:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        query = query.gte("logged_at", cutoff)
    result = query.execute()
    return result.data


@router.delete("/weight-logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_weight_log(
    log_id: str,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    result = (
        supabase.table("weight_logs")
        .delete()
        .eq("id", log_id)
        .eq("user_id", current_user.id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Log not found")


# ─── Water ───────────────────────────────────────────────────────────────────

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
        .select("*")
        .eq("user_id", current_user.id)
        .gte("logged_at", today_start)
        .order("logged_at", desc=True)
        .execute()
    )
    total = sum(r["amount_liters"] for r in result.data)
    return {
        "total_liters": total,
        "goal_liters": current_user.db_user["water_goal_liters"],
        "logs": result.data,
    }


@router.get("/water-logs", response_model=list[WaterLogResponse])
async def get_water_logs(
    date: str | None = None,
    days: int = 7,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    query = (
        supabase.table("water_logs")
        .select("*")
        .eq("user_id", current_user.id)
        .order("logged_at", desc=True)
    )
    if date:
        # Filter to a specific date
        day_start = f"{date}T00:00:00"
        day_end = f"{date}T23:59:59"
        query = query.gte("logged_at", day_start).lte("logged_at", day_end)
    else:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        query = query.gte("logged_at", cutoff)
    result = query.execute()
    return result.data


@router.delete("/water-logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_water_log(
    log_id: str,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    result = (
        supabase.table("water_logs")
        .delete()
        .eq("id", log_id)
        .eq("user_id", current_user.id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Log not found")


# ─── Steps ───────────────────────────────────────────────────────────────────

@router.post("/step-logs/sync", status_code=201)
async def sync_steps(
    payload: StepSyncRequest,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    result = supabase.table("step_logs").upsert({
        "user_id": current_user.id,
        "steps": payload.steps,
        "distance_km": payload.distance_km,
        "calories_burned": payload.calories_burned,
        "date": payload.date.isoformat(),
    }, on_conflict="user_id,date").execute()

    if payload.steps >= 10000:
        achievements_service.unlock_achievement(supabase, current_user.id, "steps_10k")

    return result.data[0]
