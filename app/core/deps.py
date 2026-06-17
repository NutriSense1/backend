from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth as firebase_auth
from app.db.supabase_client import get_supabase

bearer_scheme = HTTPBearer()


class CurrentUser:
    """Lightweight container for the authenticated request context."""

    def __init__(self, firebase_uid: str, email: str, db_user: dict | None):
        self.firebase_uid = firebase_uid
        self.email = email
        self.db_user = db_user  # row from `users` table, or None if not onboarded yet

    @property
    def id(self) -> str | None:
        return self.db_user["id"] if self.db_user else None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    """
    Verifies the Firebase ID token sent in the Authorization header
    (Authorization: Bearer <id_token>) and loads the matching app
    profile from Supabase, if one exists.

    The Flutter app obtains this token via:
        FirebaseAuth.instance.currentUser?.getIdToken()
    """
    token = credentials.credentials
    try:
        decoded = firebase_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        )

    firebase_uid = decoded["uid"]
    email = decoded.get("email", "")

    supabase = get_supabase()
    result = (
        supabase.table("users")
        .select("*")
        .eq("firebase_uid", firebase_uid)
        .limit(1)
        .execute()
    )
    db_user = result.data[0] if result.data else None

    return CurrentUser(firebase_uid=firebase_uid, email=email, db_user=db_user)


async def require_onboarded_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """
    Use this dependency on routes that require a completed profile
    (i.e. the user has finished onboarding). Raises 404 otherwise so
    the client knows to redirect to onboarding.
    """
    if current_user.db_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found. Complete onboarding first.",
        )
    return current_user
