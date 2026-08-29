"""
Outreach Speed-Dial Router: Batch WhatsApp outreach mode for rapid lead contact.
Enables Admin to send WA messages to multiple leads sequentially without
returning to the table after each send.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
import urllib.parse
from fastapi import APIRouter, Depends, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_

from app.deps import get_db
from app import models
from app.routers.leads import (
    get_profile_data,
    match_portfolio_for_business,
    build_personalized_wa_link,
    PITCH_TEMPLATES,
)

router = APIRouter(tags=["outreach"])
templates = Jinja2Templates(directory="app/templates")

# Quick note chip presets
QUICK_NOTE_CHIPS = [
    {"label": "Nomor Tidak Aktif", "value": "Nomor tidak aktif / tidak bisa dihubungi"},
    {"label": "Respon Positif", "value": "Prospek merespon positif, tertarik dengan penawaran"},
    {"label": "Minta Proposal", "value": "Prospek meminta dikirimkan proposal/penawaran harga"},
    {"label": "Sudah Punya Vendor", "value": "Sudah memiliki vendor web / tidak memerlukan saat ini"},
    {"label": "Minta Dihubungi Lagi", "value": "Prospek meminta dihubungi lagi di lain waktu"},
    {"label": "Nomor Salah", "value": "Nomor telepon salah / bukan milik usaha ini"},
    {"label": "Tidak Ada Respons", "value": "Pesan terkirim, belum ada respons"},
]


def _build_outreach_queue(
    db: Session,
    filter_mode: str = "new_high",
    lead_ids: Optional[str] = None,
    limit: int = 50
) -> List[models.Business]:
    """Build a queue of leads for outreach based on filter mode."""
    query = db.query(models.Business).outerjoin(
        models.LeadStatus, models.Business.id == models.LeadStatus.business_id
    )

    if lead_ids:
        # Specific lead IDs from bulk selection
        id_list = [int(x) for x in lead_ids.split(",") if x.strip().isdigit()]
        if id_list:
            query = query.filter(models.Business.id.in_(id_list))
    elif filter_mode == "new_high":
        # New HIGH priority leads that haven't been contacted
        query = query.filter(
            models.LeadStatus.priority == models.LeadPriority.HIGH,
            or_(
                models.LeadStatus.contact_status == models.ContactStatus.BELUM_DIHUBUNGI,
                models.LeadStatus.contact_status.is_(None)
            )
        )
    elif filter_mode == "followup_today":
        # Leads with follow-up scheduled for today or overdue
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start.replace(hour=23, minute=59, second=59)
        query = query.filter(
            models.LeadStatus.next_followup_at.isnot(None),
            models.LeadStatus.next_followup_at <= tomorrow_start
        )
    elif filter_mode == "not_contacted":
        # All leads not yet contacted
        query = query.filter(
            or_(
                models.LeadStatus.contact_status == models.ContactStatus.BELUM_DIHUBUNGI,
                models.LeadStatus.contact_status.is_(None)
            )
        )
    elif filter_mode == "no_website":
        # Leads without website
        query = query.filter(models.Business.has_website == False)  # noqa: E712
        query = query.filter(
            or_(
                models.LeadStatus.contact_status == models.ContactStatus.BELUM_DIHUBUNGI,
                models.LeadStatus.contact_status.is_(None)
            )
        )

    # Only include leads with phone numbers
    query = query.filter(
        models.Business.phone.isnot(None),
        models.Business.phone != ""
    )

    query = query.order_by(
        desc(models.LeadStatus.priority),
        desc(models.Business.rating_avg)
    )

    return query.limit(limit).all()


@router.get("/outreach", response_class=HTMLResponse)
async def outreach_view(
    request: Request,
    filter_mode: str = "new_high",
    lead_ids: Optional[str] = None,
    current_index: int = 0,
    db: Session = Depends(get_db)
):
    """Render Outreach Speed-Dial Mode page."""
    queue = _build_outreach_queue(db, filter_mode=filter_mode, lead_ids=lead_ids)
    total_queue = len(queue)

    if total_queue == 0:
        return templates.TemplateResponse(
            request=request,
            name="outreach.html",
            context={
                "active_page": "outreach",
                "queue_empty": True,
                "total_queue": 0,
                "current_index": 0,
                "filter_mode": filter_mode,
                "lead_ids": lead_ids or "",
                "business": None,
                "quick_note_chips": QUICK_NOTE_CHIPS,
            }
        )

    # Clamp index
    current_index = max(0, min(current_index, total_queue - 1))
    current_lead = queue[current_index]

    company_name, contact_person, website_url, wa_template = get_profile_data(db)
    matched_portfolio = match_portfolio_for_business(current_lead, db)
    portfolios = db.query(models.PortfolioItem).all()

    # Build WA link
    wa_link = build_personalized_wa_link(
        current_lead.phone,
        current_lead.business_name,
        wa_template,
        portfolio=matched_portfolio,
        company_name=company_name,
        contact_person=contact_person,
        website_url=website_url
    )

    # Build pitch text for display
    pitch_text = wa_template
    pitch_text = pitch_text.replace("{business_name}", current_lead.business_name or "")
    pitch_text = pitch_text.replace("{portfolio_name}", matched_portfolio.title if matched_portfolio else "Website Profesional")
    pitch_text = pitch_text.replace("{portfolio_url}", matched_portfolio.demo_url if matched_portfolio else "https://juangdev.my.id")
    pitch_text = pitch_text.replace("{pitch_snippet}", matched_portfolio.pitch_snippet if matched_portfolio and matched_portfolio.pitch_snippet else "")
    pitch_text = pitch_text.replace("{company_name}", company_name)
    pitch_text = pitch_text.replace("{contact_person}", contact_person)
    pitch_text = pitch_text.replace("{website_url}", website_url)

    # Standardize phone
    clean_digits = "".join([c for c in (current_lead.phone or "") if c.isdigit()])
    if clean_digits.startswith("08"):
        target_phone_wa = "62" + clean_digits[1:]
    elif clean_digits.startswith("8"):
        target_phone_wa = "62" + clean_digits
    elif clean_digits.startswith("62"):
        target_phone_wa = clean_digits
    else:
        target_phone_wa = ""

    # Activity log for this lead
    activities = db.query(models.ActivityLog).filter(
        models.ActivityLog.business_id == current_lead.id
    ).order_by(desc(models.ActivityLog.created_at)).limit(5).all()

    return templates.TemplateResponse(
        request=request,
        name="outreach.html",
        context={
            "active_page": "outreach",
            "queue_empty": False,
            "total_queue": total_queue,
            "current_index": current_index,
            "filter_mode": filter_mode,
            "lead_ids": lead_ids or "",
            "business": current_lead,
            "lead_status": current_lead.lead_status,
            "matched_portfolio": matched_portfolio,
            "portfolios": portfolios,
            "pitch_templates": PITCH_TEMPLATES,
            "company_name": company_name,
            "contact_person": contact_person,
            "website_url": website_url,
            "pitch_text": pitch_text,
            "wa_link": wa_link,
            "target_phone_wa": target_phone_wa,
            "quick_note_chips": QUICK_NOTE_CHIPS,
            "activities": activities,
            "contact_status_enum": models.ContactStatus,
        }
    )


@router.post("/outreach/{business_id}/mark-sent", response_class=HTMLResponse)
async def mark_sent_and_next(
    request: Request,
    business_id: int,
    filter_mode: str = Form("new_high"),
    lead_ids: Optional[str] = Form(""),
    current_index: int = Form(0),
    quick_note: Optional[str] = Form(None),
    custom_note: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Mark current lead as 'Sudah Dihubungi', log activity, and redirect to next lead.
    """
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        return HTMLResponse("<p>Lead tidak ditemukan.</p>", status_code=404)

    now = datetime.utcnow()
    user = getattr(request.state, "current_user", None)
    username = user.full_name or user.username if user else "Admin"

    # Update lead status
    lead_status = business.lead_status
    if not lead_status:
        lead_status = models.LeadStatus(
            business_id=business.id,
            contact_status=models.ContactStatus.SUDAH_DIHUBUNGI,
            priority=models.LeadPriority.LOW,
            last_contacted_at=now,
            updated_at=now
        )
        db.add(lead_status)
    else:
        lead_status.contact_status = models.ContactStatus.SUDAH_DIHUBUNGI
        lead_status.last_contacted_at = now
        lead_status.updated_at = now

    # Save note
    note_text = quick_note or custom_note
    if note_text and note_text.strip():
        if lead_status.notes:
            lead_status.notes = f"{lead_status.notes}\n[{now.strftime('%d/%m/%y %H:%M')}] {note_text.strip()}"
        else:
            lead_status.notes = f"[{now.strftime('%d/%m/%y %H:%M')}] {note_text.strip()}"

    # Log activity
    activity = models.ActivityLog(
        business_id=business.id,
        action="wa_sent",
        detail=f"Pesan WhatsApp dikirim via Outreach Mode. {('Catatan: ' + note_text.strip()) if note_text and note_text.strip() else ''}",
        created_by=username,
        created_at=now
    )
    db.add(activity)
    db.commit()

    # Redirect to next lead
    next_index = current_index + 1
    lead_ids_param = f"&lead_ids={lead_ids}" if lead_ids else ""
    redirect_url = f"/outreach?filter_mode={filter_mode}&current_index={next_index}{lead_ids_param}"

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/outreach/{business_id}/skip", response_class=HTMLResponse)
async def skip_lead(
    request: Request,
    business_id: int,
    filter_mode: str = Form("new_high"),
    lead_ids: Optional[str] = Form(""),
    current_index: int = Form(0),
    skip_reason: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Skip current lead and move to next without sending WA."""
    now = datetime.utcnow()
    user = getattr(request.state, "current_user", None)
    username = user.full_name or user.username if user else "Admin"

    # Log skip activity
    if skip_reason and skip_reason.strip():
        activity = models.ActivityLog(
            business_id=business_id,
            action="skipped",
            detail=f"Dilewati saat Outreach Mode. Alasan: {skip_reason.strip()}",
            created_by=username,
            created_at=now
        )
        db.add(activity)
        db.commit()

    next_index = current_index + 1
    lead_ids_param = f"&lead_ids={lead_ids}" if lead_ids else ""
    redirect_url = f"/outreach?filter_mode={filter_mode}&current_index={next_index}{lead_ids_param}"

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/outreach/{business_id}/quick-note", response_class=HTMLResponse)
async def add_quick_note(
    request: Request,
    business_id: int,
    note: str = Form(...),
    db: Session = Depends(get_db)
):
    """Add a quick note chip to a lead's activity log via HTMX."""
    now = datetime.utcnow()
    user = getattr(request.state, "current_user", None)
    username = user.full_name or user.username if user else "Admin"

    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        return HTMLResponse("<span class='text-xs text-rose-600'>Lead tidak ditemukan.</span>")

    # Append to notes
    lead_status = business.lead_status
    if lead_status:
        if lead_status.notes:
            lead_status.notes = f"{lead_status.notes}\n[{now.strftime('%d/%m/%y %H:%M')}] {note.strip()}"
        else:
            lead_status.notes = f"[{now.strftime('%d/%m/%y %H:%M')}] {note.strip()}"
        lead_status.updated_at = now

    # Log activity
    activity = models.ActivityLog(
        business_id=business_id,
        action="note_added",
        detail=note.strip(),
        created_by=username,
        created_at=now
    )
    db.add(activity)
    db.commit()

    return HTMLResponse(
        f'<span class="text-xs text-emerald-700 font-semibold">Catatan tersimpan: {note.strip()[:50]}</span>'
    )
