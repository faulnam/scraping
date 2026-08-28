"""
Leads Router: List view with interactive Leaflet map, HTMX sortable/filterable table,
detailed lead profile with follow-up tracking, and dynamic WhatsApp templates.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
import urllib.parse
from fastapi import APIRouter, Depends, Request, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, or_, and_

from app.deps import get_db
from app import models
from app.places_api.mapper import normalize_phone_number, normalize_phone_to_whatsapp

router = APIRouter(tags=["leads"])
templates = Jinja2Templates(directory="app/templates")

DEFAULT_WA_TEMPLATE = (
    "Halo {business_name}, perkenalkan saya {contact_person} dari {company_name}.\n\n"
    "Kami melihat profil bisnis Anda di Google Maps dengan reputasi yang sangat baik. "
    "{pitch_snippet}\n\n"
    "Anda bisa langsung melihat contoh portfolio/demo web kami di sini:\n"
    "👉 Demo Portofolio: {portfolio_url}\n"
    "🌐 Web Resmi Kami: {website_url}\n\n"
    "Apakah ada waktu luang untuk kami buatkan preview website khusus bagi {business_name}?"
)

PITCH_TEMPLATES = {
    "direct_demo": {
        "id": "direct_demo",
        "name": "Direct Demo Link (Rekomendasi)",
        "template": (
            "Halo {business_name}, perkenalkan saya {contact_person} dari {company_name}.\n\n"
            "Kami melihat profil bisnis Anda di Google Maps memiliki reputasi yang sangat baik. "
            "{pitch_snippet}\n\n"
            "Berikut contoh referensi website yang kami rancang khusus untuk industri Anda:\n"
            "👉 Demo Portofolio: {portfolio_url}\n"
            "🌐 Web Resmi: {website_url}\n\n"
            "Apakah boleh kami presentasikan preview singkat untuk {business_name}?"
        )
    },
    "sales_growth": {
        "id": "sales_growth",
        "name": "Fokus Solusi Omset & Kredibilitas",
        "template": (
            "Halo {business_name}, salam sukses dari tim {company_name}.\n\n"
            "Banyak calon pelanggan mencari layanan di Google. Untuk meningkatkan kredibilitas & omset {business_name}, kami sudah siapkan sistem website siap pakai.\n\n"
            "Lihat contoh sistem demonya di:\n"
            "👉 Demo Portofolio: {portfolio_url}\n"
            "🌐 Layanan & Web Resmi: {website_url}\n\n"
            "Boleh kami diskusikan penawaran singkatnya via WhatsApp?"
        )
    },
    "casual": {
        "id": "casual",
        "name": "Santai & Bersahabat",
        "template": (
            "Halo kak di {business_name}, salam dari tim {company_name} 😊\n\n"
            "Izin share referensi desain website modern yang pas banget untuk {business_name}:\n"
            "👉 Demo Portofolio: {portfolio_url}\n"
            "🌐 Web Resmi Kami: {website_url}\n\n"
            "Barangkali sedang ada rencana pembuatan website resmi, boleh kami bantu ya kak!"
        )
    }
}


def get_profile_data(db: Session):
    """Retrieve company name, contact person, website URL, and custom template from BusinessProfile."""
    profile = db.query(models.BusinessProfile).first()
    company_name = profile.company_name if profile and profile.company_name else "JuangDev Solutions"
    contact_person = profile.contact_person if profile and profile.contact_person else "Tim Konsultan Web"
    website_url = getattr(profile, "website_url", None) if profile and getattr(profile, "website_url", None) else "https://juangdev.my.id"
    wa_template = profile.default_wa_template if profile and profile.default_wa_template and profile.default_wa_template.strip() else DEFAULT_WA_TEMPLATE
    return company_name, contact_person, website_url, wa_template


def get_default_wa_template(db: Session) -> str:
    """Retrieve template from BusinessProfile or fallback to default."""
    _, _, _, wa_template = get_profile_data(db)
    return wa_template



def match_portfolio_for_business(business: models.Business, db: Session) -> Optional[models.PortfolioItem]:
    """
    Find the most relevant portfolio preset based on business category & name keyword scoring.
    """
    portfolios = db.query(models.PortfolioItem).all()
    if not portfolios:
        return None
    
    target_text = f"{business.category or ''} {business.business_name or ''}".lower()
    
    best_item = None
    best_score = 0
    default_item = None

    for p in portfolios:
        if p.is_default:
            default_item = p
        
        score = 0
        if p.category_keywords:
            keywords = [k.strip().lower() for k in p.category_keywords.split(",") if k.strip()]
            for kw in keywords:
                if kw in target_text:
                    score += 1
        
        if score > best_score:
            best_score = score
            best_item = p

    if best_item and best_score > 0:
        return best_item
    return default_item or portfolios[0]


def build_personalized_wa_link(
    phone: Optional[str], 
    business_name: str, 
    template: str, 
    portfolio: Optional[models.PortfolioItem] = None,
    company_name: str = "JuangDev Solutions",
    contact_person: str = "Tim Konsultan Web",
    website_url: str = "https://juangdev.my.id"
) -> Optional[str]:
    """Generate wa.me link with URL-encoded personalized message & targeted portfolio demo URL and official website."""
    if not phone:
        return None
    
    # Standardize to 628... digits
    raw_digits = "".join([c for c in phone if c.isdigit()])
    if raw_digits.startswith("08"):
        phone_digits = "62" + raw_digits[1:]
    elif raw_digits.startswith("8"):
        phone_digits = "62" + raw_digits
    elif raw_digits.startswith("62"):
        phone_digits = raw_digits
    else:
        return None

    # Only Indonesian mobile numbers (starting with 628) can receive WhatsApp
    if not phone_digits.startswith("628") or len(phone_digits) < 10:
        return None

    # Replace placeholders
    safe_name = business_name.strip() if business_name else "Bapak/Ibu"
    portfolio_title = portfolio.title if portfolio else "Website Profesional"
    portfolio_url = portfolio.demo_url if portfolio else "https://juangdev.my.id"
    pitch_snippet = portfolio.pitch_snippet if portfolio and portfolio.pitch_snippet else ""

    message = template.replace("{business_name}", safe_name)
    message = message.replace("{portfolio_name}", portfolio_title)
    message = message.replace("{portfolio_url}", portfolio_url)
    message = message.replace("{pitch_snippet}", pitch_snippet)
    message = message.replace("{company_name}", company_name)
    message = message.replace("{contact_person}", contact_person)
    message = message.replace("{website_url}", website_url)

    encoded_text = urllib.parse.quote(message)
    return f"https://wa.me/{phone_digits}?text={encoded_text}"



def _get_filtered_leads_query(
    db: Session,
    crawl_run_id: Optional[int] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    has_website: Optional[str] = None,
    min_rating: Optional[float] = None,
    contact_status: Optional[str] = None,
    priority: Optional[str] = None,
    sort_by: str = "date",
    sort_order: str = "desc"
):
    """Construct filtered and sorted SQLAlchemy query for businesses joined with lead_status."""
    query = db.query(models.Business).outerjoin(models.LeadStatus, models.Business.id == models.LeadStatus.business_id)

    # Crawl Run Session filter
    if crawl_run_id:
        query = query.filter(models.Business.crawl_run_id == crawl_run_id)

    # Search keyword filter (name, address, phone)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                models.Business.business_name.ilike(term),
                models.Business.address.ilike(term),
                models.Business.phone.ilike(term),
                models.Business.category.ilike(term)
            )
        )

    # Category filter (supports exact category or flexible partial keyword fallback)
    if category and category.strip() and category.strip() != "all":
        cat_term = category.strip()
        query = query.filter(
            or_(
                models.Business.category == cat_term,
                models.Business.category.ilike(f"%{cat_term}%"),
                models.Business.location_query.ilike(f"%{cat_term}%")
            )
        )

    # Website status filter
    if has_website == "true":
        query = query.filter(models.Business.has_website == True)  # noqa: E712
    elif has_website == "false":
        query = query.filter(models.Business.has_website == False)  # noqa: E712

    # Minimum rating filter
    if min_rating and min_rating > 0:
        query = query.filter(models.Business.rating_avg >= min_rating)

    # Contact status funnel filter
    if contact_status and contact_status.strip() and contact_status.strip() != "all":
        query = query.filter(models.LeadStatus.contact_status == contact_status.strip())

    # Priority filter
    if priority and priority.strip() and priority.strip() != "all":
        query = query.filter(models.LeadStatus.priority == priority.strip())

    # Sorting
    order_func = desc if sort_order.lower() == "desc" else asc
    if sort_by == "name":
        query = query.order_by(order_func(models.Business.business_name))
    elif sort_by == "rating":
        query = query.order_by(order_func(models.Business.rating_avg))
    elif sort_by == "reviews":
        query = query.order_by(order_func(models.Business.total_review))
    elif sort_by == "priority":
        query = query.order_by(order_func(models.LeadStatus.priority))
    elif sort_by == "status":
        query = query.order_by(order_func(models.LeadStatus.contact_status))
    else:  # 'date' default
        query = query.order_by(order_func(models.Business.scraped_at), order_func(models.Business.id))

    return query


@router.get("/leads", response_class=HTMLResponse)
async def leads_list_view(
    request: Request,
    crawl_run_id: Optional[int] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    has_website: Optional[str] = None,
    min_rating: Optional[float] = None,
    contact_status: Optional[str] = None,
    priority: Optional[str] = None,
    sort_by: str = "date",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """
    Render the Leads Management page with interactive Leaflet map & dynamic table.
    Supports partial rendering for HTMX requests and specific CrawlRun session filtering.
    """
    query = _get_filtered_leads_query(
        db,
        crawl_run_id=crawl_run_id,
        search=search,
        category=category,
        has_website=has_website,
        min_rating=min_rating,
        contact_status=contact_status,
        priority=priority,
        sort_by=sort_by,
        sort_order=sort_order
    )

    total_leads = query.count()
    total_pages = max(1, (total_leads + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * page_size

    businesses = query.offset(offset).limit(page_size).all()
    company_name, contact_person, website_url, wa_template = get_profile_data(db)

    # Attach dynamic personalized WA link and matched portfolio to each business record
    for b in businesses:
        matched_p = match_portfolio_for_business(b, db)
        b.matched_portfolio = matched_p
        b.dynamic_wa_link = build_personalized_wa_link(
            b.phone, 
            b.business_name, 
            wa_template, 
            portfolio=matched_p,
            company_name=company_name,
            contact_person=contact_person,
            website_url=website_url
        )

    # Prepare map markers for businesses with coordinates
    map_markers: List[Dict[str, Any]] = []
    for b in businesses:
        if b.latitude and b.longitude:
            map_markers.append({
                "id": b.id,
                "name": b.business_name,
                "lat": float(b.latitude),
                "lng": float(b.longitude),
                "has_website": bool(b.has_website),
                "rating": float(b.rating_avg) if b.rating_avg is not None else 0.0,
                "reviews": b.total_review,
                "category": b.category or "Usaha",
                "address": b.address or "",
                "phone": b.phone or "-",
                "wa_url": b.dynamic_wa_link,
                "portfolio_name": b.matched_portfolio.title if b.matched_portfolio else "Website Profesional",
                "portfolio_url": b.matched_portfolio.demo_url if b.matched_portfolio else "https://juangdev.my.id",
                "priority": b.lead_status.priority.value if b.lead_status else "low",
                "status": b.lead_status.contact_status.value if b.lead_status else "belum_dihubungi"
            })

    # Available categories for dropdown filter
    available_categories = [c[0] for c in db.query(models.Business.category).distinct().all() if c[0]]

    active_crawl_run = db.query(models.CrawlRun).filter(models.CrawlRun.id == crawl_run_id).first() if crawl_run_id else None

    context = {
        "request": request,
        "active_page": "leads",
        "businesses": businesses,
        "total_leads": total_leads,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size,
        "crawl_run_id": crawl_run_id or "",
        "active_crawl_run": active_crawl_run,
        "search": search or "",
        "category": category or "all",
        "has_website": has_website or "all",
        "min_rating": min_rating or 0.0,
        "contact_status": contact_status or "all",
        "priority": priority or "all",
        "sort_by": sort_by,
        "sort_order": sort_order,
        "available_categories": sorted(available_categories),
        "map_markers_json": map_markers,
        "contact_status_enum": models.ContactStatus,
        "lead_priority_enum": models.LeadPriority,
    }

    # If requested via HTMX for partial table reload
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="partials/leads_table.html",
            context=context
        )

    return templates.TemplateResponse(
        request=request,
        name="leads_list.html",
        context=context
    )


@router.get("/api/leads/table", response_class=HTMLResponse)
async def leads_table_partial(
    request: Request,
    crawl_run_id: Optional[int] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    has_website: Optional[str] = None,
    min_rating: Optional[float] = None,
    contact_status: Optional[str] = None,
    priority: Optional[str] = None,
    sort_by: str = "date",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """Explicit endpoint for HTMX partial table updates."""
    return await leads_list_view(
        request=request,
        crawl_run_id=crawl_run_id,
        search=search,
        category=category,
        has_website=has_website,
        min_rating=min_rating,
        contact_status=contact_status,
        priority=priority,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
        db=db
    )


@router.get("/leads/{business_id}", response_class=HTMLResponse)
async def lead_detail_view(
    request: Request,
    business_id: int,
    db: Session = Depends(get_db)
):
    """
    Render full detailed view for a single lead business.
    Includes Places API data, status history, portfolio demo selector, and dynamic WhatsApp studio.
    """
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Lead tidak ditemukan")

    company_name, contact_person, website_url, wa_template = get_profile_data(db)
    portfolios = db.query(models.PortfolioItem).all()
    matched_portfolio = match_portfolio_for_business(business, db)

    # Initial personalized WhatsApp link & text
    personalized_wa_link = build_personalized_wa_link(
        business.phone, 
        business.business_name, 
        wa_template,
        portfolio=matched_portfolio,
        company_name=company_name,
        contact_person=contact_person,
        website_url=website_url
    )
    
    # Calculate initial customized message text
    initial_pitch_text = wa_template
    initial_pitch_text = initial_pitch_text.replace("{business_name}", business.business_name)
    initial_pitch_text = initial_pitch_text.replace("{portfolio_name}", matched_portfolio.title if matched_portfolio else "Website Profesional")
    initial_pitch_text = initial_pitch_text.replace("{portfolio_url}", matched_portfolio.demo_url if matched_portfolio else "https://juangdev.my.id")
    initial_pitch_text = initial_pitch_text.replace("{pitch_snippet}", matched_portfolio.pitch_snippet if matched_portfolio and matched_portfolio.pitch_snippet else "")
    initial_pitch_text = initial_pitch_text.replace("{company_name}", company_name)
    initial_pitch_text = initial_pitch_text.replace("{contact_person}", contact_person)
    initial_pitch_text = initial_pitch_text.replace("{website_url}", website_url)

    # Parse opening hours list if formatted as string
    opening_hours_list = []
    if business.opening_hours:
        opening_hours_list = [h.strip() for h in business.opening_hours.split(";") if h.strip()]

    # Standardize phone number for direct WA JS generation
    clean_digits = "".join([c for c in (business.phone or "") if c.isdigit()])
    if clean_digits.startswith("08"):
        target_phone_wa = "62" + clean_digits[1:]
    elif clean_digits.startswith("8"):
        target_phone_wa = "62" + clean_digits
    elif clean_digits.startswith("62"):
        target_phone_wa = clean_digits
    else:
        target_phone_wa = ""

    return templates.TemplateResponse(
        request=request,
        name="lead_detail.html",
        context={
            "request": request,
            "active_page": "leads",
            "business": business,
            "lead_status": business.lead_status,
            "portfolios": portfolios,
            "matched_portfolio": matched_portfolio,
            "pitch_templates": PITCH_TEMPLATES,
            "company_name": company_name,
            "contact_person": contact_person,
            "website_url": website_url,
            "initial_pitch_text": initial_pitch_text,
            "personalized_wa_link": personalized_wa_link,
            "target_phone_wa": target_phone_wa,
            "opening_hours_list": opening_hours_list,
            "contact_status_enum": models.ContactStatus,
            "lead_priority_enum": models.LeadPriority,
        }
    )



@router.post("/leads/{business_id}/status", response_class=HTMLResponse)
async def update_lead_status(
    request: Request,
    business_id: int,
    contact_status: models.ContactStatus = Form(...),
    notes: Optional[str] = Form(None),
    assigned_to: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Update contact status, notes, and sales assignee for a lead via HTMX.
    """
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Lead tidak ditemukan")

    lead_status = business.lead_status
    now = datetime.utcnow()

    if not lead_status:
        lead_status = models.LeadStatus(
            business_id=business.id,
            contact_status=contact_status,
            priority=models.LeadPriority.LOW,
            notes=notes,
            assigned_to=assigned_to,
            updated_at=now
        )
        db.add(lead_status)
    else:
        lead_status.contact_status = contact_status
        lead_status.notes = notes
        lead_status.assigned_to = assigned_to
        lead_status.updated_at = now

    # Update last contacted time if transitioning away from 'belum_dihubungi'
    if contact_status != models.ContactStatus.BELUM_DIHUBUNGI:
        lead_status.last_contacted_at = now

    db.commit()
    db.refresh(lead_status)

    response_html = f"""
    <div class="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center justify-between animate-fade-in mb-3">
      <div class="flex items-center space-x-2">
        <svg class="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
        <span>Status kontak berhasil diperbarui menjadi: <strong>{contact_status.value.replace('_', ' ').title()}</strong></span>
      </div>
      <button type="button" onclick="this.parentElement.remove()" class="text-emerald-600 hover:text-emerald-900 text-xs">✕</button>
    </div>
    """
    return HTMLResponse(content=response_html)


