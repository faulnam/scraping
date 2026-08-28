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
    next: Optional[str] = "/",
    db: Session = Depends(get_db)
):
    """Render login page or redirect if already authenticated."""
    current_user = get_current_user_optional(request, db)
    if current_user:
        return RedirectResponse(url=next or "/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "next": next or "/",
            "error_message": None
        }
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form("/"),
    db: Session = Depends(get_db)
):
    """Authenticate user credentials and set session cookie."""
    clean_username = username.strip()
    user = db.query(models.User).filter(models.User.username == clean_username).first()

    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "username": clean_username,
                "next": next or "/",
                "error_message": "Username atau kata sandi tidak valid. Silakan coba lagi."
            },
            status_code=401
        )

    # Update last login timestamp
    user.last_login_at = datetime.utcnow()
    db.commit()

    # Create signed session token
    token = create_session_token(user.id)
    redirect_target = next if next and next.startswith("/") else "/"

    redirect_resp = RedirectResponse(url=redirect_target, status_code=303)
    redirect_resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=DEFAULT_SESSION_MAX_AGE_DAYS * 86400,
        httponly=True,
        samesite="lax"
    )
    return redirect_resp


@router.get("/logout")
@router.post("/logout")
async def logout(request: Request):
    """Clear session cookie and redirect to login page."""
    redirect_resp = RedirectResponse(url="/login?logged_out=1", status_code=303)
    redirect_resp.delete_cookie(key=SESSION_COOKIE_NAME)
    return redirect_resp
