import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bootstrap import run_state_aware_bootstrap
from dependencies import get_alert_change_broadcaster, get_db, get_alerts_service, get_pipeline_service
from paths import ensure_backend_data_dirs
from routes.alerts import router as alerts_router
from routes.pipeline import router as pipeline_router
from scheduler import start_daily_pipeline_scheduler, stop_daily_pipeline_scheduler

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_backend_data_dirs()

    db = get_db()
    pipeline_service = get_pipeline_service(db, get_alert_change_broadcaster())
    alerts_service = get_alerts_service(db)

    await run_state_aware_bootstrap(alerts_service, pipeline_service)
    scheduler_task, stop_event = start_daily_pipeline_scheduler(pipeline_service)

    yield

    await stop_daily_pipeline_scheduler(scheduler_task, stop_event)

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