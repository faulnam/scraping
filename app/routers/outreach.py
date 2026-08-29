"""
Outreach Speed-Dial Router: Batch WhatsApp outreach mode for rapid lead contact.
Enables Admin to send WA messages to multiple leads sequentially without
returning to the table after each send.
Automatically defaults to Uncontacted leads ('belum_dihubungi') so previous progress is saved
and resuming starts exactly on the next uncontacted lead.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
import urllib.parse
from fastapi import APIRouter, Depends, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_
import json
from pathlib import Path

from app.deps import get_db
from app import models
from app.routers.leads import (
    get_profile_data,
    match_portfolio_for_business,
    build_personalized_wa_link,
    PITCH_TEMPLATES,
    DEFAULT_OFFICIAL_WEBSITE,
)

router = APIRouter(tags=["outreach"])
templates = Jinja2Templates(directory="app/templates")

# File to store outreach progress per user
PROGRESS_FILE = Path(__file__).parents[2] / "data" / "outreach_progress.json"

def _load_progress(user_id: int) -> int | None:
    """Load the saved next index for the given user. Returns None if not set."""
    if not PROGRESS_FILE.is_file():
        return None
    try:
        data = json.loads(PROGRESS_FILE.read_text())
        return data.get(str(user_id))
    except Exception:
        return None

def _save_progress(user_id: int, index: int) -> None:
    """Save the next index for the given user to the progress file."""
    data = {}
    if PROGRESS_FILE.is_file():
        try:
            data = json.loads(PROGRESS_FILE.read_text())
        except Exception:
            data = {}
    data[str(user_id)] = index
    # Ensure directory exists
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(data))

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
    user_id: Optional[int] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    crawl_run_id: Optional[str] = None,
    has_website: Optional[str] = None,
    contact_status: Optional[str] = "belum_dihubungi",
    priority: Optional[str] = None,
    filter_mode: Optional[str] = None,
    lead_ids: Optional[str] = None
) -> List[models.Business]:
    """Build an unlimited queue of leads for outreach based on comprehensive filters, isolated by user_id."""
    query = db.query(models.Business).outerjoin(
        models.LeadStatus, models.Business.id == models.LeadStatus.business_id
    )

    if user_id:
        query = query.filter(models.Business.user_id == user_id)

    # 1. Lead IDs (from bulk selection)
    if lead_ids and lead_ids.strip():
        id_list = [int(x) for x in lead_ids.split(",") if x.strip().isdigit()]
        if id_list:
            query = query.filter(models.Business.id.in_(id_list))
    else:
        # 2. Search keyword filter
        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    models.Business.business_name.ilike(term),
                    models.Business.category.ilike(term),
                    models.Business.address.ilike(term),
                    models.Business.location_query.ilike(term),
                    models.Business.phone.ilike(term)
                )
            )

        # 3. Category filter
        if category and category.strip() and category.strip() != "all":
            cat_term = category.strip()
            query = query.filter(
                or_(
                    models.Business.category == cat_term,
                    models.Business.category.ilike(f"%{cat_term}%"),
                    models.Business.location_query.ilike(f"%{cat_term}%")
                )
            )

        # 4. Crawl Run Session filter
        if crawl_run_id and crawl_run_id.strip() and crawl_run_id.strip() != "all" and crawl_run_id.strip().isdigit():
            query = query.filter(models.Business.crawl_run_id == int(crawl_run_id.strip()))

        # 5. Website status filter
        if has_website == "true":
            query = query.filter(models.Business.has_website == True)  # noqa: E712
        elif has_website == "false":
            query = query.filter(models.Business.has_website == False)  # noqa: E712

        # 6. Contact Status filter: Default to 'belum_dihubungi' so sent leads automatically drop off
        active_contact_status = contact_status if (contact_status and contact_status.strip()) else "belum_dihubungi"
        if active_contact_status == "belum_dihubungi":
            query = query.filter(
                or_(
                    models.LeadStatus.contact_status == models.ContactStatus.BELUM_DIHUBUNGI,
                    models.LeadStatus.contact_status.is_(None)
                )
            )
        elif active_contact_status != "all":
            query = query.filter(models.LeadStatus.contact_status == active_contact_status.strip())

        # 7. Priority filter
        if priority and priority.strip() and priority.strip() != "all":
            query = query.filter(models.LeadStatus.priority == priority.strip())

        # 8. Preset filter_mode fallback if specific filters are not set
        if filter_mode == "new_high":
            query = query.filter(
                models.LeadStatus.priority == models.LeadPriority.HIGH,
                or_(
                    models.LeadStatus.contact_status == models.ContactStatus.BELUM_DIHUBUNGI,
                    models.LeadStatus.contact_status.is_(None)
                )
            )
        elif filter_mode == "followup_today":
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow_start = today_start.replace(hour=23, minute=59, second=59)
            query = query.filter(
                models.LeadStatus.next_followup_at.isnot(None),
                models.LeadStatus.next_followup_at <= tomorrow_start
            )
        elif filter_mode == "no_website":
            query = query.filter(models.Business.has_website == False)  # noqa: E712
            query = query.filter(
                or_(
                    models.LeadStatus.contact_status == models.ContactStatus.BELUM_DIHUBUNGI,
                    models.LeadStatus.contact_status.is_(None)
                )
            )

    # Only include leads with valid phone numbers for WhatsApp outreach
    query = query.filter(
        models.Business.phone.isnot(None),
        models.Business.phone != ""
    )

    query = query.order_by(
        desc(models.LeadStatus.priority),
        desc(models.Business.rating_avg),
        desc(models.Business.id)
    )

    # No artificial limit — retrieve the full queue!
    return query.all()


@router.get("/outreach", response_class=HTMLResponse)
async def outreach_view(
    request: Request,
    search: Optional[str] = None,
    category: Optional[str] = None,
    crawl_run_id: Optional[str] = None,
    has_website: Optional[str] = None,
    contact_status: Optional[str] = "belum_dihubungi",
    priority: Optional[str] = None,
    filter_mode: Optional[str] = None,
    lead_ids: Optional[str] = None,
    current_index: int = 0,
    db: Session = Depends(get_db)
):
    """Render Outreach Speed-Dial Mode page with full filter bar, unlimited queue, and portfolio attachment studio."""
    user = getattr(request.state, "current_user", None)
    user_id = user.id if user else None
    # Load saved progress if no explicit index provided in query params
    if "current_index" not in request.query_params and user_id is not None:
        saved_index = _load_progress(user_id)
        if saved_index is not None:
            current_index = saved_index

    # Available categories for dropdown filter
    cat_query = db.query(models.Business.category)
    if user_id:
        cat_query = cat_query.filter(models.Business.user_id == user_id)
    available_categories = [c[0] for c in cat_query.distinct().all() if c[0]]

    # Available crawl runs for session filter
    cr_query = db.query(models.CrawlRun).filter(models.CrawlRun.total_businesses > 0)
    if user_id:
        cr_query = cr_query.filter(models.CrawlRun.user_id == user_id)
    available_crawl_runs = cr_query.order_by(models.CrawlRun.id.desc()).all()

    # Active contact status: default to 'belum_dihubungi'
    active_contact_status = contact_status if (contact_status and contact_status.strip()) else "belum_dihubungi"

    # Build queue
    queue = _build_outreach_queue(
        db,
        user_id=user_id,
        search=search,
        category=category,
        crawl_run_id=crawl_run_id,
        has_website=has_website,
        contact_status=active_contact_status,
        priority=priority,
        filter_mode=filter_mode,
        lead_ids=lead_ids
    )
    total_queue = len(queue)

    company_name, contact_person, website_url, wa_template = get_profile_data(db, user_id=user_id)
    port_query = db.query(models.PortfolioItem)
    if user_id:
        port_query = port_query.filter(models.PortfolioItem.user_id == user_id)
    portfolios = port_query.all()

    common_context = {
        "request": request,
        "active_page": "outreach",
        "total_queue": total_queue,
        "current_index": current_index,
        "search": search or "",
        "category": category or "all",
        "crawl_run_id": crawl_run_id or "all",
        "has_website": has_website or "all",
        "contact_status": active_contact_status,
        "priority": priority or "all",
        "filter_mode": filter_mode or "",
        "lead_ids": lead_ids or "",
        "available_categories": sorted(available_categories),
        "available_crawl_runs": available_crawl_runs,
        "portfolios": portfolios,
        "pitch_templates": PITCH_TEMPLATES,
        "company_name": company_name,
        "contact_person": contact_person,
        "website_url": website_url or DEFAULT_OFFICIAL_WEBSITE,
        # Ensure official website link is always included in the pitch text
        "official_website": DEFAULT_OFFICIAL_WEBSITE,
        "quick_note_chips": QUICK_NOTE_CHIPS,
    }

    if total_queue == 0:
        return templates.TemplateResponse(
            request=request,
            name="outreach.html",
            context={
                **common_context,
                "queue_empty": True,
                "business": None,
            }
        )

    # Clamp index
    current_index = max(0, min(current_index, total_queue - 1))
    current_lead = queue[current_index]

    matched_portfolio = match_portfolio_for_business(current_lead, db, user_id=user_id)

    # Build WA link
    wa_link = build_personalized_wa_link(
        current_lead.phone,
        current_lead.business_name,
        wa_template,
        portfolio=matched_portfolio,
        company_name=company_name,
        contact_person=contact_person,
        website_url=website_url or DEFAULT_OFFICIAL_WEBSITE
    )

    # Build pitch text for display
    pitch_text = wa_template
    # Append official website link if not already present
    if DEFAULT_OFFICIAL_WEBSITE not in pitch_text:
        pitch_text += f"\n{DEFAULT_OFFICIAL_WEBSITE}"
    pitch_text = pitch_text.replace("{business_name}", current_lead.business_name or "")
    pitch_text = pitch_text.replace("{portfolio_name}", matched_portfolio.title if matched_portfolio else "Website Profesional")
    pitch_text = pitch_text.replace("{portfolio_url}", matched_portfolio.demo_url if matched_portfolio else DEFAULT_OFFICIAL_WEBSITE)
    pitch_text = pitch_text.replace("{pitch_snippet}", matched_portfolio.pitch_snippet if matched_portfolio and matched_portfolio.pitch_snippet else "")
    pitch_text = pitch_text.replace("{company_name}", company_name)
    pitch_text = pitch_text.replace("{contact_person}", contact_person)
    pitch_text = pitch_text.replace("{website_url}", website_url or DEFAULT_OFFICIAL_WEBSITE)

    # Standardize phone for WA
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
            **common_context,
            "queue_empty": False,
            "current_index": current_index,
            "business": current_lead,
            "lead_status": current_lead.lead_status,
            "matched_portfolio": matched_portfolio,
            "pitch_text": pitch_text,
            "wa_link": wa_link,
            "target_phone_wa": target_phone_wa,
            "activities": activities,
            "contact_status_enum": models.ContactStatus,
        }
    )


@router.post("/outreach/{business_id}/mark-sent")
async def mark_sent_and_next(
    request: Request,
    business_id: int,
    search: Optional[str] = Form(""),
    category: Optional[str] = Form("all"),
    crawl_run_id: Optional[str] = Form("all"),
    has_website: Optional[str] = Form("all"),
    contact_status: Optional[str] = Form("belum_dihubungi"),
    priority: Optional[str] = Form("all"),
    filter_mode: Optional[str] = Form(""),
    lead_ids: Optional[str] = Form(""),
    current_index: int = Form(0),
    quick_note: Optional[str] = Form(None),
    custom_note: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Mark current lead as 'Sudah Dihubungi' (Sudah Di-WA), log activity, and advance queue.
    """
    user = getattr(request.state, "current_user", None)
    user_id = user.id if user else None
    username = user.full_name or user.username if user else "Admin"

    biz_query = db.query(models.Business).filter(models.Business.id == business_id)
    if user_id:
        biz_query = biz_query.filter(models.Business.user_id == user_id)
    business = biz_query.first()

    if business:
        now = datetime.utcnow()
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

        note_text = quick_note or custom_note
        if note_text and note_text.strip():
            if lead_status.notes:
                lead_status.notes = f"{lead_status.notes}\n[{now.strftime('%d/%m/%y %H:%M')}] {note_text.strip()}"
            else:
                lead_status.notes = f"[{now.strftime('%d/%m/%y %H:%M')}] {note_text.strip()}"

        activity = models.ActivityLog(
            business_id=business.id,
            action="wa_sent",
            detail=f"Pesan WhatsApp dikirim via Outreach Speed-Dial. {('Catatan: ' + note_text.strip()) if note_text and note_text.strip() else ''}",
            created_by=username,
            created_at=now
        )
        db.add(activity)
        db.commit()

    active_contact_status = contact_status if (contact_status and contact_status.strip()) else "belum_dihubungi"
    
    # If filtering uncontacted leads, the current lead leaves the queue, so next lead is at current_index
    if active_contact_status == "belum_dihubungi":
        next_index = current_index
    else:
        next_index = current_index + 1

    # Save progress for next session
    if user_id is not None:
        _save_progress(user_id, next_index)

    params = {
        "current_index": next_index,
        "search": search or "",
        "category": category or "all",
        "crawl_run_id": crawl_run_id or "all",
        "has_website": has_website or "all",
        "contact_status": active_contact_status,
        "priority": priority or "all",
        "filter_mode": filter_mode or "",
        "lead_ids": lead_ids or "",
    }
    encoded_params = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    return RedirectResponse(url=f"/outreach?{encoded_params}", status_code=303)


