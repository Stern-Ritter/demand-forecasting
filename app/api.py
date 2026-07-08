from datetime import datetime, timezone

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import init_db, health_check_db
from controllers import auth, users, balance, forecast, history

API_VERSION = get_settings().API_VERSION or "v1"
API_PREFIX = f"/api/{API_VERSION}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing database...")
    try:
        init_db(drop_all=False)
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database initialization failed: {e}")
        raise
    yield
    print("Shutting down application...")


app = FastAPI(
    title="M5 Demand Forecasting API",
    description="ML service for time-series demand forecasting based on LightGBM",
    version=get_settings().API_VERSION or "1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=f"{API_PREFIX}/auth", tags=["authentication"])
app.include_router(users.router, prefix=f"{API_PREFIX}/users", tags=["users"])
app.include_router(balance.router, prefix=f"{API_PREFIX}/balance", tags=["balance"])
app.include_router(forecast.router, prefix=f"{API_PREFIX}/forecast", tags=["forecast"])
app.include_router(history.router, prefix=f"{API_PREFIX}/history", tags=["history"])


@app.get("/", tags=["system"])
async def root():
    settings = get_settings()
    return {
        "message": f"Welcome to {settings.APP_NAME or 'M5 Demand Forecasting API'}",
        "version": settings.API_VERSION or "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health", tags=["system"])
async def health_check():
    try:
        db_status = health_check_db()
        return {
            "status": "healthy",
            "service": "M5 Demand Forecasting API",
            "version": API_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dependencies": {"database": db_status},
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "service": "M5 Demand Forecasting API",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
