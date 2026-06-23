"""
Wraps the Gemini API for two jobs in the scan pipeline:
  1. Identifying food from a photo (product name, brand, type, ingredients)
  2. Generating the human-readable AI verdict + pros/cons/recommendations
     once we already have real nutrition numbers (from Open Food Facts or
     Gemini's own estimate).

Uses the official google-genai SDK.

Model selection: every call goes through `_generate`, which tries the
primary model (settings.gemini_model, "gemini-3.5-flash") first, retrying
up to `gemini_max_retries` times. If the primary model still fails after
all retries, it falls back to settings.gemini_fallback_model
("gemini-3.1-flash-lite") and retries that too before finally giving up.
"""
import asyncio
import json
import logging
from google import genai
from google.genai import types
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class GeminiService:
    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model
        self.fallback_model = settings.gemini_fallback_model
        self.max_retries = max(1, settings.gemini_max_retries)

    async def _generate(self, contents, config) -> "types.GenerateContentResponse":
        """
        Calls generate_content with retry-then-fallback:
          - try self.model up to self.max_retries times
          - if all of those fail, try self.fallback_model up to
            self.max_retries times
          - if everything fails, raise the last error
        """
        last_exc: Exception | None = None
        models_to_try = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models_to_try.append(self.fallback_model)

        for model_name in models_to_try:
            for attempt in range(1, self.max_retries + 1):
                try:
                    return self.client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        f"Gemini call failed (model={model_name}, "
                        f"attempt={attempt}/{self.max_retries}): {exc!r}"
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(min(2 ** attempt, 8))
            logger.error(f"Model '{model_name}' exhausted all retries.")

        assert last_exc is not None
        raise last_exc

    async def identify_food(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
        """
        Sends the photo to Gemini and asks for structured identification.
        Returns a dict matching the IdentifyFoodResult shape, or raises
        ValueError if Gemini can't parse a confident result.
        """
        prompt = """You are a food identification expert for a nutrition app.
Look at this image and identify the food or packaged product shown.

Respond ONLY with valid JSON (no markdown, no commentary) in this exact shape:
{
  "product_name": "string - specific name of the food/product",
  "brand": "string or null - brand name if visible on packaging, else null",
  "food_type": "string - category, e.g. 'Dairy', 'Snack', 'Fruit', 'Beverage'",
  "ingredients": ["string", "..."],
  "is_packaged": true or false,
  "barcode_visible": "string or null - barcode digits if clearly visible, else null",
  "estimated_serving_size_g": number,
  "confidence": "high" or "medium" or "low",
  "estimated_nutrition_per_serving": {
    "calories": number, "protein": number, "carbs": number, "fat": number,
    "fiber": number, "sugar": number, "sodium_mg": number, "saturated_fat": number
  }
}

If the image does not contain food, or is too unclear to identify, set confidence to "low"
and make your best reasonable guess rather than refusing. The estimated_nutrition_per_serving
is a fallback only used if no packaged-product database match is found later, so make it as
accurate as you can from visual cues (portion size, visible ingredients, cooking style)."""

        response = await self._generate(
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        try:
            result = json.loads(response.text)
        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"Gemini returned unparseable response: {response.text!r}")
            raise ValueError("Could not identify food from image") from e

        return result

    async def generate_verdict(
        self,
        product_name: str,
        nutrition: dict,
        health_score: float,
        detected_allergens: list[str],
        detected_additives: list[str],
        user_goal: str,
        user_dietary_preferences: list[str],
    ) -> dict:
        """
        Generates the AI verdict, pros/cons and recommendations given
        REAL nutrition numbers (already resolved via Open Food Facts or
        the Gemini visual estimate). This keeps the verdict grounded in
        accurate data rather than letting the model invent numbers.
        """
        prompt = f"""You are a friendly, knowledgeable nutritionist reviewing a food item
for a user whose goal is "{user_goal}" and dietary preferences are {user_dietary_preferences or "none specified"}.

Food: {product_name}
Nutrition per serving: {json.dumps(nutrition)}
Health Score: {health_score}/100
Detected allergens: {detected_allergens or "none"}
Detected additives: {detected_additives or "none"}

Respond ONLY with valid JSON in this shape:
{{
  "ai_verdict": "string - 2-3 sentences, warm and direct, explaining whether this fits their goal",
  "positives": ["string", "... up to 4 short bullet points"],
  "negatives": ["string", "... up to 3 short bullet points, empty array if none"],
  "recommendations": ["string", "... up to 3 actionable suggestions, e.g. pairing ideas or moderation tips"]
}}

Be honest and specific to the actual numbers given — do not be generically positive about
unhealthy food just to be nice, and do not be alarmist about reasonably healthy food."""

        response = await self._generate(
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.4,
            ),
        )

        try:
            return json.loads(response.text)
        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"Gemini verdict response unparseable: {response.text!r}")
            # Fail soft — return a minimal verdict rather than breaking the whole scan
            return {
                "ai_verdict": f"This item has a health score of {health_score}/100.",
                "positives": [],
                "negatives": [],
                "recommendations": [],
            }

    async def coach_chat_reply(
        self,
        user_message: str,
        conversation_history: list[dict],
        user_context: dict,
    ) -> str:
        """
        Generates a reply for the AI Coach chat screen, grounded in the
        user's actual logged data for the day.
        """
        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Coach'}: {m['content']}"
            for m in conversation_history[-10:]  # last 10 turns for context
        )

        prompt = f"""You are NutriSense's AI nutrition coach — warm, encouraging, and specific.
You have access to the user's real data today:

{json.dumps(user_context, indent=2)}

Recent conversation:
{history_text}

User: {user_message}

Reply directly and conversationally in 2-4 sentences. Reference their actual numbers
when relevant (calories remaining, protein gap, streak, etc). Do not use markdown formatting."""

        response = await self._generate(
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0.6),
        )
        return response.text.strip()