@router.post("/leads/{business_id}/quick-status", response_class=HTMLResponse)
async def quick_update_status(
    request: Request,
    business_id: int,
    contact_status: models.ContactStatus = Form(...),
    db: Session = Depends(get_db)
):
    """
    Quick status updater called directly from table dropdown via HTMX.
    """
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Lead tidak ditemukan")

    lead_status = business.lead_status
    now = datetime.utcnow()

    if not lead_status:
        lead_status = models.LeadStatus(
            business_id=business.id,
            contact_status=contact_status,
            priority=models.LeadPriority.LOW,
            updated_at=now
        )
        db.add(lead_status)
    else:
        lead_status.contact_status = contact_status
        lead_status.updated_at = now

    if contact_status != models.ContactStatus.BELUM_DIHUBUNGI:
        lead_status.last_contacted_at = now

    db.commit()
    db.refresh(lead_status)

    # Styling helper for status badge
    badge_colors = {
        models.ContactStatus.BELUM_DIHUBUNGI: "bg-slate-100 text-slate-700 border-slate-200",
        models.ContactStatus.SUDAH_DIHUBUNGI: "bg-blue-50 text-blue-700 border-blue-200",
        models.ContactStatus.FOLLOW_UP: "bg-amber-50 text-amber-800 border-amber-200",
        models.ContactStatus.DEAL: "bg-emerald-50 text-emerald-800 border-emerald-200",
        models.ContactStatus.TIDAK_TERTARIK: "bg-rose-50 text-rose-700 border-rose-200",
        models.ContactStatus.TIDAK_RELEVAN: "bg-gray-100 text-gray-500 border-gray-200"
    }

    badge_class = badge_colors.get(contact_status, "bg-slate-100 text-slate-700 border-slate-200")
    formatted_date = lead_status.last_contacted_at.strftime('%d/%m/%y %H:%M') if lead_status.last_contacted_at else ''

    status_options = ""
    for st in models.ContactStatus:
        sel = "selected" if st == contact_status else ""
        label = st.value.replace("_", " ").title()
        status_options += f'<option value="{st.value}" {sel}>{label}</option>'

    cell_html = f"""
    <div class="space-y-1.5 quick-status-wrapper" data-status-container="true">
      <select name="contact_status"
              hx-post="/leads/{business_id}/quick-status"
              hx-target="closest [data-status-container]"
              hx-swap="outerHTML"
              class="w-full text-xs sm:text-[11px] font-semibold py-1.5 px-2.5 rounded-lg border border-slate-300 bg-white text-slate-800 focus:ring-2 focus:ring-slate-900 focus:outline-none cursor-pointer">
        {status_options}
      </select>
      <div class="flex items-center justify-between text-[11px] sm:text-[10px] text-slate-500">
        <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] sm:text-[9px] font-semibold border {badge_class}">
          {contact_status.value.replace('_', ' ').title()}
        </span>
        {f'<span class="text-slate-400 font-mono text-[10px]">{formatted_date}</span>' if formatted_date else ''}
      </div>
    </div>
    """
    return HTMLResponse(content=cell_html)

