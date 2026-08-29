"""
Test script to verify Auth Role Preservation across all routes:
1. Verify Admin session preserves 'admin' role on /outreach, /dashboard, /leads, /settings/profile.
2. Verify Demo session preserves 'admin_demo' role.
"""
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, init_db
from app import models
from app.auth import create_session_token, SESSION_COOKIE_NAME

def run_tests():
    init_db()
    db = SessionLocal()
    client = TestClient(app)

    try:
        print("=== Test 1: Admin Role Preservation Across All Pages ===")
        admin_user = db.query(models.User).filter(models.User.username == "admin").first()
        demo_user = db.query(models.User).filter(models.User.username == "demo").first()

        assert admin_user is not None
        assert demo_user is not None

        # 1. Simulate Admin Session
        admin_token = create_session_token(admin_user.id)
        client.cookies.set(SESSION_COOKIE_NAME, admin_token)

        # Visit Dashboard
        resp_dash = client.get("/")
        assert resp_dash.status_code == 200
        assert "Akun Admin Utama" in resp_dash.text
        assert "Akun Demo (3 Token)" not in resp_dash.text
        print("[OK] Admin on Dashboard: Role verified as 'Akun Admin Utama'")

        # Visit Outreach
        resp_outreach = client.get("/outreach")
        assert resp_outreach.status_code == 200
        assert "Akun Admin Utama" in resp_outreach.text
        assert "Akun Demo (3 Token)" not in resp_outreach.text
        print("[OK] Admin on Outreach: Role verified as 'Akun Admin Utama' (No role switch)")

        # Visit Leads
        resp_leads = client.get("/leads")
        assert resp_leads.status_code == 200
        assert "Akun Admin Utama" in resp_leads.text
        assert "Akun Demo (3 Token)" not in resp_leads.text
        print("[OK] Admin on Leads: Role verified as 'Akun Admin Utama'")

        # Visit Settings Profile
        resp_prof = client.get("/settings/profile")
        assert resp_prof.status_code == 200
        assert "Akun Admin Utama" in resp_prof.text
        assert "Akun Demo (3 Token)" not in resp_prof.text
        print("[OK] Admin on Settings Profile: Role verified as 'Akun Admin Utama'")

        print("\n=== Test 2: Demo Role Preservation ===")
        # 2. Simulate Demo Session
        demo_token = create_session_token(demo_user.id)
        client.cookies.set(SESSION_COOKIE_NAME, demo_token)

        # Visit Dashboard
        resp_demo_dash = client.get("/")
        assert resp_demo_dash.status_code == 200
        assert "Akun Demo (3 Token)" in resp_demo_dash.text
        assert "Akun Admin Utama" not in resp_demo_dash.text
        print("[OK] Demo on Dashboard: Role verified as 'Akun Demo (3 Token)'")

        # Visit Outreach
        resp_demo_outreach = client.get("/outreach")
        assert resp_demo_outreach.status_code == 200
        assert "Akun Demo (3 Token)" in resp_demo_outreach.text
        assert "Akun Admin Utama" not in resp_demo_outreach.text
        print("[OK] Demo on Outreach: Role verified as 'Akun Demo (3 Token)'")

        print("\n=== ALL AUTH ROLE PRESERVATION TESTS PASSED! ===")
    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
