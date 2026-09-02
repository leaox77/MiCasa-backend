from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.routers import auth, users, properties, favorites, interest, admin, reports, publisher, views

settings = get_settings()

app = FastAPI(
    title="Mi Casa API",
    version="1.0.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,       prefix="/api/v1")
app.include_router(users.router,      prefix="/api/v1")
app.include_router(properties.router, prefix="/api/v1")
app.include_router(favorites.router,  prefix="/api/v1")
app.include_router(interest.router,   prefix="/api/v1")
app.include_router(publisher.router,  prefix="/api/v1")
app.include_router(admin.router,      prefix="/api/v1")
app.include_router(reports.router,    prefix="/api/v1")
app.include_router(views.router,      prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.app_env}