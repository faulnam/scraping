"""
Automated validation test script for Sprint 3:
1. Test GET / (Dashboard view with real MySQL query metrics)
2. Test GET /api/dashboard/metrics (Partial metrics endpoint)
3. Test GET /api/dashboard/charts (Chart.js dynamic JSON data feed)
4. Test POST /crawl (HTMX crawl endpoint)
"""
import sys
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, init_db
from app.models import Business, LeadStatus, CrawlRun
from app.auth import create_session_token, SESSION_COOKIE_NAME

client = TestClient(app)


def test_dashboard_sprint3():
    init_db()
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(1))
    print("\n=======================================================")
    print(" 1. TESTING GET / (DASHBOARD HTML VIEW)")
    print("=======================================================")
    response = client.get("/")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    html = response.text
    assert "Dashboard Ringkasan" in html
    assert "Mulai Crawling Leads Baru" in html
    assert "Agregasi" in html
    assert "Total Usaha Terdata" in html
    assert "Belum Punya Website" in html
    assert "Rata-rata Rating Pasar" in html
    assert "Leads Sudah Dihubungi" in html
    assert "categoryChart" in html
    assert "websiteRatingChart" in html
    print(" [OK] GET / rendered successfully with all required cards and components.")

    print("\n=======================================================")
    print(" 2. TESTING GET /api/dashboard/metrics (PARTIAL HTML)")
    print("=======================================================")
    metrics_resp = client.get("/api/dashboard/metrics?province=Jawa%20Barat&city=Kota%20Bandung")
    assert metrics_resp.status_code == 200, f"Expected 200, got {metrics_resp.status_code}"
    metrics_html = metrics_resp.text
    assert "Agregasi" in metrics_html
    assert "Total Usaha Terdata" in metrics_html
    print(" [OK] GET /api/dashboard/metrics returned valid partial HTML.")

    print("\n=======================================================")
    print(" 3. TESTING GET /api/dashboard/charts (JSON ENDPOINT)")
    print("=======================================================")
    charts_resp = client.get("/api/dashboard/charts")
    assert charts_resp.status_code == 200, f"Expected 200, got {charts_resp.status_code}"
    chart_data = charts_resp.json()
    print(" Chart Data received from MySQL:")
    print(" - Categories:", chart_data.get("categories"))
    print(" - Website vs Rating:", chart_data.get("website_vs_rating"))

    assert "categories" in chart_data
    assert "labels" in chart_data["categories"]
    assert "counts" in chart_data["categories"]
    assert "website_vs_rating" in chart_data
    assert len(chart_data["website_vs_rating"]["without_website"]) == 3
    assert len(chart_data["website_vs_rating"]["with_website"]) == 3
    print(" [OK] GET /api/dashboard/charts returned structured dynamic data from MySQL.")

    print("\n=======================================================")
    print(" 4. TESTING POST /crawl (HTMX CRAWL TRIGGER)")
    print("=======================================================")
    crawl_resp = client.post(
        "/crawl",
        data={
            "category_query": "Klinik Gigi & Dental",
            "province": "Jawa Barat",
            "city": "Kota Bandung"
        }
    )
    assert crawl_resp.status_code == 200, f"Expected 200, got {crawl_resp.status_code}"
    assert "HX-Trigger" in crawl_resp.headers
    assert crawl_resp.headers["HX-Trigger"] == "refreshDashboard"
    assert "Crawling Selesai Berhasil" in crawl_resp.text
    print(" [OK] POST /crawl triggered pipeline, returned success banner and HX-Trigger header.")

    print("\n=======================================================")
    print(" ALL SPRINT 3 TESTS PASSED SUCCESSFULLY!")
    print("=======================================================\n")


if __name__ == "__main__":
    test_dashboard_sprint3()
