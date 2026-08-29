"""
Test script to verify Admin Password Update & Multi-User Data Isolation:
1. Verify password for 'admin' is now 'qwertyu111' and old 'admin123' fails.
2. Verify data isolation between 'admin' and 'demo'.
"""
from datetime import datetime
from app.database import SessionLocal, init_db
from app import models
from app.auth import verify_password
from app.routers.leads import _get_filtered_leads_query
from app.routers.outreach import _build_outreach_queue
from app.routers.dashboard import _get_dashboard_stats

def run_tests():
    init_db()
    db = SessionLocal()
    try:
        print("=== Test 1: Admin Password Update ===")
        admin_user = db.query(models.User).filter(models.User.username == "admin").first()
        demo_user = db.query(models.User).filter(models.User.username == "demo").first()

        assert admin_user is not None, "Admin user must exist"
        assert demo_user is not None, "Demo user must exist"

        # Verify new password
        assert verify_password("qwertyu111", admin_user.password_hash) == True, "Password 'qwertyu111' MUST verify"
        print("[OK] Admin password verified successfully with 'qwertyu111'")

        # Verify old password fails
        assert verify_password("admin123", admin_user.password_hash) == False, "Old password 'admin123' MUST FAIL"
        print("[OK] Old password 'admin123' rejected as expected")

        # Verify demo password
        assert verify_password("demo123", demo_user.password_hash) == True, "Demo password 'demo123' MUST verify"
        print("[OK] Demo password 'demo123' verified successfully")

        print("\n=== Test 2: Multi-User Data Isolation ===")

        # Clean previous test isolation data
        db.query(models.Business).filter(models.Business.google_place_id.in_(["admin_place_1", "demo_place_1"])).delete()
        db.query(models.CrawlRun).filter(models.CrawlRun.location_query == "TestIsolationCity").delete()
        db.commit()

        # 1. Create Admin Crawl & Business
        admin_cr = models.CrawlRun(
            user_id=admin_user.id,
            location_query="TestIsolationCity",
            category_query="Admin Category",
            status="success",
            total_businesses=1
        )
        db.add(admin_cr)
        db.flush()

        admin_biz = models.Business(
            user_id=admin_user.id,
            crawl_run_id=admin_cr.id,
            google_place_id="admin_place_1",
            location_query="TestIsolationCity",
            category="Admin Category",
            business_name="Admin Exclusive Business",
            phone="081111111111",
            has_website=False,
            rating_avg=4.9,
            total_review=100
        )
        db.add(admin_biz)
        db.flush()
        db.add(models.LeadStatus(business_id=admin_biz.id, contact_status=models.ContactStatus.BELUM_DIHUBUNGI, priority=models.LeadPriority.HIGH))

        # 2. Create Demo Crawl & Business
        demo_cr = models.CrawlRun(
            user_id=demo_user.id,
            location_query="TestIsolationCity",
            category_query="Demo Category",
            status="success",
            total_businesses=1
        )
        db.add(demo_cr)
        db.flush()

        demo_biz = models.Business(
            user_id=demo_user.id,
            crawl_run_id=demo_cr.id,
            google_place_id="demo_place_1",
            location_query="TestIsolationCity",
            category="Demo Category",
            business_name="Demo Sandbox Business",
            phone="082222222222",
            has_website=False,
            rating_avg=4.2,
            total_review=10
        )
        db.add(demo_biz)
        db.flush()
        db.add(models.LeadStatus(business_id=demo_biz.id, contact_status=models.ContactStatus.BELUM_DIHUBUNGI, priority=models.LeadPriority.MEDIUM))
        db.commit()

        # 3. Query Leads for Admin
        admin_leads = _get_filtered_leads_query(db, user_id=admin_user.id).all()
        admin_lead_names = [b.business_name for b in admin_leads]
        assert "Admin Exclusive Business" in admin_lead_names, "Admin must see their own business"
        assert "Demo Sandbox Business" not in admin_lead_names, "Admin MUST NOT see Demo's business"
        print("[OK] Admin lead query is properly isolated (Demo leads hidden)")

        # 4. Query Leads for Demo
        demo_leads = _get_filtered_leads_query(db, user_id=demo_user.id).all()
        demo_lead_names = [b.business_name for b in demo_leads]
        assert "Demo Sandbox Business" in demo_lead_names, "Demo must see their own business"
        assert "Admin Exclusive Business" not in demo_lead_names, "Demo MUST NOT see Admin's business"
        print("[OK] Demo lead query is properly isolated (Admin leads hidden)")

        # 5. Query Outreach Queue for Admin vs Demo
        admin_queue = _build_outreach_queue(db, user_id=admin_user.id, filter_mode="not_contacted")
        demo_queue = _build_outreach_queue(db, user_id=demo_user.id, filter_mode="not_contacted")

        assert any(b.business_name == "Admin Exclusive Business" for b in admin_queue)
        assert not any(b.business_name == "Demo Sandbox Business" for b in admin_queue)

        assert any(b.business_name == "Demo Sandbox Business" for b in demo_queue)
        assert not any(b.business_name == "Admin Exclusive Business" for b in demo_queue)
        print("[OK] Outreach queue is properly isolated between Admin and Demo")

        # 6. Dashboard Stats Isolation
        admin_stats = _get_dashboard_stats(db, user_id=admin_user.id)
        demo_stats = _get_dashboard_stats(db, user_id=demo_user.id)

        print(f"[OK] Dashboard stats: Admin total businesses = {admin_stats['total_businesses']}, Demo total businesses = {demo_stats['total_businesses']}")

        print("\n=== ALL ISOLATION & PASSWORD TESTS PASSED! ===")
    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
