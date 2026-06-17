"""
Server-authoritative nutrition math. The Flutter app has a client-side
mirror of these formulas for instant UI feedback during onboarding, but
the backend is the source of truth whenever targets are persisted.
"""

ACTIVITY_MULTIPLIERS = {
    "Sedentary": 1.2,
    "Lightly Active": 1.375,
    "Moderately Active": 1.55,
    "Very Active": 1.725,
    "Extremely Active": 1.9,
}

GOAL_CALORIE_ADJUSTMENT = {
    "Lose Weight": -500,
    "Maintain Weight": 0,
    "Gain Weight": 500,
    "Build Muscle": 300,
    "Improve Health": 0,
    "Eat Healthier": 0,
}

GOAL_PROTEIN_G_PER_KG = {
    "Build Muscle": 2.0,
    "Lose Weight": 1.6,
    "Gain Weight": 1.8,
}
DEFAULT_PROTEIN_G_PER_KG = 1.2


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    height_m = height_cm / 100
    return weight_kg / (height_m * height_m)


def bmi_category(bmi: float) -> str:
    if bmi < 18.5:
        return "Underweight"
    if bmi < 25.0:
        return "Normal"
    if bmi < 30.0:
        return "Overweight"
    return "Obese"


def calculate_bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> float:
    """Mifflin-St Jeor Equation."""
    base = (10 * weight_kg) + (6.25 * height_cm) - (5 * age)
    return base + 5 if gender.lower() == "male" else base - 161


def calculate_tdee(bmr: float, activity_level: str) -> float:
    multiplier = ACTIVITY_MULTIPLIERS.get(activity_level, 1.2)
    return bmr * multiplier


def calculate_daily_calories(tdee: float, goal: str) -> float:
    adjustment = GOAL_CALORIE_ADJUSTMENT.get(goal, 0)
    return tdee + adjustment


def calculate_protein_target(weight_kg: float, goal: str) -> float:
    g_per_kg = GOAL_PROTEIN_G_PER_KG.get(goal, DEFAULT_PROTEIN_G_PER_KG)
    return weight_kg * g_per_kg


def calculate_macro_targets(total_calories: float, protein_g: float) -> dict:
    """Returns daily protein/carbs/fat targets in grams."""
    protein_cals = protein_g * 4
    remaining = total_calories - protein_cals
    carbs_cals = remaining * 0.55
    fat_cals = remaining * 0.45
    return {
        "protein_g": round(protein_g, 1),
        "carbs_g": round(carbs_cals / 4, 1),
        "fat_g": round(fat_cals / 9, 1),
    }


def calculate_all_targets(
    weight_kg: float, height_cm: float, age: int, gender: str,
    activity_level: str, goal: str,
) -> dict:
    """Convenience wrapper used during onboarding / profile updates."""
    bmr = calculate_bmr(weight_kg, height_cm, age, gender)
    tdee = calculate_tdee(bmr, activity_level)
    daily_calories = calculate_daily_calories(tdee, goal)
    protein_target = calculate_protein_target(weight_kg, goal)
    macros = calculate_macro_targets(daily_calories, protein_target)
    return {
        "bmr": round(bmr, 1),
        "tdee": round(tdee, 1),
        "daily_calorie_target": round(daily_calories, 1),
        "daily_protein_target": macros["protein_g"],
        "daily_carbs_target": macros["carbs_g"],
        "daily_fat_target": macros["fat_g"],
    }


def estimate_weeks_to_goal(current_weight: float, goal_weight: float) -> int:
    diff = abs(current_weight - goal_weight)
    # ~0.5kg/week is the medically recommended safe rate
    return max(0, round(diff / 0.5))


def calculate_health_score(
    protein: float, fiber: float, added_sugar: float, sodium: float,
    saturated_fat: float, additive_count: int, is_ultra_processed: bool,
) -> float:
    """
    Proprietary 0-100 health score.

    Baseline of 50, then:
      + up to 20 pts for protein (20g+ per serving = max)
      + up to 15 pts for fiber (5g+ per serving = max)
      - up to 20 pts for added sugar (25g+ = max penalty)
      - up to 15 pts for sodium (2300mg+ = max penalty, the FDA daily limit)
      - up to 10 pts for saturated fat (20g+ = max penalty)
      - up to 10 pts for additives (2 pts each, capped at 5 additives)
      - 10 pt flat penalty if NOVA-classified ultra-processed
    """
    score = 50.0

    protein_score = min(20.0, (protein / 20.0) * 20)
    score += protein_score

    fiber_score = min(15.0, (fiber / 5.0) * 15)
    score += fiber_score

    sugar_penalty = min(20.0, (added_sugar / 25.0) * 20)
    score -= sugar_penalty

    sodium_penalty = min(15.0, (sodium / 2300.0) * 15)
    score -= sodium_penalty

    sat_fat_penalty = min(10.0, (saturated_fat / 20.0) * 10)
    score -= sat_fat_penalty

    additive_penalty = min(10.0, additive_count * 2.0)
    score -= additive_penalty

    if is_ultra_processed:
        score -= 10

    return max(0.0, min(100.0, round(score, 1)))


def health_score_label(score: float) -> str:
    if score >= 80:
        return "Excellent"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Fair"
    return "Poor"
