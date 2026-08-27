"""
Settings & Guide Router: Manage outreach profile, custom WhatsApp default templates,
portfolio demo catalogue, and render methodology and ethics documentation.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.deps import get_db
from app import models
from app.routers.leads import DEFAULT_WA_TEMPLATE

router = APIRouter(tags=["settings"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/settings/profile", response_class=HTMLResponse)
async def profile_view(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Render Business Profile and Portfolio Catalogue configuration form.
    """
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
    """
    Update or create BusinessProfile record in MySQL.
    """
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
    """
    Add a new Portfolio / Demo link preset to MySQL.
    """
    if is_default:
        # Reset other default flags
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
    """
    Delete a Portfolio preset from MySQL.
    """
    item = db.query(models.PortfolioItem).filter(models.PortfolioItem.id == portfolio_id).first()
    if item:
        db.delete(item)
        db.commit()

    return RedirectResponse(url="/settings/profile?portfolio_deleted=1", status_code=303)


@router.get("/guide", response_class=HTMLResponse)
async def guide_view(request: Request):
    """
    Render static methodology and ethical outreach documentation.
    """
    return templates.TemplateResponse(
        request=request,
        name="guide.html",
        context={
            "active_page": "guide"
        }
    )