_gemini_service: GeminiService | None = None


def get_gemini_service() -> GeminiService:
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service

    async def generate_nutrition_tip(
        self,
        user_goal: str,
        user_name: str,
        calories_consumed: float,
        calorie_target: float,
        protein_consumed: float,
        protein_target: float,
        water_consumed: float,
        water_target: float,
        meals_logged: int,
        current_streak: int,
        dietary_preferences: list[str],
    ) -> dict:
        """
        Generates a fresh, personalised nutrition tip for the home screen,
        grounded in the user's actual data for today.
        """
        pct_cal = round((calories_consumed / calorie_target * 100) if calorie_target else 0)
        pct_protein = round((protein_consumed / protein_target * 100) if protein_target else 0)

        prompt = f"""You are NutriSense, a friendly AI nutrition coach generating a short home-screen tip.

User: {user_name}
Goal: {user_goal}
Dietary preferences: {dietary_preferences or ["none"]}
Today so far: {calories_consumed:.0f} kcal consumed ({pct_cal}% of {calorie_target:.0f} kcal target), 
  {protein_consumed:.0f}g protein ({pct_protein}% of {protein_target:.0f}g target),
  {water_consumed:.1f}L water ({water_consumed:.1f}/{water_target:.1f}L),
  {meals_logged} meals logged, {current_streak}-day streak.

Generate a short, personalised, actionable nutrition tip for this user RIGHT NOW (not generic advice).
Reference their actual numbers. Be specific, warm, and motivating. 2-3 sentences maximum.

Respond ONLY with valid JSON:
{{"title": "short title (4-6 words)", "tip": "the personalised tip (2-3 sentences)"}}"""

        response = await self._generate(
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7,
            ),
        )
        try:
            result = json.loads(response.text)
            return {
                "title": result.get("title", "Today's Tip"),
                "tip": result.get("tip", "Keep logging your meals to get personalised insights!"),
            }
        except (json.JSONDecodeError, AttributeError):
            return {
                "title": "Stay on Track",
                "tip": "Keep logging your meals to get personalised nutrition insights tailored to your goals.",
            }
