from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.init_db import ensure_sqlite_schema_compatibility
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.routers.streams import router as streams_router
from app.routers.users import router as users_router
from app.routers.webhook import router as webhook_router

# Import models so SQLAlchemy metadata is fully registered before create_all.
from app import models  # noqa: F401


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
        ensure_sqlite_schema_compatibility()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(users_router, prefix=settings.api_prefix)
app.include_router(webhook_router, prefix=settings.api_prefix)
app.include_router(streams_router, prefix=settings.api_prefix)
