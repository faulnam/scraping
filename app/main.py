from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import os

from app.config import get_settings
from app.database import init_db
from app.auth import SESSION_COOKIE_NAME, verify_session_token
from app.routers import auth, dashboard, leads, history, export, settings as settings_router

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

# Authentication Guard Middleware
PUBLIC_PREFIXES = ("/login", "/logout", "/static", "/favicon.ico")

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    
    # Allow public endpoints
    if any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return await call_next(request)
    
    # Check session token
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = verify_session_token(token) if token else None
    
    if not user_id:
        # Check if HTMX request
        if request.headers.get("hx-request"):
            resp = HTMLResponse(content="", status_code=200)
            resp.headers["HX-Redirect"] = f"/login?next={path}"
            return resp
        
        # Standard browser navigation -> redirect to /login
        return RedirectResponse(url=f"/login?next={path}", status_code=303)
    
    response = await call_next(request)
    return response


# Mount static files directory
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include main routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(leads.router)
app.include_router(history.router)
app.include_router(export.router)
app.include_router(settings_router.router)
