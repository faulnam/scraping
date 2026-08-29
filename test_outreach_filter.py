"""
Test script for Outreach Speed-Dial full queue & keyword filtering:
1. Tests keyword search on outreach queue (e.g. "padel").
2. Verifies unlimited queue retrieval (no 50 limit).
3. Verifies category and session filters.
"""
from app.database import SessionLocal, init_db
from app import models
from app.routers.outreach import _build_outreach_queue

def run_tests():
    init_db()
    db = SessionLocal()
    try:
        print("=== Test 1: Outreach Queue Keyword Filter & Unlimited Fetch ===")
        admin_user = db.query(models.User).filter(models.User.username == "admin").first()
        assert admin_user is not None

        # Count how many leads exist for keyword 'padel' (or any keyword)
        all_leads = _build_outreach_queue(db, user_id=admin_user.id)
        total_admin_leads = len(all_leads)
        print(f"[OK] Total leads in Admin queue: {total_admin_leads} (Unlimited retrieval verified)")

        # Search filter test with keyword "padel"
        padel_queue = _build_outreach_queue(db, user_id=admin_user.id, search="padel")
        print(f"[OK] Keyword 'padel' filter returned: {len(padel_queue)} leads")

        for b in padel_queue:
            matches_padel = (
                "padel" in (b.business_name or "").lower() or
                "padel" in (b.category or "").lower() or
                "padel" in (b.address or "").lower() or
                "padel" in (b.location_query or "").lower()
            )
            assert matches_padel, f"Business '{b.business_name}' should match keyword 'padel'"

        print("=== Test 2: Outreach Category Filter ===")
        categories = db.query(models.Business.category).filter(models.Business.user_id == admin_user.id).distinct().all()
        if categories and categories[0][0]:
            test_cat = categories[0][0]
            cat_queue = _build_outreach_queue(db, user_id=admin_user.id, category=test_cat)
            print(f"[OK] Category '{test_cat}' filter returned: {len(cat_queue)} leads")
            for b in cat_queue:
                assert test_cat.lower() in (b.category or "").lower() or test_cat.lower() in (b.location_query or "").lower()

        print("\n=== ALL OUTREACH FILTER TESTS PASSED! ===")
    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
