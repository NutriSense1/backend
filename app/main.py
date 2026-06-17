import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.firebase import init_firebase
from app.api.routes import users, scan, food_logs, tracking, ai_coach, analytics, achievements

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Firebase Admin SDK...")
    init_firebase()
    logger.info("Startup complete.")
    yield
    logger.info("Shutting down.")


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "ok", "service": settings.app_name}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception(f"Unhandled exception on {request.url}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ── Routers ──
prefix = settings.api_v1_prefix
app.include_router(users.router, prefix=prefix)
app.include_router(scan.router, prefix=prefix)
app.include_router(food_logs.router, prefix=prefix)
app.include_router(tracking.router, prefix=prefix)
app.include_router(ai_coach.router, prefix=prefix)
app.include_router(analytics.router, prefix=prefix)
app.include_router(achievements.router, prefix=prefix)
