from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from paths import ensure_backend_data_dirs
from routes.alerts import router as alerts_router
from routes.pipeline import router as pipeline_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_backend_data_dirs()
    yield

app = FastAPI(
    title="Food Recall Monitor API",
    description="API for monitoring food recalls and providing alerts.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts_router)
app.include_router(pipeline_router)


@app.get("/")
async def root():
    return {
        "message": "Welcome to the Food Recall Monitor API!"
    }

@app.get("/health")
async def check_health():
    return {
        "status": "healthy"
    }