from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.models import User

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 开发阶段自动建表；生产环境请使用 Alembic 迁移
    Base.metadata.create_all(bind=engine)
    avatars_dir = settings.UPLOAD_DIR / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    if settings.ADMIN_INITIAL_EMAIL:
        with SessionLocal() as db:
            admin = db.scalar(
                select(User).where(User.email == settings.ADMIN_INITIAL_EMAIL)
            )
            if admin is not None:
                admin.role = "admin"
                db.commit()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="基于大模型的自适应学习平台 API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.APP_NAME}
