"""
Authentication Router: Login, session handling, and logout endpoints.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user_optional
from app import models
from app.auth import (
    hash_password,
    verify_password,
    create_session_token,
    SESSION_COOKIE_NAME,
    DEFAULT_SESSION_MAX_AGE_DAYS
)

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_view(
    request: Request,
    next: Optional[str] = "/dashboard",
    db: Session = Depends(get_db)
):
    """Render login page allowing login or switching accounts."""
    current_user = get_current_user_optional(request, db)
    
    # If already logged in and not explicitly logging out, redirect straight to dashboard
    if current_user and not request.query_params.get("logged_out"):
        target = next if next and next.startswith("/") and not next.startswith("/login") and not next.startswith("/landing") and next != "/" else "/dashboard"
        resp = RedirectResponse(url=target, status_code=303)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        return resp

    resp = templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "current_user": current_user,
            "next": next or "/dashboard",
            "error_message": None
        }
    )
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form("/dashboard"),
    db: Session = Depends(get_db)
):
    """Authenticate user credentials and set fresh session cookie."""
    clean_username = username.strip()
    user = db.query(models.User).filter(models.User.username == clean_username).first()

    if not user or not user.is_active or not verify_password(password, user.password_hash):
        current_user = get_current_user_optional(request, db)
        resp = templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "current_user": current_user,
                "username": clean_username,
                "next": next or "/dashboard",
                "error_message": "Username atau kata sandi tidak valid. Silakan coba lagi."
            },
            status_code=401
        )
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        return resp

    # Update last login timestamp
    user.last_login_at = datetime.utcnow()
    db.commit()

    # Create signed session token for authenticated user
    token = create_session_token(user.id)
    
    # Always redirect to /dashboard unless specifically targeted to another valid app subpath
    if next and next.startswith("/") and not next.startswith("/login") and not next.startswith("/landing") and next != "/":
        redirect_target = next
    else:
        redirect_target = "/dashboard"

    redirect_resp = RedirectResponse(url=redirect_target, status_code=303)
    redirect_resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=DEFAULT_SESSION_MAX_AGE_DAYS * 86400,
        path="/",
        httponly=True,
        samesite="lax"
    )
    redirect_resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    redirect_resp.headers["Pragma"] = "no-cache"
    return redirect_resp


@router.get("/logout")
@router.post("/logout")
async def logout(request: Request):
    """Clear session cookie and redirect to login page."""
    redirect_resp = RedirectResponse(url="/login?logged_out=1", status_code=303)
    redirect_resp.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    redirect_resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    redirect_resp.headers["Pragma"] = "no-cache"
    return redirect_resp
