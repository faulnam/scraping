"""
Export Router: Export filtered leads dataset to CSV and Excel via pandas & openpyxl.
Isolated per user: Exports only leads belonging to current user.
"""
from datetime import datetime
import io
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session
import pandas as pd

from app.deps import get_db
from app.routers.leads import _get_filtered_leads_query, get_profile_data, match_portfolio_for_business, build_personalized_wa_link

router = APIRouter(prefix="/export", tags=["export"])


def _build_leads_export_dataframe(
    db: Session,
    user_id: Optional[int] = None,
    crawl_run_id: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    has_website: Optional[str] = None,
    min_rating: Optional[str] = None,
    contact_status: Optional[str] = None,
    priority: Optional[str] = None,
    sort_by: str = "date",
    sort_order: str = "desc"
) -> pd.DataFrame:
    """Query MySQL and construct a pandas DataFrame ready for CSV/Excel export, isolated by user_id."""
    query = _get_filtered_leads_query(
        db,
        user_id=user_id,
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

    businesses = query.all()
    company_name, contact_person, website_url, wa_template = get_profile_data(db)

    rows: List[Dict[str, Any]] = []
    for b in businesses:
        ls = b.lead_status
        matched_p = match_portfolio_for_business(b, db)
        wa_link = build_personalized_wa_link(
            b.phone, 
            b.business_name, 
            wa_template,
            portfolio=matched_p,
            company_name=company_name,
            contact_person=contact_person,
            website_url=website_url
        )
        
        status_val = ls.contact_status.value.replace("_", " ").title() if ls else "Belum Dihubungi"
        prio_val = ls.priority.value.upper() if ls else "LOW"
        notes_val = ls.notes if ls and ls.notes else ""
        pic_val = ls.assigned_to if ls and ls.assigned_to else ""
        last_contacted_val = ls.last_contacted_at.strftime("%Y-%m-%d %H:%M") if ls and ls.last_contacted_at else ""
        scraped_val = b.scraped_at.strftime("%Y-%m-%d %H:%M") if b.scraped_at else ""
        portfolio_title = matched_p.title if matched_p else "Website Profesional"
        portfolio_demo = matched_p.demo_url if matched_p else "https://juangdev.my.id"

        rows.append({
            "ID": b.id,
            "Nama Usaha": b.business_name,
            "Kategori": b.category or "",
            "Status Website": "Sudah Ada Website" if b.has_website else "Belum Ada Website (Target)",
            "Website URL": b.website or "",
            "Nomor Telepon": b.phone or "",
            "Demo Web Ditawarkan": portfolio_title,
            "Link Demo Ditawarkan": portfolio_demo,
            "Link WhatsApp Direct": wa_link or "",
            "Rating": float(b.rating_avg) if b.rating_avg is not None else "",
            "Total Ulasan": b.total_review,
            "Alamat Lengkap": b.address or "",
            "Kota": b.city or "",
            "Provinsi": b.province or "",
            "Jam Operasional": b.opening_hours or "",
            "Status Funnel Sales": status_val,
            "Tingkat Prioritas": prio_val,
            "PIC Sales": pic_val,
            "Catatan Sales": notes_val,
            "Terakhir Dihubungi": last_contacted_val,
            "Tanggal Data Diperoleh": scraped_val,
            "Google Maps Link": b.gmaps_url or "",
            "Google Place ID": b.google_place_id,
        })

    return pd.DataFrame(rows)


@router.get("/leads.csv")
async def export_leads_csv(
    request: Request,
    crawl_run_id: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    has_website: Optional[str] = None,
    min_rating: Optional[str] = None,
    contact_status: Optional[str] = None,
    priority: Optional[str] = None,
    sort_by: str = "date",
    sort_order: str = "desc",
    db: Session = Depends(get_db)
):
    """
    Export filtered leads dataset to CSV format with UTF-8 BOM encoding for Excel compatibility.
    """
    user = getattr(request.state, "current_user", None)
    user_id = user.id if user else None

    df = _build_leads_export_dataframe(
        db,
        user_id=user_id,
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

    csv_data = df.to_csv(index=False, encoding="utf-8-sig")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"leadmaps_leads_{timestamp}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/leads.xlsx")
async def export_leads_excel(
    request: Request,
    crawl_run_id: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    has_website: Optional[str] = None,
    min_rating: Optional[str] = None,
    contact_status: Optional[str] = None,
    priority: Optional[str] = None,
    sort_by: str = "date",
    sort_order: str = "desc",
    db: Session = Depends(get_db)
):
    """
    Export filtered leads dataset to Excel XLSX spreadsheet using pandas & openpyxl.
    """
    user = getattr(request.state, "current_user", None)
    user_id = user.id if user else None

    df = _build_leads_export_dataframe(
        db,
        user_id=user_id,
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

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Leads Data")
        
        # Auto adjust column widths for clean readability
        worksheet = writer.sheets["Leads Data"]
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = col[0].column_letter
            worksheet.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

    output.seek(0)
    xlsx_bytes = output.getvalue()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"leadmaps_leads_{timestamp}.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
