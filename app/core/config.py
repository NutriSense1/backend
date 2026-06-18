from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration is read from environment variables.
    Locally, these come from a .env file (see .env.example).
    On Render, these are set in the dashboard under Environment.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── App ──
    environment: str = "development"
    app_name: str = "NutriSense API"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "*"  # comma-separated list in production

    # ── Supabase ──
    supabase_url: str
    supabase_service_role_key: str  # server-side key, full DB access, NEVER ship to client

    # ── Firebase ──
    # Path to the service account JSON, OR the JSON content itself as a string
    # (Render env vars can't hold files well, so we support inline JSON).
    firebase_service_account_json: str | None = None
    firebase_service_account_path: str | None = None

    # ── Gemini ──
    # Primary model is tried first (with retries). If it still fails after
    # gemini_max_retries attempts, we fall back to gemini_fallback_model.
    gemini_api_key: str
    gemini_model: str = "gemini-3.5-flash"
    gemini_fallback_model: str = "gemini-3.1-flash-lite"
    gemini_max_retries: int = 2

    # ── Open Food Facts ──
    off_base_url: str = "https://world.openfoodfacts.org/api/v3"
    off_search_url: str = "https://world.openfoodfacts.org/cgi/search.pl"

    # ── Rate limiting ──
    free_tier_daily_scan_limit: int = 5

    # ── Keep-alive (prevents Render free/idle instances from spinning down) ──
    keep_alive_enabled: bool = True
    keep_alive_interval_seconds: int = 720  # 12 minutes

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
