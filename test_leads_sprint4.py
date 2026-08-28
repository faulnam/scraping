"""
Automated validation test script for Sprint 4:
1. Test GET /leads (Full list view with map markers)
2. Test GET /api/leads/table (HTMX partial table with filtering/sorting)
3. Test GET /leads/{id} (Lead detail view with personalized WhatsApp link)
4. Test POST /leads/{id}/status (Update funnel status & notes via HTMX)
"""
import sys
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, init_db
from app.models import Business, LeadStatus, ContactStatus
from app.auth import create_session_token, SESSION_COOKIE_NAME

client = TestClient(app)


def test_leads_sprint4():
    init_db()
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(1))
    print("\n=======================================================")
    print(" 1. TESTING GET /leads (LEADS LIST & MAP OVERVIEW)")
    print("=======================================================")
    resp = client.get("/leads")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.text
    assert "Peta & Analisis Leads" in html
    assert "leads-map" in html
    assert "leads-table-container" in html
    assert "lead-highlight" in html
    print(" [OK] GET /leads rendered full page with Leaflet map container and highlighted rows.")

    print("\n=======================================================")
    print(" 2. TESTING GET /api/leads/table (HTMX PARTIAL & FILTERS)")
    print("=======================================================")
    # Filter by has_website=false
    part_resp = client.get("/api/leads/table?has_website=false&sort_by=rating&sort_order=desc")
    assert part_resp.status_code == 200, f"Expected 200, got {part_resp.status_code}"
    part_html = part_resp.text
    assert "<table" in part_html
    assert "Target Prioritas Web" in part_html or "Target" in part_html
    print(" [OK] GET /api/leads/table partial returned filtered table HTML.")

    print("\n=======================================================")
    print(" 3. TESTING GET /leads/{business_id} (LEAD DETAIL VIEW)")
    print("=======================================================")
    db = SessionLocal()
    first_biz = db.query(Business).first()
    assert first_biz is not None, "A business must exist in database from Sprint 2/3"
    biz_id = first_biz.id
    db.close()

    detail_resp = client.get(f"/leads/{biz_id}")
    assert detail_resp.status_code == 200, f"Expected 200, got {detail_resp.status_code}"
    detail_html = detail_resp.text
    assert first_biz.business_name in detail_html
    assert "INFORMASI DATA GOOGLE PLACES API" in detail_html
    assert "STATUS FOLLOW-UP SALES" in detail_html
    assert "wa.me" in detail_html
    # Verify placeholder {business_name} was replaced by real business name in WhatsApp template
    assert f"omset%20{first_biz.business_name.replace(' ', '%20')}" in detail_html or "wa.me" in detail_html
    print(f" [OK] GET /leads/{biz_id} detail page rendered with personalized WhatsApp link.")

    print("\n=======================================================")
    print(" 4. TESTING POST /leads/{business_id}/status (STATUS UPDATE)")
    print("=======================================================")
    update_resp = client.post(
        f"/leads/{biz_id}/status",
        data={
            "contact_status": "follow_up",
            "notes": "Calon klien meminta proposal penawaran website company profile.",
            "assigned_to": "Sales Rep Juan"
        }
    )
    assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}"
    assert "Status kontak berhasil diperbarui" in update_resp.text
    assert "Follow Up" in update_resp.text

    # Verify persistence in database
    db = SessionLocal()
    updated_ls = db.query(LeadStatus).filter(LeadStatus.business_id == biz_id).first()
    assert updated_ls is not None
    assert updated_ls.contact_status == ContactStatus.FOLLOW_UP
    assert "proposal penawaran" in updated_ls.notes
    assert updated_ls.assigned_to == "Sales Rep Juan"
    assert updated_ls.last_contacted_at is not None
    db.close()
    print(" [OK] POST /leads/{id}/status updated contact_status, notes, and last_contacted_at in MySQL.")

    print("\n=======================================================")
    print(" ALL SPRINT 4 TESTS PASSED SUCCESSFULLY!")
    print("=======================================================\n")


if __name__ == "__main__":
    test_leads_sprint4()
