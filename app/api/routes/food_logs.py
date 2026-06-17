from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.deps import require_onboarded_user, CurrentUser
from app.db.supabase_client import get_supabase
from app.schemas.schemas import FoodLogCreate, FoodLogResponse

router = APIRouter(prefix="/food-logs", tags=["food-logs"])


@router.post("", response_model=FoodLogResponse, status_code=201)
async def create_food_log(
    payload: FoodLogCreate,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    row = {
        "user_id": current_user.id,
        "scan_id": payload.scan_id,
        "product_name": payload.product_name,
        "brand": payload.brand,
        "image_url": payload.image_url,
        "meal_type": payload.meal_type,
        "serving_size": payload.serving_size,
        "serving_unit": payload.serving_unit,
        "servings_consumed": payload.servings_consumed,
        "nutrition_info": payload.nutrition_info.model_dump(),
        "health_score": payload.health_score,
    }
    result = supabase.table("food_logs").insert(row).execute()

    # XP for logging
    supabase.table("users").update({
        "xp": current_user.db_user["xp"] + 5,
    }).eq("id", current_user.id).execute()

    # Achievement: clean eater (health score 80+)
    if payload.health_score >= 80:
        supabase.table("user_achievements").upsert({
            "user_id": current_user.id,
            "achievement_id": "health_score_80",
            "is_unlocked": True,
            "progress": 1.0,
            "unlocked_at": datetime.utcnow().isoformat(),
        }, on_conflict="user_id,achievement_id").execute()

    return result.data[0]


@router.get("", response_model=list[FoodLogResponse])
async def get_food_logs(
    log_date: date | None = Query(None, alias="date"),
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    query = supabase.table("food_logs").select("*").eq("user_id", current_user.id)

    if log_date:
        start = datetime.combine(log_date, datetime.min.time())
        end = start + timedelta(days=1)
        query = query.gte("logged_at", start.isoformat()).lt("logged_at", end.isoformat())

    result = query.order("logged_at", desc=True).execute()
    return result.data


@router.delete("/{log_id}", status_code=204)
async def delete_food_log(
    log_id: str,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    existing = (
        supabase.table("food_logs")
        .select("id")
        .eq("id", log_id)
        .eq("user_id", current_user.id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Food log not found")

    supabase.table("food_logs").delete().eq("id", log_id).execute()
