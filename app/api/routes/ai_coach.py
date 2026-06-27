import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from app.core.deps import require_onboarded_user, CurrentUser
from app.db.supabase_client import get_supabase
from app.schemas.schemas import (
    CoachChatRequest, CoachChatResponse, DailyReviewResponse,
    ChatSession, ChatMessageResponse,
)
from app.services.gemini_service import get_gemini_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai-coach"])


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    protein  = sum(l["nutrition_info"]["protein"]  * l["servings_consumed"] for l in logs)

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
        "protein_consumed":  round(protein, 1),
        "water_consumed_liters": round(water_total, 2),
        "meals_logged": len(logs),
    }


def _execute_actions(supabase, user_id: str, user_db: dict, actions: list[dict]) -> None:
    """Execute each agentic action by writing directly to the relevant table."""
    for action in actions:
        atype = action.get("type")
        try:
            if atype == "water":
                liters = float(action.get("amount_liters") or 0)
                if liters > 0:
                    supabase.table("water_logs").insert({
                        "user_id": user_id,
                        "amount_liters": liters,
                    }).execute()
                    logger.info(f"Auto-logged water: {liters}L for {user_id}")

            elif atype == "food":
                calories = float(action.get("calories") or 0)
                if calories > 0:
                    supabase.table("food_logs").insert({
                        "user_id": user_id,
                        "product_name": action.get("name") or "Unknown food",
                        "meal_type":    action.get("meal_type") or "snack",
                        "serving_size":      1,
                        "serving_unit":      "serving",
                        "servings_consumed": 1,
                        "nutrition_info": {
                            "calories":      calories,
                            "protein":       float(action.get("protein") or 0),
                            "carbs":         float(action.get("carbs")   or 0),
                            "fat":           float(action.get("fat")     or 0),
                            "fiber":         0,
                            "sugar":         0,
                            "sodium_mg":     0,
                            "saturated_fat": 0,
                        },
                        "health_score": 50,
                    }).execute()
                    # XP reward for logging
                    supabase.table("users").update({
                        "xp": user_db["xp"] + 5,
                    }).eq("id", user_id).execute()
                    logger.info(f"Auto-logged food: {action.get('name')} for {user_id}")

            elif atype == "weight":
                kg = float(action.get("weight_kg") or 0)
                if kg > 0:
                    supabase.table("weight_logs").insert({
                        "user_id":   user_id,
                        "weight_kg": kg,
                        "note":      "Logged via AI Coach",
                    }).execute()
                    supabase.table("users").update({
                        "weight_kg": kg,
                        "xp": user_db["xp"] + 8,
                    }).eq("id", user_id).execute()
                    logger.info(f"Auto-logged weight: {kg}kg for {user_id}")

        except Exception as exc:
            logger.warning(f"Failed to execute action {atype}: {exc!r}")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/daily-review", response_model=DailyReviewResponse)
async def get_daily_review(current_user: CurrentUser = Depends(require_onboarded_user)):
    supabase = get_supabase()
    user     = current_user.db_user
    summary  = _today_summary(supabase, current_user.id)

    remaining_cals    = user["daily_calorie_target"] - summary["calories_consumed"]
    remaining_protein = user["daily_protein_target"]  - summary["protein_consumed"]

    if summary["meals_logged"] == 0:
        content = "You haven't logged anything yet today. Scan your first meal or tell me what you've eaten!"
        title   = "Let's get started"
    elif remaining_cals < 0:
        content = f"You're {abs(round(remaining_cals))} kcal over your target today. Consider a lighter dinner or a short walk."
        title   = "Slightly over target"
    elif remaining_protein > 30:
        content = f"You have {round(remaining_cals)} kcal and {round(remaining_protein)}g protein remaining. Go for a protein-rich meal next!"
        title   = "Protein gap to close"
    else:
        content = f"You're on track with {round(remaining_cals)} kcal remaining today. Keep it up!"
        title   = "On track"

    return {
        "title":              title,
        "content":            content,
        "calories_consumed":  summary["calories_consumed"],
        "calories_target":    user["daily_calorie_target"],
        "protein_consumed":   summary["protein_consumed"],
        "protein_target":     user["daily_protein_target"],
        "meals_logged":       summary["meals_logged"],
    }


