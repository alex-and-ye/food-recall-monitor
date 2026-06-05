from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.server.routes import alerts, pipeline

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

app.include_router(alerts.router)
app.include_router(pipeline.router)

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