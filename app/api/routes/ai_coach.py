from datetime import datetime
from fastapi import APIRouter, Depends
from app.core.deps import require_onboarded_user, CurrentUser
from app.db.supabase_client import get_supabase
from app.schemas.schemas import CoachChatRequest, CoachChatResponse, DailyReviewResponse
from app.services.gemini_service import get_gemini_service

router = APIRouter(prefix="/ai", tags=["ai-coach"])


def _today_summary(supabase, user_id: str) -> dict:
    today_start = datetime.utcnow().strftime("%Y-%m-%dT00:00:00")
    logs = (
        supabase.table("food_logs")
        .select("nutrition_info, servings_consumed")
        .eq("user_id", user_id)
        .gte("logged_at", today_start)
        .execute()
    ).data

    calories = sum(l["nutrition_info"]["calories"] * l["servings_consumed"] for l in logs)
    protein = sum(l["nutrition_info"]["protein"] * l["servings_consumed"] for l in logs)

    water = (
        supabase.table("water_logs")
        .select("amount_liters")
        .eq("user_id", user_id)
        .gte("logged_at", today_start)
        .execute()
    ).data
    water_total = sum(w["amount_liters"] for w in water)

    return {
        "calories_consumed": round(calories, 1),
        "protein_consumed": round(protein, 1),
        "water_consumed_liters": round(water_total, 2),
        "meals_logged": len(logs),
    }


@router.get("/daily-review", response_model=DailyReviewResponse)
async def get_daily_review(current_user: CurrentUser = Depends(require_onboarded_user)):
    supabase = get_supabase()
    user = current_user.db_user
    summary = _today_summary(supabase, current_user.id)

    remaining_cals = user["daily_calorie_target"] - summary["calories_consumed"]
    remaining_protein = user["daily_protein_target"] - summary["protein_consumed"]

    if summary["meals_logged"] == 0:
        content = "You haven't logged anything yet today. Scan your first meal to get personalised insights!"
        title = "Let's get started"
    elif remaining_cals < 0:
        content = f"You're {abs(round(remaining_cals))} kcal over your target today. Consider a lighter dinner or a walk to balance it out."
        title = "Slightly over target"
    elif remaining_protein > 30:
        content = f"You have {round(remaining_cals)} kcal and {round(remaining_protein)}g protein remaining. Prioritise a protein-rich meal next."
        title = "Protein gap to close"
    else:
        content = f"You're on track with {round(remaining_cals)} kcal remaining today. Keep it up!"
        title = "On track"

    return {
        "title": title,
        "content": content,
        "calories_consumed": summary["calories_consumed"],
        "calories_target": user["daily_calorie_target"],
        "protein_consumed": summary["protein_consumed"],
        "protein_target": user["daily_protein_target"],
        "meals_logged": summary["meals_logged"],
    }


@router.get("/nutrition-tip")
async def get_nutrition_tip(current_user: CurrentUser = Depends(require_onboarded_user)):
    """
    Returns a fresh, AI-generated personalised nutrition tip for the home screen,
    grounded in the user's actual intake and goals for today.
    """
    supabase = get_supabase()
    user = current_user.db_user
    summary = _today_summary(supabase, current_user.id)

    gemini = get_gemini_service()
    tip = await gemini.generate_nutrition_tip(
        user_goal=user["goal"],
        user_name=user["name"].split()[0],  # first name only
        calories_consumed=summary["calories_consumed"],
        calorie_target=user["daily_calorie_target"],
        protein_consumed=summary["protein_consumed"],
        protein_target=user["daily_protein_target"],
        water_consumed=summary["water_consumed_liters"],
        water_target=user["water_goal_liters"],
        meals_logged=summary["meals_logged"],
        current_streak=user["current_streak"],
        dietary_preferences=user.get("dietary_preferences") or [],
    )
    return tip


@router.post("/coach/chat", response_model=CoachChatResponse)
async def coach_chat(
    payload: CoachChatRequest,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    supabase = get_supabase()
    user = current_user.db_user

    supabase.table("ai_coach_messages").insert({
        "user_id": current_user.id,
        "role": "user",
        "content": payload.message,
    }).execute()

    history = (
        supabase.table("ai_coach_messages")
        .select("role, content")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    ).data
    history.reverse()

    context = {
        "goal": user["goal"],
        "current_streak": user["current_streak"],
        **_today_summary(supabase, current_user.id),
        "calorie_target": user["daily_calorie_target"],
        "protein_target": user["daily_protein_target"],
    }

    gemini = get_gemini_service()
    reply = await gemini.coach_chat_reply(
        user_message=payload.message,
        conversation_history=history,
        user_context=context,
    )

    supabase.table("ai_coach_messages").insert({
        "user_id": current_user.id,
        "role": "assistant",
        "content": reply,
    }).execute()

    return {"reply": reply}
