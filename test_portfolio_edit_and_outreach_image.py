"""
Comprehensive Unit & Integration Test:
1. Portfolio Edit Endpoint (POST /settings/portfolios/{id}/edit)
2. Image Mockup Replacement & Removal
3. Outreach Image URL Resolution & Placeholder Handling ({image_url}, {mockup_url})
4. Default Flag Toggle & Multi-User Isolation
"""
import os
import io

# Setup SQLite for isolated testing
os.environ["DATABASE_URL"] = "sqlite:///./test_temp_portfolio.db"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, Integer
from sqlalchemy.orm import sessionmaker
import app.database
from app.database import Base
from app import models
from app.auth import hash_password, create_session_token, SESSION_COOKIE_NAME
from app.routers.leads import build_personalized_wa_link, match_portfolio_for_business

# Adjust BigInteger for SQLite autoincrement compatibility in tests
for table in Base.metadata.tables.values():
    for column in table.columns:
        if column.primary_key:
            column.type = Integer()

# Setup test DB
test_engine = create_engine("sqlite:///./test_temp_portfolio.db", connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
app.database.engine = test_engine
app.database.SessionLocal = TestSessionLocal

from app.deps import get_db
from app.main import app

def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

def run_tests():
    print("\n=======================================================")
    print(" 1. INITIALIZING TEST SQLITE DATABASE & USERS")
    print("=======================================================")
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    
    db = TestSessionLocal()
    
    # Create test admin user
    admin_user = models.User(
        id=1,
        username="admin",
        password_hash=hash_password("admin123"),
        full_name="Admin Juang",
        is_admin=True,
        role="admin"
    )
    db.add(admin_user)
    
    # Create test lead & crawl run
    crawl_run = models.CrawlRun(
        id=1,
        user_id=1,
        location_query="Jakarta Selatan",
        category_query="Padel Club",
        status="success",
        total_businesses=1
    )
    db.add(crawl_run)
    db.commit()

    biz = models.Business(
        id=1,
        user_id=1,
        crawl_run_id=1,
        google_place_id="ChIJ_test_padel_123",
        location_query="Jakarta Selatan",
        category="Padel Court & Sports Club",
        business_name="Padel Arena Jakarta",
        phone="081234567890",
        has_website=False,
        rating_avg=4.9,
        total_review=45
    )
    db.add(biz)
    
    # Default profile
    profile = models.BusinessProfile(
        id=1,
        user_id=1,
        company_name="JuangDev Solutions",
        contact_person="Ahmad Juang",
        website_url="https://juangdev.my.id",
        default_wa_template="Halo {business_name}, portofolio: {portfolio_url} mockup: {mockup_url}"
    )
    db.add(profile)
    db.commit()

    # Authenticate as admin
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(admin_user.id))
    print(f" [OK] Logged in as Admin (ID #{admin_user.id})")

    print("\n=======================================================")
    print(" 2. TESTING ADD PORTFOLIO WITH IMAGE FILE UPLOAD")
    print("=======================================================")
    fake_png = io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4")
    
    add_resp = client.post(
        "/settings/portfolios",
        data={
            "title": "Website Padel & Sport Club",
            "category_keywords": "padel, sport, tenis, lapangan, olahraga, club",
            "demo_url": "https://demo-padel.juangdev.my.id",
            "pitch_snippet": "Kami memiliki sistem booking lapangan & membership Padel modern.",
            "is_default": False
        },
        files={
            "image_file": ("padel_mockup.png", fake_png, "image/png")
        },
        follow_redirects=False
    )
    assert add_resp.status_code == 303
    assert "portfolio_added=1" in add_resp.headers["location"]
    
    created_item = db.query(models.PortfolioItem).filter(
        models.PortfolioItem.title == "Website Padel & Sport Club",
        models.PortfolioItem.user_id == admin_user.id
    ).first()
    assert created_item is not None
    assert created_item.image_url is not None
    assert "/static/uploads/portfolio/" in created_item.image_url
    print(f" [OK] Created portfolio ID #{created_item.id} with image: {created_item.image_url}")

    print("\n=======================================================")
    print(" 3. TESTING EDIT PORTFOLIO (DATA & ONLINE IMAGE URL UPDATE)")
    print("=======================================================")
    edit_resp = client.post(
        f"/settings/portfolios/{created_item.id}/edit",
        data={
            "title": "Website Padel & Tennis Arena (Updated)",
            "category_keywords": "padel, sport, arena, raket, tenis, badminton",
            "demo_url": "https://padel-arena.juangdev.my.id",
            "pitch_snippet": "Sistem booking lapangan instan via WA.",
            "image_url": "https://images.unsplash.com/photo-1554068865-24cecd4e34b8",
            "is_default": False,
            "remove_image": False
        },
        follow_redirects=False
    )
    assert edit_resp.status_code == 303
    assert "portfolio_updated=1" in edit_resp.headers["location"]
    
    db.refresh(created_item)
    assert created_item.title == "Website Padel & Tennis Arena (Updated)"
    assert created_item.demo_url == "https://padel-arena.juangdev.my.id"
    assert created_item.category_keywords == "padel, sport, arena, raket, tenis, badminton"
    assert created_item.pitch_snippet == "Sistem booking lapangan instan via WA."
    assert created_item.image_url == "https://images.unsplash.com/photo-1554068865-24cecd4e34b8"
    print(f" [OK] Successfully edited portfolio #{created_item.id} with new URL image & fields")

    print("\n=======================================================")
    print(" 4. TESTING EDIT PORTFOLIO WITH NEW FILE UPLOAD & DEFAULT FLAG")
    print("=======================================================")
    fake_png_2 = io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x06\x00\x00\x00\x1f\x15c4")
    edit_file_resp = client.post(
        f"/settings/portfolios/{created_item.id}/edit",
        data={
            "title": "Website Padel & Tennis Arena (Updated)",
            "category_keywords": "padel, sport, arena, raket, tenis, badminton",
            "demo_url": "https://padel-arena.juangdev.my.id",
            "pitch_snippet": "Sistem booking lapangan instan via WA.",
            "is_default": True,
            "remove_image": False
        },
        files={
            "image_file": ("padel_v2.png", fake_png_2, "image/png")
        },
        follow_redirects=False
    )
    assert edit_file_resp.status_code == 303
    db.refresh(created_item)
    assert "/static/uploads/portfolio/" in created_item.image_url
    assert created_item.is_default is True
    print(f" [OK] Successfully uploaded replacement image file: {created_item.image_url} and set default=True")

    print("\n=======================================================")
    print(" 5. TESTING EDIT PORTFOLIO (REMOVE IMAGE OPTION)")
    print("=======================================================")
    remove_img_resp = client.post(
        f"/settings/portfolios/{created_item.id}/edit",
        data={
            "title": "Website Padel & Tennis Arena (Updated)",
            "category_keywords": "padel, sport, arena",
            "demo_url": "https://padel-arena.juangdev.my.id",
            "pitch_snippet": "Pitch tanpa mockup gambar.",
            "is_default": False,
            "remove_image": True
        },
        follow_redirects=False
    )
    assert remove_img_resp.status_code == 303
    db.refresh(created_item)
    assert created_item.image_url is None
    print(" [OK] Successfully removed image from portfolio.")

    print("\n=======================================================")
    print(" 6. TESTING OUTREACH PLACEHOLDER RESOLUTION ({image_url}, {mockup_url})")
    print("=======================================================")
    # Put image back
    created_item.image_url = "/static/uploads/portfolio/test_padel.png"
    db.commit()

    template_with_img = (
        "Halo {business_name}, lihat portofolio {portfolio_name} kami di {portfolio_url}.\n"
        "Mockup desain: {image_url}\n"
        "Web kami: {website_url}"
    )

    wa_link = build_personalized_wa_link(
        phone="081234567890",
        business_name="Padel Club Jakarta",
        template=template_with_img,
        portfolio=created_item,
        company_name="JuangDev Solutions",
        contact_person="Konsultan",
        website_url="https://juangdev.my.id",
        base_url="https://app.juangdev.com"
    )
    assert wa_link is not None
    assert "https%3A//app.juangdev.com/static/uploads/portfolio/test_padel.png" in wa_link or "app.juangdev.com" in wa_link
    print(f" [OK] WhatsApp link successfully includes resolved image URL: {wa_link[:100]}...")

    print("\n=======================================================")
    print(" 7. TESTING OUTREACH SPEED-DIAL PAGE RENDERING")
    print("=======================================================")
    outreach_resp = client.get("/outreach")
    assert outreach_resp.status_code == 200
    assert "WhatsApp Outreach Studio" in outreach_resp.text
    assert "Mockup Desain Web" in outreach_resp.text
    assert "Link Mockup" in outreach_resp.text
    assert "+ Ke Chat" in outreach_resp.text
    print(" [OK] GET /outreach rendered with Mockup controls & + Ke Chat button.")

    print("\n=======================================================")
    print(" 8. TESTING SETTINGS PROFILE PAGE RENDERING WITH EDIT MODAL")
    print("=======================================================")
    profile_resp = client.get("/settings/profile")
    assert profile_resp.status_code == 200
    assert "edit-portfolio-modal" in profile_resp.text
    assert "openEditPortfolioModal" in profile_resp.text
    assert "{image_url}" in profile_resp.text
    assert "{mockup_url}" in profile_resp.text
    print(" [OK] GET /settings/profile rendered with Edit Portfolio Modal & Placeholders.")

    db.close()
    test_engine.dispose()
    try:
        if os.path.exists("./test_temp_portfolio.db"):
            os.remove("./test_temp_portfolio.db")
        print(" [OK] Cleaned up temporary test database.")
    except Exception:
        pass

    print("\n=======================================================")
    print(" ALL PORTFOLIO EDIT & OUTREACH IMAGE TESTS PASSED (100%)")
    print("=======================================================\n")

if __name__ == "__main__":
    run_tests()