@router.get("/nutrition-tip")
async def get_nutrition_tip(current_user: CurrentUser = Depends(require_onboarded_user)):
    supabase = get_supabase()
    user     = current_user.db_user
    summary  = _today_summary(supabase, current_user.id)

    gemini = get_gemini_service()
    tip = await gemini.generate_nutrition_tip(
        user_goal=user["goal"],
        user_name=user["name"].split()[0],
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


@router.get("/coach/sessions", response_model=list[ChatSession])
async def list_sessions(current_user: CurrentUser = Depends(require_onboarded_user)):
    """List all chat sessions for this user, newest first."""
    supabase = get_supabase()
    rows = (
        supabase.table("chat_sessions")
        .select("*")
        .eq("user_id", current_user.id)
        .order("updated_at", desc=True)
        .limit(50)
        .execute()
    ).data
    return rows


@router.get("/coach/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def get_session_messages(
    session_id: str,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    """Return the full message history for one session."""
    supabase = get_supabase()

    # Verify ownership
    session = (
        supabase.table("chat_sessions")
        .select("id")
        .eq("id", session_id)
        .eq("user_id", current_user.id)
        .execute()
    ).data
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        supabase.table("ai_coach_messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    ).data
    return messages


@router.post("/coach/chat", response_model=CoachChatResponse)
async def coach_chat(
    payload: CoachChatRequest,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    """
    Agentic coach endpoint. 
    - Creates a session if session_id is None.
    - Calls Gemini and gets reply + actions.
    - Executes actions (logs water/food/weight to DB).
    - Stores both messages with actions in the DB.
    """
    supabase = get_supabase()
    user     = current_user.db_user

    # ── Session management ──────────────────────────────────────────────────
    session_id    = payload.session_id
    session_title = "New Chat"

    if session_id:
        # Verify the session belongs to this user
        existing = (
            supabase.table("chat_sessions")
            .select("id, title")
            .eq("id", session_id)
            .eq("user_id", current_user.id)
            .execute()
        ).data
        if not existing:
            raise HTTPException(status_code=404, detail="Session not found")
        session_title = existing[0]["title"]
    else:
        # Create new session — title is first 40 chars of the opening message
        title = payload.message[:40].strip()
        if len(payload.message) > 40:
            title += "…"
        session_title = title
        new_session = supabase.table("chat_sessions").insert({
            "user_id": current_user.id,
            "title":   title,
            "preview": "",
        }).execute()
        session_id = new_session.data[0]["id"]

    # ── Build conversation history for context ──────────────────────────────
    history = (
        supabase.table("ai_coach_messages")
        .select("role, content")
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    ).data
    history.reverse()

    # ── Build user context ──────────────────────────────────────────────────
    context = {
        "user_name":      user["name"].split()[0],
        "goal":           user["goal"],
        "current_streak": user["current_streak"],
        "calorie_target": user["daily_calorie_target"],
        "protein_target": user["daily_protein_target"],
        "water_goal_L":   user["water_goal_liters"],
        **_today_summary(supabase, current_user.id),
    }

    # ── Save user message ───────────────────────────────────────────────────
    supabase.table("ai_coach_messages").insert({
        "user_id":    current_user.id,
        "session_id": session_id,
        "role":       "user",
        "content":    payload.message,
        "actions":    [],
    }).execute()

    # ── Call Gemini ─────────────────────────────────────────────────────────
    gemini = get_gemini_service()
    result = await gemini.coach_chat_reply(
        user_message=payload.message,
        conversation_history=history,
        user_context=context,
        user_name=user["name"].split()[0],
    )
    reply   = result["reply"]
    actions = result["actions"]  # list[dict]

    # ── Execute agentic actions (write to DB) ───────────────────────────────
    if actions:
        _execute_actions(supabase, current_user.id, user, actions)

    # ── Save assistant message with actions ─────────────────────────────────
    supabase.table("ai_coach_messages").insert({
        "user_id":    current_user.id,
        "session_id": session_id,
        "role":       "assistant",
        "content":    reply,
        "actions":    actions,
    }).execute()

    # ── Update session preview + updated_at ────────────────────────────────
    preview = reply[:80]
    supabase.table("chat_sessions").update({
        "preview":    preview,
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", session_id).execute()

    return {
        "reply":         reply,
        "session_id":    session_id,
        "session_title": session_title,
        "actions":       actions,
    }
