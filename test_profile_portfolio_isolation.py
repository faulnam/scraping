"""
Test script to verify:
1. BusinessProfile and PortfolioItems are isolated between Admin and Demo.
2. Demo profile defaults are blank/empty, Demo portfolio list is empty.
3. Admin profile and portfolios remain intact.
"""
from app.database import SessionLocal, init_db
from app import models
from app.routers.leads import get_profile_data, match_portfolio_for_business

def run_tests():
    init_db()
    db = SessionLocal()
    try:
        print("=== Test 1: Verify Admin vs Demo Profile & Portfolio Isolation ===")
        admin_user = db.query(models.User).filter(models.User.username == "admin").first()
        demo_user = db.query(models.User).filter(models.User.username == "demo").first()

        assert admin_user is not None
        assert demo_user is not None

        # Admin profile
        admin_co, admin_pic, admin_web, admin_tmpl = get_profile_data(db, user_id=admin_user.id)
        admin_ports = db.query(models.PortfolioItem).filter(models.PortfolioItem.user_id == admin_user.id).all()

        print(f"[OK] Admin profile: company='{admin_co}', website='{admin_web}', portfolios_count={len(admin_ports)}")
        assert bool(admin_co), "Admin company name should exist"
        assert len(admin_ports) > 0, "Admin should have portfolio items"

        # Demo profile
        demo_co, demo_pic, demo_web, demo_tmpl = get_profile_data(db, user_id=demo_user.id)
        demo_ports = db.query(models.PortfolioItem).filter(models.PortfolioItem.user_id == demo_user.id).all()

        print(f"[OK] Demo profile: company='{demo_co}', website='{demo_web}', portfolios_count={len(demo_ports)}")
        assert demo_co == "", f"Demo company should be empty, got '{demo_co}'"
        assert demo_web == "", f"Demo website should be empty, got '{demo_web}'"
        assert len(demo_ports) == 0, f"Demo should NOT have admin portfolios, got {len(demo_ports)}"

        # Matched portfolio for Demo business
        demo_biz = db.query(models.Business).filter(models.Business.user_id == demo_user.id).first()
        demo_matched = match_portfolio_for_business(demo_biz, db, user_id=demo_user.id)
        assert demo_matched is None, "Demo matched portfolio should be None (no portfolios)"
        print("[OK] Demo matched portfolio correctly returned None (no admin portfolio leak)")

        print("\n=== ALL PROFILE & PORTFOLIO ISOLATION TESTS PASSED! ===")
    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
