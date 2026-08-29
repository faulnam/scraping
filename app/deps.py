from datetime import datetime, timedelta
from typing import Generator, Optional
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models
from app.auth import SESSION_COOKIE_NAME, verify_session_token


def get_db() -> Generator[Session, None, None]:
    """Dependency generator that provides a SQLAlchemy database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[models.User]:
    """Get current logged in user from session cookie if present, else None."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    user_id = verify_session_token(token)
    if not user_id:
        return None

    user = db.query(models.User).filter(models.User.id == user_id, models.User.is_active == True).first()  # noqa: E712
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> models.User:
    """Enforce authentication. If not logged in, raise 401 / redirect trigger."""
    user = get_current_user_optional(request, db)
    if not user:
        # Check if request accepts HTML (browser page navigation)
        accept = request.headers.get("accept", "")
        if "text/html" in accept and not request.headers.get("hx-request"):
            raise HTTPException(
                status_code=303,
                headers={"Location": f"/login?next={request.url.path}"}
            )
        raise HTTPException(
            status_code=401,
            detail="Otentikasi dibutuhkan. Harap login terlebih dahulu."
        )
    return user


def require_admin_role(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    """Ensure the current user has full 'admin' role. Blocks admin_demo from sensitive endpoints."""
    if getattr(current_user, "role", "admin") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak. Hanya Admin yang dapat mengakses halaman ini."
        )
    return current_user


def check_demo_crawl_token(user: models.User, db: Session) -> dict:
    """
    Check and consume a crawl token for Admin Demo users.
    Returns dict with 'allowed' (bool), 'tokens_used', 'tokens_remaining', 'message'.
    Admin (full) users always get unlimited access.
    """
    role = getattr(user, "role", "admin")
    if role != "admin_demo":
        return {"allowed": True, "tokens_used": 0, "tokens_remaining": 999, "message": ""}

    now = datetime.utcnow()
    window_24h_ago = now - timedelta(hours=24)

    token_record = db.query(models.DemoToken).filter(
        models.DemoToken.user_id == user.id
    ).first()

    if not token_record:
        # First-time usage: create token record
        token_record = models.DemoToken(
            user_id=user.id,
            tokens_used=1,
            window_start=now,
            max_tokens=3
        )
        db.add(token_record)
        db.commit()
        db.refresh(token_record)
        return {"allowed": True, "tokens_used": 1, "tokens_remaining": 2, "message": ""}

    # Check if window has expired (reset)
    if token_record.window_start < window_24h_ago:
        token_record.tokens_used = 1
        token_record.window_start = now
        db.commit()
        return {"allowed": True, "tokens_used": 1, "tokens_remaining": 2, "message": ""}

    # Window still active
    if token_record.tokens_used >= token_record.max_tokens:
        remaining_seconds = int((token_record.window_start + timedelta(hours=24) - now).total_seconds())
        hours_left = remaining_seconds // 3600
        mins_left = (remaining_seconds % 3600) // 60
        return {
            "allowed": False,
            "tokens_used": token_record.tokens_used,
            "tokens_remaining": 0,
            "message": f"Batas token crawling tercapai ({token_record.max_tokens}x per 24 jam). Token akan direset dalam {hours_left} jam {mins_left} menit."
        }

    # Consume a token
    token_record.tokens_used += 1
    db.commit()
    remaining = token_record.max_tokens - token_record.tokens_used
    return {"allowed": True, "tokens_used": token_record.tokens_used, "tokens_remaining": remaining, "message": ""}


def get_demo_token_info(user: models.User, db: Session) -> dict:
    """Get current token usage info without consuming a token. For display purposes only."""
    role = getattr(user, "role", "admin")
    if role != "admin_demo":
        return {"is_demo": False, "tokens_used": 0, "tokens_remaining": 999, "max_tokens": 999}

    now = datetime.utcnow()
    window_24h_ago = now - timedelta(hours=24)

    token_record = db.query(models.DemoToken).filter(
        models.DemoToken.user_id == user.id
    ).first()

    if not token_record:
        return {"is_demo": True, "tokens_used": 0, "tokens_remaining": 3, "max_tokens": 3}

    if token_record.window_start < window_24h_ago:
        return {"is_demo": True, "tokens_used": 0, "tokens_remaining": 3, "max_tokens": 3}

    remaining = max(0, token_record.max_tokens - token_record.tokens_used)
    return {
        "is_demo": True,
        "tokens_used": token_record.tokens_used,
        "tokens_remaining": remaining,
        "max_tokens": token_record.max_tokens
    }
