"""
Contacted Router: Pembukuan Kontak & Outreach Ledger.
Menampilkan rekapitulasi data usaha yang telah dihubungi,
lengkap dengan filter kategori, status follow-up, catatan pembukuan,
serta fitur export CSV dan update status cepat.
Data diisolasi per akun user (user_id).
"""
from datetime import datetime, timedelta
import io
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Request, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, or_, and_, distinct
import pandas as pd

from app.deps import get_db
from app import models
from app.places_api.mapper import normalize_phone_to_whatsapp

router = APIRouter(tags=["contacted"])
templates = Jinja2Templates(directory="app/templates")


def _get_contacted_query(
    db: Session,
    user_id: Optional[int] = None,
    category: Optional[str] = None,
    contact_status: Optional[str] = None,
    search: Optional[str] = None,
    date_range: Optional[str] = None,
    sort_by: str = "last_contacted",
    sort_order: str = "desc"
):
    """
    Query utama pembukuan: Hanya mengambil bisnis yang SUDAH dihubungi
    (contact_status != 'belum_dihubungi' ATAU last_contacted_at is not None),
    diisolasi per user_id.
    """
    query = db.query(models.Business).join(
        models.LeadStatus, models.Business.id == models.LeadStatus.business_id
    )

    if user_id:
        query = query.filter(models.Business.user_id == user_id)

    # Kriteria usaha yang sudah dihubungi
    query = query.filter(
        or_(
            models.LeadStatus.contact_status != models.ContactStatus.BELUM_DIHUBUNGI,
            models.LeadStatus.last_contacted_at.isnot(None)
        )
    )

    # Filter Kategori Usaha
    if category and category.strip() and category != "all":
        query = query.filter(models.Business.category == category.strip())

    # Filter Status Kontak
    if contact_status and contact_status.strip() and contact_status != "all":
        query = query.filter(models.LeadStatus.contact_status == contact_status.strip())

    # Filter Pencarian Bebas (Nama, Telepon, Kota, Catatan)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                models.Business.business_name.ilike(term),
                models.Business.phone.ilike(term),
                models.Business.city.ilike(term),
                models.Business.category.ilike(term),
                models.LeadStatus.notes.ilike(term)
            )
        )

    # Filter Rentang Waktu Terakhir Dihubungi
    if date_range:
        now = datetime.utcnow()
        if date_range == "today":
            start_of_day = datetime(now.year, now.month, now.day)
            query = query.filter(models.LeadStatus.last_contacted_at >= start_of_day)
        elif date_range == "7d":
            seven_days_ago = now - timedelta(days=7)
            query = query.filter(models.LeadStatus.last_contacted_at >= seven_days_ago)
        elif date_range == "30d":
            thirty_days_ago = now - timedelta(days=30)
            query = query.filter(models.LeadStatus.last_contacted_at >= thirty_days_ago)

    # Pengurutan Data
    if sort_by == "name":
        col = models.Business.business_name
    elif sort_by == "category":
        col = models.Business.category
    elif sort_by == "updated_at":
        col = models.LeadStatus.updated_at
    else:  # default last_contacted
        col = models.LeadStatus.last_contacted_at

    if sort_order == "asc":
        query = query.order_by(asc(col), desc(models.Business.id))
    else:
        query = query.order_by(desc(col), desc(models.Business.id))

    return query


