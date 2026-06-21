import base64
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.deps import require_onboarded_user, CurrentUser
from app.db.supabase_client import get_supabase
from app.schemas.schemas import ScanRequest, ScanResultResponse
from app.services.scan_pipeline import run_scan_pipeline
from app.services import achievements_service
from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("", response_model=ScanResultResponse)
async def scan_food(
    payload: ScanRequest,
    current_user: CurrentUser = Depends(require_onboarded_user),
):
    """
    The flagship endpoint. Accepts a base64-encoded photo, runs it through
    the Gemini + Open Food Facts pipeline, persists the result, and
    returns the full breakdown.
    """
    user = current_user.db_user
    settings = get_settings()

    # ── Free tier scan limit ──
    if not user["is_premium"]:
        supabase = get_supabase()
        today_start = datetime.utcnow().strftime("%Y-%m-%dT00:00:00")
        today_scans = (
            supabase.table("scan_history")
            .select("id", count="exact")
            .eq("user_id", user["id"])
            .gte("scanned_at", today_start)
            .execute()
        )
        if (today_scans.count or 0) >= settings.free_tier_daily_scan_limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Free tier limit of {settings.free_tier_daily_scan_limit} scans/day reached. Upgrade to Premium for unlimited scans.",
            )

    # ── Decode image ──
    try:
        image_bytes = base64.b64decode(payload.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    if len(image_bytes) > 10 * 1024 * 1024:  # 10MB cap
        raise HTTPException(status_code=413, detail="Image too large (max 10MB)")

    # ── Run the pipeline ──
    try:
        result = await run_scan_pipeline(
            image_bytes=image_bytes,
            mime_type="image/jpeg",
            user_goal=user["goal"],
            user_dietary_preferences=user["dietary_preferences"] or [],
            user_allergies=user["allergies"] or [],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Scan pipeline failed")
        raise HTTPException(status_code=502, detail="AI scan failed, please try again")

    # ── Persist to scan_history ──
    supabase = get_supabase()
    row = {
        "user_id": user["id"],
        "product_name": result["product_name"],
        "brand": result["brand"],
        "food_type": result["food_type"],
        "ingredients": result["ingredients"],
        "detected_additives": result["detected_additives"],
        "detected_allergens": result["detected_allergens"],
        "nutrition_info": result["nutrition_info"],
        "serving_size": result["serving_size"],
        "serving_unit": result["serving_unit"],
        "health_score": result["health_score"],
        "health_score_label": result["health_score_label"],
        "ai_verdict": result["ai_verdict"],
        "positives": result["positives"],
        "negatives": result["negatives"],
        "recommendations": result["recommendations"],
        "is_ultra_processed": result["is_ultra_processed"],
        "confidence": result["confidence"],
        "barcode": result["barcode"],
        "off_product_code": result["off_product_code"],
    }
    inserted = supabase.table("scan_history").insert(row).execute()
    scan_row = inserted.data[0]

    # ── Bump scan count + XP, check achievements ──
    new_total_scans = user["total_scans"] + 1
    supabase.table("users").update({
        "total_scans": new_total_scans,
        "xp": user["xp"] + 10,
    }).eq("id", user["id"]).execute()

    _maybe_unlock_scan_achievements(supabase, user["id"], new_total_scans)

    return {
        **scan_row,
        "user_allergy_warning": result["user_allergy_warning"],
    }


def _maybe_unlock_scan_achievements(supabase, user_id: str, total_scans: int) -> None:
    milestones = {1: "first_scan", 10: "scan_10", 50: "scan_50"}
    achievement_id = milestones.get(total_scans)
    if not achievement_id:
        return
    achievements_service.unlock_achievement(supabase, user_id, achievement_id)
