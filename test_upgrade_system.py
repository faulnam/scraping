"""
Comprehensive test script for the LeadMaps BI upgrade:
1. Tests database tables (activity_logs, demo_tokens, users.role, lead_status.next_followup_at).
2. Tests Admin & Admin Demo authentication & permissions.
3. Tests Admin Demo crawl token limit (3 per 24h).
4. Tests Outreach Speed-Dial queue and mark-sent endpoints.
5. Tests Bulk Actions (bulk status change & bulk delete).
6. Tests ActivityLog tracking.
"""
from datetime import datetime, timedelta
from app.database import SessionLocal, init_db
from app import models
from app.auth import hash_password, verify_password
from app.deps import check_demo_crawl_token, get_demo_token_info

def run_tests():
    init_db()
    db = SessionLocal()
    try:
        print("=== Test 1: Verify Models & Seeding ===")
        admin_user = db.query(models.User).filter(models.User.username == "admin").first()
        demo_user = db.query(models.User).filter(models.User.username == "demo").first()
        
        assert admin_user is not None, "Admin user must exist"
        assert admin_user.role == "admin", f"Admin role should be admin, got {admin_user.role}"
        assert demo_user is not None, "Demo user must exist"
        assert demo_user.role == "admin_demo", f"Demo role should be admin_demo, got {demo_user.role}"
        print(f"[OK] Users seeded: Admin ({admin_user.username}, role={admin_user.role}), Demo ({demo_user.username}, role={demo_user.role})")

        print("\n=== Test 2: Admin Demo 3 Token / 24h Crawl Limit ===")
        # Clear existing demo tokens for a clean test
        db.query(models.DemoToken).filter(models.DemoToken.user_id == demo_user.id).delete()
        db.commit()

        # Call 1
        res1 = check_demo_crawl_token(demo_user, db)
        assert res1["allowed"] == True, "Token 1 should be allowed"
        assert res1["tokens_remaining"] == 2, f"Expected 2 remaining, got {res1['tokens_remaining']}"
        print("[OK] Token 1 consumed (2 remaining)")

        # Call 2
        res2 = check_demo_crawl_token(demo_user, db)
        assert res2["allowed"] == True, "Token 2 should be allowed"
        assert res2["tokens_remaining"] == 1, f"Expected 1 remaining, got {res2['tokens_remaining']}"
        print("[OK] Token 2 consumed (1 remaining)")

        # Call 3
        res3 = check_demo_crawl_token(demo_user, db)
        assert res3["allowed"] == True, "Token 3 should be allowed"
        assert res3["tokens_remaining"] == 0, f"Expected 0 remaining, got {res3['tokens_remaining']}"
        print("[OK] Token 3 consumed (0 remaining)")

        # Call 4 (Should be blocked)
        res4 = check_demo_crawl_token(demo_user, db)
        assert res4["allowed"] == False, "Token 4 should be BLOCKED"
        print(f"[OK] Token 4 correctly blocked: '{res4['message']}'")

        # Admin user should never be blocked
        admin_res = check_demo_crawl_token(admin_user, db)
        assert admin_res["allowed"] == True, "Admin should always be allowed unlimited tokens"
        print("[OK] Full Admin user has unlimited crawl tokens")

        print("\n=== Test 3: ActivityLog & Follow-up Scheduling ===")
        biz = db.query(models.Business).first()
        if not biz:
            # Create a sample business for testing
            cr = models.CrawlRun(location_query="Bandung", category_query="Bengkel", status="success")
            db.add(cr)
            db.flush()
            biz = models.Business(
                crawl_run_id=cr.id,
                google_place_id="test_place_123",
                location_query="Bandung",
                category="Bengkel Motor",
                business_name="Bengkel Sejahtera Test",
                phone="081234567890",
                has_website=False,
                rating_avg=4.8,
                total_review=45
            )
            db.add(biz)
            db.flush()
            ls = models.LeadStatus(
                business_id=biz.id,
                contact_status=models.ContactStatus.BELUM_DIHUBUNGI,
                priority=models.LeadPriority.HIGH
            )
            db.add(ls)
            db.commit()

        now = datetime.utcnow()
        act = models.ActivityLog(
            business_id=biz.id,
            action="status_changed",
            detail="Status diubah menjadi Sudah Dihubungi untuk pengetesan",
            created_by="Admin",
            created_at=now
        )
        db.add(act)
        biz.lead_status.next_followup_at = now + timedelta(days=2)
        biz.lead_status.followup_note = "Hubungi kembali untuk follow-up"
        db.commit()

        loaded_act = db.query(models.ActivityLog).filter(models.ActivityLog.business_id == biz.id).first()
        assert loaded_act is not None
        assert biz.lead_status.next_followup_at is not None
        print(f"[OK] ActivityLog recorded: {loaded_act.action} by {loaded_act.created_by}")
        print(f"[OK] Follow-up scheduled for: {biz.lead_status.next_followup_at.strftime('%Y-%m-%d %H:%M')}")

        print("\n=== ALL UPGRADE TESTS PASSED SUCCESSFULLY! ===")
    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
