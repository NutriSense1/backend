from datetime import datetime, date
from pydantic import BaseModel, Field, EmailStr


# ─── User / Onboarding ──────────────────────────────────────────────────────

class OnboardingRequest(BaseModel):
    name: str
    age: int = Field(ge=10, le=120)
    gender: str
    height_cm: float = Field(gt=0)
    weight_kg: float = Field(gt=0)
    goal_weight_kg: float = Field(gt=0)
    activity_level: str
    goal: str
    dietary_preferences: list[str] = []
    allergies: list[str] = []
    water_goal_liters: float = 2.5


class UserProfileResponse(BaseModel):
    id: str
    name: str
    email: str
    avatar_url: str | None
    age: int
    gender: str
    height_cm: float
    weight_kg: float
    goal_weight_kg: float
    activity_level: str
    goal: str
    dietary_preferences: list[str]
    allergies: list[str]
    water_goal_liters: float
    daily_calorie_target: float
    daily_protein_target: float
    daily_carbs_target: float
    daily_fat_target: float
    is_premium: bool
    total_scans: int
    xp: int
    level: int
    current_streak: int
    created_at: datetime


class UserProfileUpdate(BaseModel):
    name: str | None = None
    weight_kg: float | None = None
    goal_weight_kg: float | None = None
    activity_level: str | None = None
    goal: str | None = None
    dietary_preferences: list[str] | None = None
    allergies: list[str] | None = None
    water_goal_liters: float | None = None


# ─── Scan ───────────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    image_base64: str
    meal_type: str | None = None


class NutritionInfo(BaseModel):
    calories: float = 0
    protein: float = 0
    carbs: float = 0
    fat: float = 0
    fiber: float = 0
    sugar: float = 0
    added_sugar: float = 0
    sodium: float = 0
    saturated_fat: float = 0
    trans_fat: float = 0
    cholesterol: float = 0
    potassium: float = 0


class ScanResultResponse(BaseModel):
    id: str
    image_url: str | None = None
    product_name: str
    brand: str | None = None
    food_type: str
    ingredients: list[str] = []
    detected_additives: list[str] = []
    detected_allergens: list[str] = []
    user_allergy_warning: list[str] = []
    nutrition_info: NutritionInfo
    serving_size: float
    serving_unit: str
    health_score: float
    health_score_label: str
    ai_verdict: str
    positives: list[str] = []
    negatives: list[str] = []
    recommendations: list[str] = []
    is_ultra_processed: bool
    confidence: str
    scanned_at: datetime


# ─── Food Logs ──────────────────────────────────────────────────────────────

class FoodLogCreate(BaseModel):
    scan_id: str | None = None
    product_name: str
    brand: str | None = None
    image_url: str | None = None
    meal_type: str
    serving_size: float = 100
    serving_unit: str = "g"
    servings_consumed: float = 1.0
    nutrition_info: NutritionInfo
    health_score: float


class FoodLogResponse(BaseModel):
    id: str
    product_name: str
    brand: str | None
    image_url: str | None
    meal_type: str
    serving_size: float
    serving_unit: str
    servings_consumed: float
    nutrition_info: NutritionInfo
    health_score: float
    logged_at: datetime


# ─── Weight / Water / Steps ─────────────────────────────────────────────────

class WeightLogCreate(BaseModel):
    weight_kg: float = Field(gt=0)
    note: str | None = None


class WeightLogResponse(BaseModel):
    id: str
    weight_kg: float
    note: str | None
    logged_at: datetime


class WaterLogCreate(BaseModel):
    amount_liters: float


class WaterLogResponse(BaseModel):
    id: str
    amount_liters: float
    logged_at: datetime


class StepSyncRequest(BaseModel):
    steps: int
    distance_km: float
    calories_burned: float
    date: date


# ─── AI Coach ───────────────────────────────────────────────────────────────

class CoachChatRequest(BaseModel):
    message: str


class CoachChatResponse(BaseModel):
    reply: str


class DailyReviewResponse(BaseModel):
    title: str
    content: str
    calories_consumed: float
    calories_target: float
    protein_consumed: float
    protein_target: float
    meals_logged: int


# ─── Analytics ──────────────────────────────────────────────────────────────

class WeeklyReportResponse(BaseModel):
    avg_calories: float
    avg_health_score: float
    consistency_score: float
    goal_adherence_score: float
    daily_calories: list[float]
    daily_health_scores: list[float]
