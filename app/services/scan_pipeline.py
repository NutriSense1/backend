"""
Orchestrates the full scan pipeline:
  1. Gemini identifies the food from the photo
  2. If it looks like a packaged product, try Open Food Facts for ground-truth nutrition
  3. Fall back to Gemini's visual estimate if no OFF match
  4. Compute the proprietary health score from real numbers
  5. Ask Gemini for the human-readable verdict, grounded in those numbers
  6. Cross-check user's allergy list against detected allergens
"""
import logging
from app.services.gemini_service import get_gemini_service
from app.services.open_food_facts_service import get_off_service
from app.services import nutrition_calculator as calc

logger = logging.getLogger(__name__)


async def run_scan_pipeline(
    image_bytes: bytes,
    mime_type: str,
    user_goal: str,
    user_dietary_preferences: list[str],
    user_allergies: list[str],
) -> dict:
    gemini = get_gemini_service()
    off = get_off_service()

    # ── Step 1: Identify food from image ──
    identification = await gemini.identify_food(image_bytes, mime_type)

    product_name = identification.get("product_name", "Unknown Food")
    brand = identification.get("brand")
    food_type = identification.get("food_type", "Food")
    ingredients = identification.get("ingredients", [])
    is_packaged = identification.get("is_packaged", False)
    barcode = identification.get("barcode_visible")
    confidence = identification.get("confidence", "medium")
    serving_size = identification.get("estimated_serving_size_g", 100)
    fallback_nutrition = identification.get("estimated_nutrition_per_serving", {})

    # ── Step 2: Try Open Food Facts if this looks like a packaged product ──
    off_nutrition = None
    off_product_code = None
    detected_additives: list[str] = []
    detected_allergens: list[str] = []
    is_ultra_processed = False

    if is_packaged:
        product = None
        if barcode:
            product = await off.lookup_by_barcode(barcode)
        if not product:
            candidates = await off.search_by_name(product_name, brand)
            product = candidates[0] if candidates else None

        if product:
            extracted = off.extract_nutrition(product)
            off_nutrition = extracted
            off_product_code = product.get("code")
            detected_additives = extracted["additives"]
            detected_allergens = extracted["allergens"]
            is_ultra_processed = extracted["is_ultra_processed"]
            # Prefer OFF's product name/brand if available (more precise than Gemini's guess)
            product_name = extracted.get("product_name") or product_name
            brand = extracted.get("brand") or brand

    # ── Step 3: Resolve final nutrition (OFF ground truth > Gemini estimate) ──
    nutrition = off_nutrition if off_nutrition else {
        "calories": fallback_nutrition.get("calories", 0),
        "protein": fallback_nutrition.get("protein", 0),
        "carbs": fallback_nutrition.get("carbs", 0),
        "fat": fallback_nutrition.get("fat", 0),
        "fiber": fallback_nutrition.get("fiber", 0),
        "sugar": fallback_nutrition.get("sugar", 0),
        "added_sugar": fallback_nutrition.get("sugar", 0),
        "sodium": fallback_nutrition.get("sodium_mg", 0),
        "saturated_fat": fallback_nutrition.get("saturated_fat", 0),
        "trans_fat": 0,
        "cholesterol": 0,
        "potassium": 0,
    }
    if not off_nutrition:
        # No OFF match means lower confidence regardless of what Gemini reported
        confidence = "low" if confidence == "high" else confidence

    # ── Step 4: Health score ──
    health_score = calc.calculate_health_score(
        protein=nutrition["protein"],
        fiber=nutrition["fiber"],
        added_sugar=nutrition["added_sugar"],
        sodium=nutrition["sodium"],
        saturated_fat=nutrition["saturated_fat"],
        additive_count=len(detected_additives),
        is_ultra_processed=is_ultra_processed,
    )
    score_label = calc.health_score_label(health_score)

    # ── Step 5: AI verdict, grounded in real numbers ──
    verdict_data = await gemini.generate_verdict(
        product_name=product_name,
        nutrition=nutrition,
        health_score=health_score,
        detected_allergens=detected_allergens,
        detected_additives=detected_additives,
        user_goal=user_goal,
        user_dietary_preferences=user_dietary_preferences,
    )

    # ── Step 6: Cross-check against the user's known allergies ──
    user_allergy_matches = [
        a for a in user_allergies
        if any(a.lower() in d.lower() or d.lower() in a.lower() for d in detected_allergens)
    ]

    return {
        "product_name": product_name,
        "brand": brand,
        "food_type": food_type,
        "ingredients": ingredients,
        "detected_additives": detected_additives,
        "detected_allergens": detected_allergens,
        "user_allergy_warning": user_allergy_matches,  # subset relevant to THIS user
        "nutrition_info": nutrition,
        "serving_size": serving_size,
        "serving_unit": "g",
        "health_score": health_score,
        "health_score_label": score_label,
        "ai_verdict": verdict_data.get("ai_verdict", ""),
        "positives": verdict_data.get("positives", []),
        "negatives": verdict_data.get("negatives", []),
        "recommendations": verdict_data.get("recommendations", []),
        "is_ultra_processed": is_ultra_processed,
        "confidence": confidence,
        "barcode": barcode,
        "off_product_code": off_product_code,
    }
