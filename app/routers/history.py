"""
History Router: Crawling session audit logs, API usage & cost monitoring.
Isolated per user: Each user only sees their own crawl history.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.deps import get_db
from app import models

router = APIRouter(tags=["history"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/history", response_class=HTMLResponse)
async def history_view(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """
    Render crawling history log table with API requests monitoring, isolated by user_id.
    """
    user = getattr(request.state, "current_user", None)
    user_id = user.id if user else None

    base_query = db.query(models.CrawlRun)
    if user_id:
        base_query = base_query.filter(models.CrawlRun.user_id == user_id)
    base_query = base_query.order_by(desc(models.CrawlRun.started_at), desc(models.CrawlRun.id))
    
    total_runs = base_query.count()
    total_pages = max(1, (total_runs + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * page_size

    runs = base_query.offset(offset).limit(page_size).all()

    # Aggregate metric stats isolated by user_id
    api_query = db.query(func.sum(models.CrawlRun.api_requests_used))
    leads_query = db.query(func.sum(models.CrawlRun.total_businesses))
    succ_query = db.query(func.count(models.CrawlRun.id)).filter(models.CrawlRun.status == "success")

    if user_id:
        api_query = api_query.filter(models.CrawlRun.user_id == user_id)
        leads_query = leads_query.filter(models.CrawlRun.user_id == user_id)
        succ_query = succ_query.filter(models.CrawlRun.user_id == user_id)

    total_api_requests = api_query.scalar() or 0
    total_scraped_leads = leads_query.scalar() or 0
    avg_leads_per_run = (total_scraped_leads / total_runs) if total_runs > 0 else 0.0
    success_runs_count = succ_query.scalar() or 0
    success_rate = (success_runs_count / total_runs * 100) if total_runs > 0 else 100.0

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "active_page": "history",
            "runs": runs,
            "total_runs": total_runs,
            "total_pages": total_pages,
            "current_page": page,
            "total_api_requests": int(total_api_requests),
            "total_scraped_leads": int(total_scraped_leads),
            "avg_leads_per_run": round(avg_leads_per_run, 1),
            "success_rate": round(success_rate, 1),
        }
    )
