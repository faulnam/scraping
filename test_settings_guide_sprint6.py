"""
Automated validation test script for Sprint 6:
1. Test GET /settings/profile (Profile configuration form)
2. Test POST /settings/profile (Create & update business profile & WA template)
3. Test GET /guide (Methodology & Ethics documentation)
"""
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, init_db
from app.models import BusinessProfile
from app.auth import create_session_token, SESSION_COOKIE_NAME

client = TestClient(app)


def test_settings_and_guide():
    init_db()
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(1))
    print("\n=======================================================")
    print(" 1. TESTING GET /settings/profile (PROFILE FORM VIEW)")
    print("=======================================================")
    resp = client.get("/settings/profile")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.text
    assert "Profil Bisnis" in html
    assert "company_name" in html
    assert "default_wa_template" in html
    assert "{business_name}" in html
    print(" [OK] GET /settings/profile rendered successfully with configuration form.")

    print("\n=======================================================")
    print(" 2. TESTING POST /settings/profile (PROFILE CRUD UPDATE)")
    print("=======================================================")
    test_template = (
        "Halo {business_name}, salam kenal dari JuangDev. "
        "Kami siap membantu pembuatan website modern untuk meningkatkan penjualan usaha Anda. "
        "Boleh kami kirimkan portofolio kami?"
    )

    post_resp = client.post(
        "/settings/profile",
        data={
            "company_name": "JuangDev Digital Agency",
            "contact_person": "Juan Senior Consultant",
            "phone": "081299887711",
            "default_wa_template": test_template
        }
    )
    assert post_resp.status_code == 200, f"Expected 200, got {post_resp.status_code}"
    assert "berhasil disimpan" in post_resp.text
    assert "JuangDev Digital Agency" in post_resp.text

    # Verify persistence in database
    db = SessionLocal()
    profile = db.query(BusinessProfile).first()
    assert profile is not None
    assert profile.company_name == "JuangDev Digital Agency"
    assert profile.contact_person == "Juan Senior Consultant"
    assert profile.phone == "081299887711"
    assert profile.default_wa_template == test_template
    db.close()
    print(" [OK] POST /settings/profile successfully updated and verified in MySQL.")

    print("\n=======================================================")
    print(" 3. TESTING GET /guide (METHODOLOGY & ETHICS GUIDE VIEW)")
    print("=======================================================")
    guide_resp = client.get("/guide")
    assert guide_resp.status_code == 200, f"Expected 200, got {guide_resp.status_code}"
    guide_html = guide_resp.text
    assert "Metodologi & Panduan" in guide_html
    assert "Algoritma Lead Scoring" in guide_html
    assert "HIGH PRIORITY" in guide_html
    assert "Cache 30 Hari" in guide_html
    assert "Funnel Status" in guide_html
    assert "Panduan Etika Outreach" in guide_html
    print(" [OK] GET /guide rendered successfully with all methodology documentation sections.")

    print("\n=======================================================")
    print(" ALL SPRINT 6 TESTS PASSED SUCCESSFULLY!")
    print("=======================================================\n")


if __name__ == "__main__":
    test_settings_and_guide()
