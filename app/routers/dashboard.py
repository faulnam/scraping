"""
Dashboard Router: Aggregation overview, live metrics, filter controllers,
crawl trigger endpoint via HTMX, and Chart.js dynamic data feed.
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Request, Form, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_, or_

from app.deps import get_db, check_demo_crawl_token, get_demo_token_info
from app import models
from app.ingest.pipeline import run_ingest_pipeline

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


def _apply_business_filters(
    query,
    province: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    time_range: Optional[str] = None
):
    """Apply standard filter conditions to a Business query."""
    if province and province.strip() and province.strip() != "all":
        query = query.filter(models.Business.province == province.strip())
    if city and city.strip() and city.strip() != "all":
        query = query.filter(models.Business.city == city.strip())
    if category and category.strip() and category.strip() != "all":
        query = query.filter(models.Business.category == category.strip())

    now = datetime.utcnow()
    if time_range == "7d":
        query = query.filter(models.Business.scraped_at >= now - timedelta(days=7))
    elif time_range == "30d":
        query = query.filter(models.Business.scraped_at >= now - timedelta(days=30))
    elif time_range == "90d":
        query = query.filter(models.Business.scraped_at >= now - timedelta(days=90))

    return query


def _get_dashboard_stats(
    db: Session,
    province: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    time_range: Optional[str] = None
) -> Dict[str, Any]:
    """Calculate all dynamic metrics and dropdown items from MySQL."""
    base_query = db.query(models.Business)
    filtered_query = _apply_business_filters(base_query, province, city, category, time_range)

    # 1. Total Businesses
    total_businesses = filtered_query.count()

    # 2. Without Website & Percentage
    without_website = filtered_query.filter(models.Business.has_website == False).count()  # noqa: E712
    without_website_pct = (without_website / total_businesses * 100) if total_businesses > 0 else 0.0

    # 3. Average Rating & Total Reviews
    avg_rating_val = filtered_query.with_entities(func.avg(models.Business.rating_avg)).scalar()
    avg_rating = f"{float(avg_rating_val):.1f}" if avg_rating_val is not None else "0.0"
    total_reviews_sum = filtered_query.with_entities(func.sum(models.Business.total_review)).scalar() or 0

    # 4. Contacted Leads & Pipeline breakdown
    lead_query = db.query(models.LeadStatus).join(models.Business, models.LeadStatus.business_id == models.Business.id)
    lead_query = _apply_business_filters(lead_query, province, city, category, time_range)

    contacted_count = lead_query.filter(models.LeadStatus.contact_status != models.ContactStatus.BELUM_DIHUBUNGI).count()
    follow_up_count = lead_query.filter(models.LeadStatus.contact_status == models.ContactStatus.FOLLOW_UP).count()
    deal_count = lead_query.filter(models.LeadStatus.contact_status == models.ContactStatus.DEAL).count()

    # Total crawl runs
    total_crawl_runs = db.query(func.count(models.CrawlRun.id)).scalar() or 0

    # Dropdown choices from DB
    available_provinces = [p[0] for p in db.query(models.Business.province).distinct().all() if p[0]]
    available_cities = [c[0] for c in db.query(models.Business.city).distinct().all() if c[0]]
    available_categories = [cat[0] for cat in db.query(models.Business.category).distinct().all() if cat[0]]

    # Ensure defaults if DB is fresh
    if "Jawa Barat" not in available_provinces:
        available_provinces.append("Jawa Barat")
    if "Kota Bandung" not in available_cities:
        available_cities.append("Kota Bandung")

    return {
        "total_businesses": total_businesses,
        "without_website": without_website,
        "without_website_pct": round(without_website_pct, 1),
        "avg_rating": avg_rating,
        "total_reviews_sum": int(total_reviews_sum),
        "contacted_count": contacted_count,
        "follow_up_count": follow_up_count,
        "deal_count": deal_count,
        "total_crawl_runs": total_crawl_runs,
        "available_provinces": sorted(available_provinces),
        "available_cities": sorted(available_cities),
        "available_categories": sorted(available_categories),
        "active_province": province or "all",
        "active_city": city or "all",
        "active_category": category or "all",
        "active_time_range": time_range or "all",
    }


def _get_agenda_stats(db: Session) -> Dict[str, int]:
    """Calculate follow-up agenda counts for the dashboard widget."""
    now = datetime.utcnow()
    today_end = now.replace(hour=23, minute=59, second=59)

    # Overdue + due today follow-ups
    followup_due_count = db.query(models.LeadStatus).filter(
        models.LeadStatus.next_followup_at.isnot(None),
        models.LeadStatus.next_followup_at <= today_end,
        models.LeadStatus.contact_status.notin_([
            models.ContactStatus.DEAL,
            models.ContactStatus.TIDAK_TERTARIK,
            models.ContactStatus.TIDAK_RELEVAN
        ])
    ).count()

    # New HIGH priority leads ready for first outreach
    new_high_count = db.query(models.LeadStatus).filter(
        models.LeadStatus.priority == models.LeadPriority.HIGH,
        models.LeadStatus.contact_status == models.ContactStatus.BELUM_DIHUBUNGI
    ).count()

    return {
        "followup_due_count": followup_due_count,
        "new_high_count": new_high_count,
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    province: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    time_range: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Render the main business intelligence dashboard overview."""
    stats = _get_dashboard_stats(db, province=province, city=city, category=category, time_range=time_range)
    agenda = _get_agenda_stats(db)

    # Get demo token info for current user
    user = getattr(request.state, "current_user", None)
    token_info = get_demo_token_info(user, db) if user else {"is_demo": False}

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "active_page": "dashboard",
            "token_info": token_info,
            **stats,
            **agenda
        }
    )


