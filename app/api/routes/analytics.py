from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends
from app.core.deps import require_onboarded_user, CurrentUser
from app.db.supabase_client import get_supabase
from app.schemas.schemas import WeeklyReportResponse

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/weekly", response_model=WeeklyReportResponse)
async def get_weekly_report(current_user: CurrentUser = Depends(require_onboarded_user)):
    supabase = get_supabase()
    user = current_user.db_user
    cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()

    logs = (
        supabase.table("food_logs")
        .select("logged_at, nutrition_info, servings_consumed, health_score")
        .eq("user_id", current_user.id)
        .gte("logged_at", cutoff)
        .execute()
    ).data

    by_day: dict[str, list] = defaultdict(list)
    for log in logs:
        day = log["logged_at"][:10]
        by_day[day].append(log)

    days_sorted = sorted(by_day.keys())
    daily_calories = []
    daily_scores = []
    for day in days_sorted:
        day_logs = by_day[day]
        cals = sum(l["nutrition_info"]["calories"] * l["servings_consumed"] for l in day_logs)
        scores = [l["health_score"] for l in day_logs]
        daily_calories.append(round(cals, 1))
        daily_scores.append(round(sum(scores) / len(scores), 1) if scores else 0)

    avg_calories = round(sum(daily_calories) / len(daily_calories), 1) if daily_calories else 0
    avg_score = round(sum(daily_scores) / len(daily_scores), 1) if daily_scores else 0

    # Consistency: how many of the last 7 days had at least one log
    days_with_logs = len(by_day)
    consistency_score = round((days_with_logs / 7) * 100, 1)

    # Goal adherence: how close avg calories tracked to target
    target = user["daily_calorie_target"]
    if avg_calories and target:
        adherence = max(0, 100 - (abs(avg_calories - target) / target * 100))
    else:
        adherence = 0
    goal_adherence_score = round(adherence, 1)

    return {
        "avg_calories": avg_calories,
        "avg_health_score": avg_score,
        "consistency_score": consistency_score,
        "goal_adherence_score": goal_adherence_score,
        "daily_calories": daily_calories,
        "daily_health_scores": daily_scores,
    }
