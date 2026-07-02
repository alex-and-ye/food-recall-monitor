import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from logging_config import configure_logging

configure_logging()

from routes.alerts import router as alerts_router
from routes.pipeline import router as pipeline_router

LOGGER = logging.getLogger(__name__)

app = FastAPI(
    title="Food Recall Monitor API",
    description="API for monitoring food recalls and providing alerts.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts_router)
app.include_router(pipeline_router)


@app.middleware("http")
async def trace_request_lifecycle(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4()))
    started_at = time.perf_counter()
    client_ip = request.client.host if request.client is not None else None

    LOGGER.info(
        "HTTP request started",
        extra={
            "event": "http_request_started",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query,
            "client_ip": client_ip,
        },
    )

    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
        LOGGER.exception(
            "HTTP request failed",
            extra={
                "event": "http_request_failed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query,
                "client_ip": client_ip,
                "duration_ms": elapsed_ms,
            },
        )
        raise

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
    response.headers["x-request-id"] = request_id
    LOGGER.info(
        "HTTP request completed",
        extra={
            "event": "http_request_completed",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query,
            "client_ip": client_ip,
            "status_code": response.status_code,
            "duration_ms": elapsed_ms,
        },
    )
    return response


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