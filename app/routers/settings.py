"""
Settings & Guide Router: Manage outreach profile, custom WhatsApp default templates,
portfolio demo catalogue, multi-API key management with auto-fallback, account settings, and guide.
"""
from datetime import datetime
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app import models
from app.auth import hash_password, verify_password
from app.routers.leads import DEFAULT_WA_TEMPLATE

router = APIRouter(tags=["settings"])
templates = Jinja2Templates(directory="app/templates")


# ==============================================================================
# 1. Profil Bisnis & Template WhatsApp
# ==============================================================================

@router.get("/settings/profile", response_class=HTMLResponse)
async def profile_view(
    request: Request,
    db: Session = Depends(get_db)
):
    """Render Business Profile, WhatsApp template, and Portfolio configuration."""
    profile = db.query(models.BusinessProfile).first()
    portfolios = db.query(models.PortfolioItem).order_by(models.PortfolioItem.id.asc()).all()

    company_name = profile.company_name if profile else "JuangDev Solutions"
    contact_person = profile.contact_person if profile else "Tim Konsultan Web"
    phone = profile.phone if profile else "081234567890"
    website_url = getattr(profile, "website_url", None) if profile and getattr(profile, "website_url", None) else "https://juangdev.my.id"
    wa_template = profile.default_wa_template if profile and profile.default_wa_template else DEFAULT_WA_TEMPLATE

    return templates.TemplateResponse(
        request=request,
        name="settings_profile.html",
        context={
            "active_page": "profile",
            "profile": profile,
            "portfolios": portfolios,
            "company_name": company_name,
            "contact_person": contact_person,
            "phone": phone,
            "website_url": website_url,
            "wa_template": wa_template,
        }
    )


@router.post("/settings/profile", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    company_name: str = Form(...),
    contact_person: Optional[str] = Form(""),
    phone: Optional[str] = Form(""),
    website_url: Optional[str] = Form("https://juangdev.my.id"),
    default_wa_template: Optional[str] = Form(DEFAULT_WA_TEMPLATE),
    db: Session = Depends(get_db)
):
    """Update or create BusinessProfile record in MySQL."""
    profile = db.query(models.BusinessProfile).first()
    now = datetime.utcnow()

    clean_website_url = website_url.strip() if website_url and website_url.strip() else "https://juangdev.my.id"

    if not profile:
        profile = models.BusinessProfile(
            company_name=company_name.strip(),
            contact_person=contact_person.strip() if contact_person else None,
            phone=phone.strip() if phone else None,
            website_url=clean_website_url,
            default_wa_template=default_wa_template.strip() if default_wa_template else DEFAULT_WA_TEMPLATE,
            updated_at=now
        )
        db.add(profile)
    else:
        profile.company_name = company_name.strip()
        profile.contact_person = contact_person.strip() if contact_person else None
        profile.phone = phone.strip() if phone else None
        profile.website_url = clean_website_url
        profile.default_wa_template = default_wa_template.strip() if default_wa_template else DEFAULT_WA_TEMPLATE
        profile.updated_at = now

    db.commit()
    db.refresh(profile)

    portfolios = db.query(models.PortfolioItem).order_by(models.PortfolioItem.id.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="settings_profile.html",
        context={
            "active_page": "profile",
            "profile": profile,
            "portfolios": portfolios,
            "company_name": profile.company_name,
            "contact_person": profile.contact_person or "",
            "phone": profile.phone or "",
            "website_url": getattr(profile, "website_url", None) or "https://juangdev.my.id",
            "wa_template": profile.default_wa_template,
            "success_message": "Profil bisnis, website resmi, dan template WhatsApp berhasil disimpan!"
        }
    )


# ==============================================================================
# 2. Portfolio Demo Presets
# ==============================================================================

@router.post("/settings/portfolios", response_class=HTMLResponse)
async def add_portfolio_item(
    request: Request,
    title: str = Form(...),
    category_keywords: Optional[str] = Form(""),
    demo_url: str = Form(...),
    pitch_snippet: Optional[str] = Form(""),
    is_default: Optional[bool] = Form(False),
    db: Session = Depends(get_db)
):
    """Add a new Portfolio / Demo link preset to MySQL."""
    if is_default:
        db.query(models.PortfolioItem).update({models.PortfolioItem.is_default: False})

    new_item = models.PortfolioItem(
        title=title.strip(),
        category_keywords=category_keywords.strip() if category_keywords else "",
        demo_url=demo_url.strip(),
        pitch_snippet=pitch_snippet.strip() if pitch_snippet else "",
        is_default=bool(is_default),
        created_at=datetime.utcnow()
    )
    db.add(new_item)
    db.commit()

    return RedirectResponse(url="/settings/profile?portfolio_added=1", status_code=303)


