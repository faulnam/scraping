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