@router.post("/outreach/{business_id}/skip")
async def skip_lead(
    request: Request,
    business_id: int,
    search: Optional[str] = Form(""),
    category: Optional[str] = Form("all"),
    crawl_run_id: Optional[str] = Form("all"),
    has_website: Optional[str] = Form("all"),
    contact_status: Optional[str] = Form("belum_dihubungi"),
    priority: Optional[str] = Form("all"),
    filter_mode: Optional[str] = Form(""),
    lead_ids: Optional[str] = Form(""),
    current_index: int = Form(0),
    skip_reason: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Skip current lead and move to next lead in the queue without marking sent."""
    user = getattr(request.state, "current_user", None)
    user_id = user.id if user else None
    username = user.full_name or user.username if user else "Admin"

    if skip_reason and skip_reason.strip():
        now = datetime.utcnow()
        activity = models.ActivityLog(
            business_id=business_id,
            action="skipped",
            detail=f"Dilewati saat Outreach Mode. Alasan: {skip_reason.strip()}",
            created_by=username,
            created_at=now
        )
        db.add(activity)
        db.commit()

    active_contact_status = contact_status if (contact_status and contact_status.strip()) else "belum_dihubungi"
    next_index = current_index + 1
    # Save progress for next session
    if user_id is not None:
        _save_progress(user_id, next_index)
    params = {
        "current_index": next_index,
        "search": search or "",
        "category": category or "all",
        "crawl_run_id": crawl_run_id or "all",
        "has_website": has_website or "all",
        "contact_status": active_contact_status,
        "priority": priority or "all",
        "filter_mode": filter_mode or "",
        "lead_ids": lead_ids or "",
    }
    encoded_params = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    return RedirectResponse(url=f"/outreach?{encoded_params}", status_code=303)


@router.post("/outreach/{business_id}/quick-note", response_class=HTMLResponse)
async def add_quick_note(
    request: Request,
    business_id: int,
    note: str = Form(...),
    db: Session = Depends(get_db)
):
    """Add a quick note chip to a lead's activity log via HTMX."""
    user = getattr(request.state, "current_user", None)
    user_id = user.id if user else None
    username = user.full_name or user.username if user else "Admin"

    biz_query = db.query(models.Business).filter(models.Business.id == business_id)
    if user_id:
        biz_query = biz_query.filter(models.Business.user_id == user_id)
    business = biz_query.first()

    if not business:
        return HTMLResponse("<span class='text-xs text-rose-600'>Lead tidak ditemukan.</span>")

    now = datetime.utcnow()
    lead_status = business.lead_status
    if lead_status:
        if lead_status.notes:
            lead_status.notes = f"{lead_status.notes}\n[{now.strftime('%d/%m/%y %H:%M')}] {note.strip()}"
        else:
            lead_status.notes = f"[{now.strftime('%d/%m/%y %H:%M')}] {note.strip()}"
        lead_status.updated_at = now

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