@router.post("/settings/portfolios/{portfolio_id}/delete", response_class=HTMLResponse)
async def delete_portfolio_item(
    request: Request,
    portfolio_id: int,
    db: Session = Depends(get_db)
):
    """Delete a Portfolio preset from MySQL."""
    item = db.query(models.PortfolioItem).filter(models.PortfolioItem.id == portfolio_id).first()
    if item:
        db.delete(item)
        db.commit()

    return RedirectResponse(url="/settings/profile?portfolio_deleted=1", status_code=303)


# ==============================================================================
# 3. Multi-API Key Management & Auto-Fallback Panel
# ==============================================================================

@router.get("/settings/api-keys", response_class=HTMLResponse)
async def api_keys_view(
    request: Request,
    db: Session = Depends(get_db)
):
    """Render Multi-API Key Management panel."""
    keys = db.query(models.ApiKeyConfig).order_by(models.ApiKeyConfig.priority.asc(), models.ApiKeyConfig.id.asc()).all()

    total_active_keys = sum(1 for k in keys if k.is_active and k.status != "exhausted")
    total_quota_limit = sum(k.quota_limit or 0 for k in keys if k.is_active)
    total_requests_used = sum(k.requests_used or 0 for k in keys)

    return templates.TemplateResponse(
        request=request,
        name="settings_api_keys.html",
        context={
            "active_page": "api_keys",
            "keys": keys,
            "total_active_keys": total_active_keys,
            "total_quota_limit": total_quota_limit,
            "total_requests_used": total_requests_used,
        }
    )


@router.post("/settings/api-keys/create", response_class=HTMLResponse)
async def create_api_key(
    request: Request,
    label: str = Form(...),
    provider: str = Form("serpapi"),
    api_key: str = Form(...),
    quota_limit: int = Form(250),
    priority: int = Form(1),
    db: Session = Depends(get_db)
):
    """Add a new API key to the rotation pool."""
    clean_key = api_key.strip()
    if not clean_key:
        return RedirectResponse(url="/settings/api-keys?error=API+Key+tidak+boleh+kosong", status_code=303)

    new_key = models.ApiKeyConfig(
        provider=provider.strip(),
        label=label.strip(),
        api_key=clean_key,
        quota_limit=max(1, quota_limit),
        priority=max(1, priority),
        is_active=True,
        status="active",
        requests_used=0,
        created_at=datetime.utcnow()
    )
    db.add(new_key)
    db.commit()

    return RedirectResponse(url="/settings/api-keys?added=1", status_code=303)


@router.post("/settings/api-keys/{key_id}/toggle", response_class=HTMLResponse)
async def toggle_api_key(
    key_id: int,
    db: Session = Depends(get_db)
):
    """Enable or disable an API key."""
    key = db.query(models.ApiKeyConfig).filter(models.ApiKeyConfig.id == key_id).first()
    if key:
        key.is_active = not key.is_active
        db.commit()
    return RedirectResponse(url="/settings/api-keys?toggled=1", status_code=303)


@router.post("/settings/api-keys/{key_id}/set-primary", response_class=HTMLResponse)
async def set_primary_api_key(
    key_id: int,
    db: Session = Depends(get_db)
):
    """Make this key Priority 1 (Primary)."""
    target = db.query(models.ApiKeyConfig).filter(models.ApiKeyConfig.id == key_id).first()
    if target:
        all_keys = db.query(models.ApiKeyConfig).filter(models.ApiKeyConfig.id != key_id).order_by(models.ApiKeyConfig.priority.asc()).all()
        target.priority = 1
        for idx, k in enumerate(all_keys, start=2):
            k.priority = idx
        db.commit()
    return RedirectResponse(url="/settings/api-keys?primary_set=1", status_code=303)


@router.post("/settings/api-keys/{key_id}/reset-status", response_class=HTMLResponse)
async def reset_api_key_status(
    key_id: int,
    db: Session = Depends(get_db)
):
    """Reset key status back to 'active' and clear error."""
    key = db.query(models.ApiKeyConfig).filter(models.ApiKeyConfig.id == key_id).first()
    if key:
        key.status = "active"
        key.last_error_message = None
        db.commit()
    return RedirectResponse(url="/settings/api-keys?status_reset=1", status_code=303)