def _get_contacted_stats(db: Session, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Hitung agregat KPI pembukuan kontak (terhubung, deal, follow-up, conversion rate)."""
    base_query = db.query(models.LeadStatus).join(
        models.Business, models.Business.id == models.LeadStatus.business_id
    )
    if user_id:
        base_query = base_query.filter(models.Business.user_id == user_id)

    base_query = base_query.filter(
        or_(
            models.LeadStatus.contact_status != models.ContactStatus.BELUM_DIHUBUNGI,
            models.LeadStatus.last_contacted_at.isnot(None)
        )
    )

    total_contacted = base_query.count()
    sudah_wa_count = base_query.filter(models.LeadStatus.contact_status == models.ContactStatus.SUDAH_DIHUBUNGI).count()
    follow_up_count = base_query.filter(models.LeadStatus.contact_status == models.ContactStatus.FOLLOW_UP).count()
    deal_count = base_query.filter(models.LeadStatus.contact_status == models.ContactStatus.DEAL).count()
    tidak_tertarik_count = base_query.filter(models.LeadStatus.contact_status == models.ContactStatus.TIDAK_TERTARIK).count()
    
    deal_rate = round((deal_count / total_contacted * 100), 1) if total_contacted > 0 else 0.0

    return {
        "total_contacted": total_contacted,
        "sudah_wa_count": sudah_wa_count,
        "follow_up_count": follow_up_count,
        "deal_count": deal_count,
        "tidak_tertarik_count": tidak_tertarik_count,
        "deal_rate": deal_rate,
    }


def _get_distinct_categories(db: Session, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Ambil daftar kategori unik dari usaha yang sudah dihubungi untuk dropdown filter."""
    cat_query = db.query(
        models.Business.category,
        func.count(models.Business.id).label("count")
    ).join(
        models.LeadStatus, models.Business.id == models.LeadStatus.business_id
    )

    if user_id:
        cat_query = cat_query.filter(models.Business.user_id == user_id)

    cat_query = cat_query.filter(
        or_(
            models.LeadStatus.contact_status != models.ContactStatus.BELUM_DIHUBUNGI,
            models.LeadStatus.last_contacted_at.isnot(None)
        )
    ).filter(
        models.Business.category.isnot(None),
        models.Business.category != ""
    ).group_by(models.Business.category).order_by(models.Business.category)

    results = []
    for row in cat_query.all():
        if row.category and row.category.strip():
            results.append({"name": row.category.strip(), "count": row.count})
    return results


@router.get("/contacted", response_class=HTMLResponse)
@router.get("/pembukuan", response_class=HTMLResponse)
async def contacted_view(
    request: Request,
    category: Optional[str] = None,
    contact_status: Optional[str] = None,
    search: Optional[str] = None,
    date_range: Optional[str] = None,
    sort_by: str = "last_contacted",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db)
):
    """
    Halaman Pembukuan Kontak: Pure data usaha yang telah dihubungi
    dilengkapi filter kategori, status, tanggal, dan metrik konversi.
    """
    user = getattr(request.state, "current_user", None)
    user_id = user.id if user else None

    # Query data terfilter
    query = _get_contacted_query(
        db=db,
        user_id=user_id,
        category=category,
        contact_status=contact_status,
        search=search,
        date_range=date_range,
        sort_by=sort_by,
        sort_order=sort_order
    )

    total_items = query.count()
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * page_size

    businesses = query.offset(offset).limit(page_size).all()

    # Hitung metrik dan kategori
    stats = _get_contacted_stats(db, user_id=user_id)
    categories = _get_distinct_categories(db, user_id=user_id)

    # Tambahkan format wa_direct_url untuk setiap lead
    for b in businesses:
        raw_phone = b.phone or ""
        clean_digits = "".join([c for c in raw_phone if c.isdigit()])
        if clean_digits.startswith("08"):
            target_wa = "62" + clean_digits[1:]
        elif clean_digits.startswith("8"):
            target_wa = "62" + clean_digits
        elif clean_digits.startswith("62"):
            target_wa = clean_digits
        else:
            target_wa = clean_digits
        b.direct_wa_link = f"https://wa.me/{target_wa}" if target_wa else None

    # Render template partial jika request berasal dari HTMX
    if request.headers.get("hx-request") and not request.headers.get("hx-boosted"):
        return templates.TemplateResponse(
            request=request,
            name="partials/contacted_table.html",
            context={
                "businesses": businesses,
                "total_items": total_items,
                "total_pages": total_pages,
                "current_page": page,
                "page_size": page_size,
                "category": category,
                "contact_status": contact_status,
                "search": search,
                "date_range": date_range,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "contact_status_enum": models.ContactStatus,
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="contacted.html",
        context={
            "request": request,
            "active_page": "contacted",
            "businesses": businesses,
            "stats": stats,
            "categories": categories,
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "page_size": page_size,
            "selected_category": category,
            "selected_status": contact_status,
            "search_query": search or "",
            "selected_date_range": date_range,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "contact_status_enum": models.ContactStatus,
            "lead_priority_enum": models.LeadPriority,
        }
    )


@router.post("/contacted/{business_id}/update-status")
async def update_contacted_status(
    request: Request,
    business_id: int,
    contact_status: models.ContactStatus = Form(...),
    notes: Optional[str] = Form(None),
    next_followup_at: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Update cepat status kontak, catatan pembukuan, atau tanggal follow-up dari halaman pembukuan.
    """
    user = getattr(request.state, "current_user", None)
    user_id = user.id if user else None

    query = db.query(models.Business).filter(models.Business.id == business_id)
    if user_id:
        query = query.filter(models.Business.user_id == user_id)
    business = query.first()

    if not business:
        raise HTTPException(status_code=404, detail="Lead tidak ditemukan")

    lead_status = business.lead_status
    now = datetime.utcnow()
    username = user.full_name or user.username if user else "Admin"

    if not lead_status:
        lead_status = models.LeadStatus(
            business_id=business.id,
            contact_status=contact_status,
            priority=models.LeadPriority.LOW,
            notes=notes,
            last_contacted_at=now,
            updated_at=now
        )
        db.add(lead_status)
    else:
        old_status = lead_status.contact_status.value
        lead_status.contact_status = contact_status
        lead_status.updated_at = now
        
        # Tambahkan catatan baru ke riwayat jika ada
        if notes and notes.strip():
            prefix = f"[{now.strftime('%d/%m/%y %H:%M')}] "
            if lead_status.notes:
                lead_status.notes = f"{lead_status.notes}\n{prefix}{notes.strip()}"
            else:
                lead_status.notes = f"{prefix}{notes.strip()}"

    if next_followup_at and next_followup_at.strip():
        try:
            lead_status.next_followup_at = datetime.fromisoformat(next_followup_at.strip())
        except Exception:
            pass

    activity = models.ActivityLog(
        business_id=business.id,
        action="status_updated_ledger",
        detail=f"Status pembukuan diubah menjadi '{contact_status.value.replace('_', ' ').title()}' oleh {username}.",
        created_by=username,
        created_at=now
    )
    db.add(activity)

    db.commit()

    # Jika request AJAX / HTMX, kembalikan respons sukses
    if request.headers.get("hx-request"):
        return HTMLResponse(
            f'<div class="p-2.5 rounded-lg bg-emerald-100 border border-emerald-400 text-emerald-900 text-xs font-bold animate-fade-in">'
            f'✓ Status {business.business_name} berhasil diperbarui: {contact_status.value.replace("_", " ").title()}'
            f'</div>'
        )

    # Fallback redirect kembali ke halaman pembukuan
    referer = request.headers.get("referer") or "/contacted"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=referer, status_code=303)


@router.get("/contacted/export/csv")
async def export_contacted_csv(
    request: Request,
    category: Optional[str] = None,
    contact_status: Optional[str] = None,
    search: Optional[str] = None,
    date_range: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Export rekapitulasi data pembukuan kontak ke format CSV untuk analisis spreadsheet.
    """
    user = getattr(request.state, "current_user", None)
    user_id = user.id if user else None

    query = _get_contacted_query(
        db=db,
        user_id=user_id,
        category=category,
        contact_status=contact_status,
        search=search,
        date_range=date_range,
        sort_by="last_contacted",
        sort_order="desc"
    )

    businesses = query.all()

    rows: List[Dict[str, Any]] = []
    for idx, b in enumerate(businesses, 1):
        ls = b.lead_status
        last_contact = ls.last_contacted_at.strftime("%Y-%m-%d %H:%M") if ls and ls.last_contacted_at else "-"
        next_followup = ls.next_followup_at.strftime("%Y-%m-%d %H:%M") if ls and ls.next_followup_at else "-"
        status_label = ls.contact_status.value.replace("_", " ").title() if ls and ls.contact_status else "Belum Dihubungi"

        rows.append({
            "No": idx,
            "Waktu Terakhir Kontak": last_contact,
            "Nama Bisnis / Usaha": b.business_name,
            "Kategori": b.category or "-",
            "Nomor Telepon": b.phone or "-",
            "Status Kontak": status_label,
            "Jadwal Follow Up": next_followup,
            "Catatan Pembukuan": ls.notes if ls and ls.notes else "-",
            "Kota": b.city or "-",
            "Provinsi": b.province or "-",
            "Alamat": b.address or "-",
            "Website": b.website or "-",
            "Rating": float(b.rating_avg) if b.rating_avg else "-",
            "Total Review": b.total_review or 0,
            "Link Google Maps": b.gmaps_url or "-",
        })

    df = pd.DataFrame(rows)
    stream = io.StringIO()
    df.to_csv(stream, index=False, encoding="utf-8-sig")

    filename = f"pembukuan_kontak_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=stream.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
