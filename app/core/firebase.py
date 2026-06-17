import json
import firebase_admin
from firebase_admin import credentials
from app.core.config import get_settings

_initialized = False


def init_firebase() -> None:
    """
    Initializes the Firebase Admin SDK exactly once.
    Call this on app startup (see app/main.py lifespan).

    Supports two ways of providing the service account:
    1. FIREBASE_SERVICE_ACCOUNT_JSON — the full JSON content as a string
       (best for Render, where you paste the JSON directly as an env var).
    2. FIREBASE_SERVICE_ACCOUNT_PATH — a path to a mounted JSON file
       (best for local development).
    """
    global _initialized
    if _initialized:
        return

    settings = get_settings()

    if settings.firebase_service_account_json:
        cred_dict = json.loads(settings.firebase_service_account_json)
        cred = credentials.Certificate(cred_dict)
    elif settings.firebase_service_account_path:
        cred = credentials.Certificate(settings.firebase_service_account_path)
    else:
        raise RuntimeError(
            "No Firebase credentials configured. Set FIREBASE_SERVICE_ACCOUNT_JSON "
            "or FIREBASE_SERVICE_ACCOUNT_PATH."
        )

    firebase_admin.initialize_app(cred)
    _initialized = True