@router.post("/settings/api-keys/{key_id}/delete", response_class=HTMLResponse)
async def delete_api_key(
    key_id: int,
    db: Session = Depends(get_db)
):
    """Delete an API key from the system."""
    key = db.query(models.ApiKeyConfig).filter(models.ApiKeyConfig.id == key_id).first()
    if key:
        db.delete(key)
        db.commit()
    return RedirectResponse(url="/settings/api-keys?deleted=1", status_code=303)


@router.post("/settings/api-keys/{key_id}/test", response_class=HTMLResponse)
async def test_api_key(
    key_id: int,
    db: Session = Depends(get_db)
):
    """Test live connectivity of an API Key."""
    key = db.query(models.ApiKeyConfig).filter(models.ApiKeyConfig.id == key_id).first()
    if not key:
        return HTMLResponse("<span class='text-xs text-rose-500 font-semibold'>API Key tidak ditemukan.</span>")

    try:
        if key.provider == "serpapi":
            url = f"https://serpapi.com/account.json?api_key={key.api_key}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    remaining = data.get("total_searches_left", "N/A")
                    plan = data.get("plan_name", "Free / Starter")
                    key.status = "active"
                    key.last_error_message = None
                    db.commit()
                    return HTMLResponse(f"<span class='text-[11px] text-emerald-600 font-semibold bg-emerald-50 px-2 py-1 rounded border border-emerald-200'>✅ Valid! Sisa: {remaining} search ({plan})</span>")
                else:
                    err_msg = f"HTTP {resp.status_code}: {resp.text}"
                    key.status = "exhausted" if resp.status_code in (401, 429) else "error"
                    key.last_error_message = err_msg[:200]
                    db.commit()
                    return HTMLResponse(f"<span class='text-[11px] text-rose-600 font-semibold bg-rose-50 px-2 py-1 rounded border border-rose-200'>❌ Gagal: {resp.status_code}</span>")
        else:
            # Google Places API test
            url = f"https://places.googleapis.com/v1/places:searchText"
            headers = {"X-Goog-Api-Key": key.api_key, "X-Goog-FieldMask": "places.id"}
            body = {"textQuery": "test", "pageSize": 1}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=body)
                if resp.status_code == 200:
                    key.status = "active"
                    key.last_error_message = None
                    db.commit()
                    return HTMLResponse("<span class='text-[11px] text-emerald-600 font-semibold bg-emerald-50 px-2 py-1 rounded border border-emerald-200'>✅ Valid Google Places API Key</span>")
                else:
                    key.status = "error"
                    key.last_error_message = f"HTTP {resp.status_code}"
                    db.commit()
                    return HTMLResponse(f"<span class='text-[11px] text-rose-600 font-semibold bg-rose-50 px-2 py-1 rounded border border-rose-200'>❌ Gagal: HTTP {resp.status_code}</span>")
    except Exception as e:
        return HTMLResponse(f"<span class='text-[11px] text-rose-600 font-semibold bg-rose-50 px-2 py-1 rounded border border-rose-200'>⚠️ Error: {str(e)[:40]}</span>")


# ==============================================================================
# 4. Akun Admin & Ganti Password
# ==============================================================================

@router.post("/settings/account/password", response_class=HTMLResponse)
async def update_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Change logged-in user password."""
    if not verify_password(old_password, current_user.password_hash):
        return RedirectResponse(url="/settings/profile?pw_error=Kata+sandi+lama+tidak+cocok", status_code=303)

    if len(new_password) < 6:
        return RedirectResponse(url="/settings/profile?pw_error=Kata+sandi+baru+minimal+6+karakter", status_code=303)

    if new_password != confirm_password:
        return RedirectResponse(url="/settings/profile?pw_error=Konfirmasi+kata+sandi+tidak+cocok", status_code=303)

    current_user.password_hash = hash_password(new_password)
    db.commit()

    return RedirectResponse(url="/settings/profile?pw_success=1", status_code=303)


# ==============================================================================
# 5. Panduan & Metodologi
# ==============================================================================

@router.get("/guide", response_class=HTMLResponse)
async def guide_view(request: Request):
    """Render static methodology and ethical outreach documentation."""
    return templates.TemplateResponse(
        request=request,
        name="guide.html",
        context={
            "active_page": "guide"
        }
    )
