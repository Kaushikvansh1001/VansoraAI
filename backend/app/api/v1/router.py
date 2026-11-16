from fastapi import APIRouter

from app.api.v1.routes import ai, analyst, auth, dashboard, health, knowledge, organizations, support, workflows

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(dashboard.router)
api_router.include_router(ai.router)
api_router.include_router(knowledge.router)
api_router.include_router(analyst.router)
api_router.include_router(workflows.router)
api_router.include_router(support.router)
