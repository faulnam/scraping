from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import os

from app.config import get_settings
from app.database import init_db, SessionLocal
from app.auth import SESSION_COOKIE_NAME, verify_session_token
from app.routers import auth, dashboard, leads, history, export, settings as settings_router, outreach
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from app import models

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

# Enable Proxy Headers for Nginx Reverse Proxy (HTTPS scheme detection)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Authentication Guard Middleware
PUBLIC_PREFIXES = ("/landing", "/login", "/logout", "/static", "/favicon.ico")

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    
    # Check session token and inject user into request.state
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = verify_session_token(token) if token else None

    # Load user into request.state if authenticated
    user = None
    if user_id:
        db = SessionLocal()
        try:
            user = db.query(models.User).filter(
                models.User.id == user_id,
                models.User.is_active == True  # noqa: E712
            ).first()
            if user:
                _ = (user.id, user.username, user.full_name, user.role, user.is_admin, user.is_active)
                db.expunge(user)
        except Exception as e:
            print(f"[Auth Middleware] Error loading user {user_id}: {e}")
            user = None
        finally:
            db.close()
    
    request.state.current_user = user
    request.state.user_id = user.id if user else None

    # Allow public endpoints
    if any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers.setdefault("Cache-Control", "no-cache, no-store, must-revalidate")
            response.headers.setdefault("Pragma", "no-cache")
            response.headers.setdefault("Vary", "Cookie")
        return response

    # Allow root endpoint "/" (handles redirection or landing rendering)
    if path == "/":
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers.setdefault("Cache-Control", "no-cache, no-store, must-revalidate")
            response.headers.setdefault("Pragma", "no-cache")
            response.headers.setdefault("Vary", "Cookie")
        return response
    
    # Protected endpoints require authentication
    if not user:
        if request.headers.get("hx-request"):
            resp = HTMLResponse(content="", status_code=200)
            resp.headers["HX-Redirect"] = f"/login?next={path}"
            return resp
        return RedirectResponse(url=f"/login?next={path}", status_code=303)

    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        response.headers.setdefault("Cache-Control", "no-cache, no-store, must-revalidate")
        response.headers.setdefault("Pragma", "no-cache")
        response.headers.setdefault("Vary", "Cookie")
    return response


# Mount static files directory
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon_route():
    favicon_path = "app/static/img/favicon.jpg"
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/jpeg")
    return HTMLResponse(status_code=404)

# Include main routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(leads.router)
app.include_router(history.router)
app.include_router(export.router)
app.include_router(settings_router.router)
app.include_router(outreach.router)
