"""
History Router: Crawling session audit logs, API usage & cost monitoring.
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
    Render crawling history log table with API requests monitoring.
    """
    base_query = db.query(models.CrawlRun).order_by(desc(models.CrawlRun.started_at), desc(models.CrawlRun.id))
    
    total_runs = base_query.count()
    total_pages = max(1, (total_runs + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * page_size

    runs = base_query.offset(offset).limit(page_size).all()

    # Aggregate metric stats
    total_api_requests = db.query(func.sum(models.CrawlRun.api_requests_used)).scalar() or 0
    total_scraped_leads = db.query(func.sum(models.CrawlRun.total_businesses)).scalar() or 0
    avg_leads_per_run = (total_scraped_leads / total_runs) if total_runs > 0 else 0.0
    success_runs_count = db.query(func.count(models.CrawlRun.id)).filter(models.CrawlRun.status == "success").scalar() or 0
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
