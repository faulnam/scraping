from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import os

from app.config import get_settings
from app.database import init_db
from app.routers import dashboard, leads, history, export, settings as settings_router

settings = get_settings()
templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure static directories exist and initialize database tables
    os.makedirs("app/static/css", exist_ok=True)
    os.makedirs("app/static/src", exist_ok=True)
    try:
        init_db()
    except Exception as e:
        print(f"[Warning] Failed to initialize DB tables automatically: {e}")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Mount static files directory
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include main routers
app.include_router(dashboard.router)
app.include_router(leads.router)
app.include_router(history.router)
app.include_router(export.router)
app.include_router(settings_router.router)

