from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as api_router

from .config import get_settings

app = FastAPI(title="HomeMatch prototype")

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


app.include_router(router)
app.include_router(api_router)
