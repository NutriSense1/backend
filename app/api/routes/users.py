from fastapi import APIRouter, Depends, HTTPException, status
from app.core.deps import get_current_user, CurrentUser
from app.db.supabase_client import get_supabase
from app.schemas.schemas import OnboardingRequest, UserProfileResponse, UserProfileUpdate
from app.services import nutrition_calculator as calc

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/onboarding", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
async def complete_onboarding(
    payload: OnboardingRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Creates the app profile row after Firebase sign-up. Called once,
    right after the Flutter onboarding flow collects all the answers.
    """
    if current_user.db_user is not None:
        raise HTTPException(status_code=409, detail="User already onboarded")

    targets = calc.calculate_all_targets(
        weight_kg=payload.weight_kg,
        height_cm=payload.height_cm,
        age=payload.age,
        gender=payload.gender,
        activity_level=payload.activity_level,
        goal=payload.goal,
    )

    supabase = get_supabase()
    row = {
        "firebase_uid": current_user.firebase_uid,
        "email": current_user.email,
        "name": payload.name,
        "age": payload.age,
        "gender": payload.gender,
        "height_cm": payload.height_cm,
        "weight_kg": payload.weight_kg,
        "goal_weight_kg": payload.goal_weight_kg,
        "activity_level": payload.activity_level,
        "goal": payload.goal,
        "dietary_preferences": payload.dietary_preferences,
        "allergies": payload.allergies,
        "water_goal_liters": payload.water_goal_liters,
        "daily_calorie_target": targets["daily_calorie_target"],
        "daily_protein_target": targets["daily_protein_target"],
        "daily_carbs_target": targets["daily_carbs_target"],
        "daily_fat_target": targets["daily_fat_target"],
    }
    result = supabase.table("users").insert(row).execute()
    return result.data[0]


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(current_user: CurrentUser = Depends(get_current_user)):
    if current_user.db_user is None:
        raise HTTPException(status_code=404, detail="User profile not found")
    return current_user.db_user


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(
    payload: UserProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    if current_user.db_user is None:
        raise HTTPException(status_code=404, detail="User profile not found")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return current_user.db_user

    # If weight, goal, or activity level changed, recompute targets
    recompute_triggers = {"weight_kg", "goal", "activity_level"}
    if recompute_triggers & updates.keys():
        merged = {**current_user.db_user, **updates}
        targets = calc.calculate_all_targets(
            weight_kg=merged["weight_kg"],
            height_cm=merged["height_cm"],
            age=merged["age"],
            gender=merged["gender"],
            activity_level=merged["activity_level"],
            goal=merged["goal"],
        )
        updates.update({
            "daily_calorie_target": targets["daily_calorie_target"],
            "daily_protein_target": targets["daily_protein_target"],
            "daily_carbs_target": targets["daily_carbs_target"],
            "daily_fat_target": targets["daily_fat_target"],
        })

    supabase = get_supabase()
    result = (
        supabase.table("users")
        .update(updates)
        .eq("id", current_user.id)
        .execute()
    )
    return result.data[0]