@router.get("/api/dashboard/metrics", response_class=HTMLResponse)
async def dashboard_metrics_partial(
    request: Request,
    province: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    time_range: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Partial HTML response for the 4 metric cards and header (used by HTMX filter/refresh)."""
    stats = _get_dashboard_stats(db, province=province, city=city, category=category, time_range=time_range)
    return templates.TemplateResponse(
        request=request,
        name="partials/metric_card.html",
        context=stats
    )


import time
import asyncio

_last_crawl_timestamp = 0.0
_crawl_lock = asyncio.Lock()


@router.post("/crawl", response_class=HTMLResponse)
async def trigger_crawl(
    request: Request,
    category_query: str = Form(...),
    province: Optional[str] = Form("Jawa Barat"),
    city: Optional[str] = Form("Kota Bandung"),
    crawl_mode: Optional[str] = Form("unlimited"),
    db: Session = Depends(get_db)
):
    """
    Trigger Places API crawling pipeline via HTMX POST.
    Protected with rate-limiting / debounce to avoid accidental spam.
    Admin Demo users are limited to 3 crawls per 24-hour window.
    """
    global _last_crawl_timestamp

    # Check demo token first
    user = getattr(request.state, "current_user", None)
    if user:
        token_result = check_demo_crawl_token(user, db)
        if not token_result["allowed"]:
            limit_html = f"""
            <div class="p-3.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs font-semibold flex items-center justify-between shadow-sm animate-fade-in">
              <div class="flex items-center space-x-2">
                <svg class="w-4 h-4 text-amber-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"></path></svg>
                <span>{token_result['message']}</span>
              </div>
              <button type="button" onclick="this.parentElement.remove()" class="text-amber-600 hover:text-amber-950 text-xs font-bold">&#x2715;</button>
            </div>
            """
            return HTMLResponse(content=limit_html, status_code=429)

    now_ts = time.time()
    # Rate limit: minimum 2 seconds cooldown between requests
    if now_ts - _last_crawl_timestamp < 2.0 or _crawl_lock.locked():
        cooldown_html = """
        <div class="p-3.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs font-semibold flex items-center justify-between shadow-sm animate-fade-in">
          <div class="flex items-center space-x-2">
            <svg class="w-4 h-4 text-amber-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            <span>Sesi crawling sedang berjalan atau baru saja selesai. Harap tunggu beberapa saat sebelum memulai crawl baru.</span>
          </div>
          <button type="button" onclick="this.parentElement.remove()" class="text-amber-600 hover:text-amber-950 text-xs font-bold">&#x2715;</button>
        </div>
        """
        return HTMLResponse(content=cooldown_html, status_code=429)

    max_results = int(crawl_mode) if crawl_mode and crawl_mode.isdigit() else None

    async with _crawl_lock:
        _last_crawl_timestamp = time.time()
        location_query = f"{city}, {province}".strip(", ")
        try:
            crawl_run = await run_ingest_pipeline(
                category_query=category_query,
                location_query=location_query,
                province=province,
                city=city,
                max_results=max_results,
                db=db
            )

            mode_label = "Semua Listing Hingga Habis" if not max_results else f"Maksimal {max_results} Leads"
            response_html = f"""
            <div class="p-4 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm flex items-start justify-between shadow-sm animate-fade-in">
              <div class="flex items-center space-x-3">
                <svg class="w-5 h-5 text-emerald-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                <div>
                  <p class="font-bold text-emerald-900">Crawling Selesai Berhasil</p>
                  <p class="text-xs text-emerald-700 mt-0.5">
                    Berhasil memproses <strong>{crawl_run.total_businesses} usaha</strong> untuk kategori '<strong>{category_query}</strong>' di <strong>{location_query}</strong> (Mode: {mode_label}).
                    Total request API terpakai: <strong>{crawl_run.api_requests_used} request</strong> (Sesi #{crawl_run.id}).
                  </p>
                </div>
              </div>
              <button type="button" onclick="this.parentElement.remove()" class="text-emerald-500 hover:text-emerald-800 text-xs font-semibold px-2 py-1">&#x2715;</button>
            </div>
            """
            response = HTMLResponse(content=response_html)
            response.headers["HX-Trigger"] = "refreshDashboard"
            return response


        except Exception as e:
            error_html = f"""
            <div class="p-4 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-sm flex items-start justify-between shadow-sm animate-fade-in">
              <div class="flex items-center space-x-3">
                <svg class="w-5 h-5 text-rose-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"></path></svg>
                <div>
                  <p class="font-bold text-rose-900">Proses Crawling Gagal</p>
                  <p class="text-xs text-rose-700 mt-0.5">{str(e)}</p>
                </div>
              </div>
              <button type="button" onclick="this.parentElement.remove()" class="text-rose-500 hover:text-rose-800 text-xs font-semibold px-2 py-1">&#x2715;</button>
            </div>
            """
            return HTMLResponse(content=error_html, status_code=500)


@router.get("/api/dashboard/charts", response_class=JSONResponse)
async def dashboard_charts(
    province: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    time_range: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Return dynamic JSON data queried from MySQL for Chart.js:
    1. Category Distribution (Bar Chart)
    2. Website Status vs. Rating Distribution (Stacked/Grouped Bar Chart)
    """
    base_query = db.query(models.Business)
    filtered_query = _apply_business_filters(base_query, province, city, category, time_range)

    # 1. Category Distribution
    cat_query = db.query(
        models.Business.category,
        func.count(models.Business.id).label("count")
    )
    cat_query = _apply_business_filters(cat_query, province, city, category, time_range)
    cat_rows = cat_query.group_by(models.Business.category).order_by(func.count(models.Business.id).desc()).limit(8).all()

    category_labels = [row[0] if row[0] else "Lainnya" for row in cat_rows]
    category_counts = [row[1] for row in cat_rows]

    # 2. Status Website vs Rating Brackets
    # Brackets: < 4.0, 4.0 - 4.5, 4.6 - 5.0
    bracket_low_no_web = filtered_query.filter(and_(models.Business.rating_avg < 4.0, models.Business.has_website == False)).count()  # noqa: E712
    bracket_low_has_web = filtered_query.filter(and_(models.Business.rating_avg < 4.0, models.Business.has_website == True)).count()   # noqa: E712

    bracket_mid_no_web = filtered_query.filter(and_(models.Business.rating_avg >= 4.0, models.Business.rating_avg <= 4.5, models.Business.has_website == False)).count()  # noqa: E712
    bracket_mid_has_web = filtered_query.filter(and_(models.Business.rating_avg >= 4.0, models.Business.rating_avg <= 4.5, models.Business.has_website == True)).count()   # noqa: E712

    bracket_high_no_web = filtered_query.filter(and_(models.Business.rating_avg > 4.5, models.Business.has_website == False)).count()  # noqa: E712
    bracket_high_has_web = filtered_query.filter(and_(models.Business.rating_avg > 4.5, models.Business.has_website == True)).count()   # noqa: E712

    rating_labels = ["Rating < 4.0", "Rating 4.0 - 4.5", "Rating 4.6 - 5.0 (Prioritas)"]
    without_web_data = [bracket_low_no_web, bracket_mid_no_web, bracket_high_no_web]
    with_web_data = [bracket_low_has_web, bracket_mid_has_web, bracket_high_has_web]

    return {
        "categories": {
            "labels": category_labels,
            "counts": category_counts
        },
        "website_vs_rating": {
            "labels": rating_labels,
            "without_website": without_web_data,
            "with_website": with_web_data
        }
    }
