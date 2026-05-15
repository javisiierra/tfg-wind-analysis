from fastapi import APIRouter

from app.api.v1.pipeline import router as pipeline_router
from app.api.v1.dashboard_router import router as dashboard_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(pipeline_router)
api_router.include_router(dashboard_router)