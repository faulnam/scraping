"""
Unit & Integration Test: Custom WhatsApp Pitch Studio & Dynamic Category-Matched Portfolio Demo Links
"""
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, init_db
from app import models
from app.routers.leads import match_portfolio_for_business, build_personalized_wa_link, DEFAULT_WA_TEMPLATE

client = TestClient(app)


def test_portfolio_feature():
    print("\n=======================================================")
    print(" 1. TESTING DATABASE PORTFOLIO SEEDING")
    print("=======================================================")
    init_db()
    db = SessionLocal()
    
    portfolios = db.query(models.PortfolioItem).all()
    print(f" Total portfolio items found in DB: {len(portfolios)}")
    assert len(portfolios) >= 6, "Default portfolio items should be at least 6"
    for p in portfolios:
        print(f" - [{p.id}] {p.title} -> {p.demo_url} (Default: {p.is_default})")
    print(" [OK] Portfolio presets verified in MySQL.")

    print("\n=======================================================")
    print(" 2. TESTING CATEGORY-MATCHING ALGORITHM")
    print("=======================================================")
    # Test Clinic
    b_clinic = models.Business(business_name="Klinik Gigi Sehat", category="Klinik Gigi & Dental")
    matched_clinic = match_portfolio_for_business(b_clinic, db)
    print(f" Target: '{b_clinic.business_name}' ({b_clinic.category}) -> Matched: '{matched_clinic.title}' [{matched_clinic.demo_url}]")
    assert "Klinik" in matched_clinic.title or "Dental" in matched_clinic.title

    # Test Toko / Olshop
    b_shop = models.Business(business_name="Butik Fashion Trendy", category="Toko Pakaian & Fashion")
    matched_shop = match_portfolio_for_business(b_shop, db)
    print(f" Target: '{b_shop.business_name}' ({b_shop.category}) -> Matched: '{matched_shop.title}' [{matched_shop.demo_url}]")
    assert "Toko Online" in matched_shop.title or "E-Commerce" in matched_shop.title

    # Test Resto
    b_resto = models.Business(business_name="Kafe Kopi Senja", category="Kafe & Restoran")
    matched_resto = match_portfolio_for_business(b_resto, db)
    print(f" Target: '{b_resto.business_name}' ({b_resto.category}) -> Matched: '{matched_resto.title}' [{matched_resto.demo_url}]")
    assert "Restoran" in matched_resto.title or "Kafe" in matched_resto.title

    # Test Bengkel
    b_bengkel = models.Business(business_name="Bengkel Motor Juang Speed", category="Bengkel Motor")
    matched_bengkel = match_portfolio_for_business(b_bengkel, db)
    print(f" Target: '{b_bengkel.business_name}' ({b_bengkel.category}) -> Matched: '{matched_bengkel.title}' [{matched_bengkel.demo_url}]")
    assert "Bengkel" in matched_bengkel.title

    # Test Fallback Default
    b_general = models.Business(business_name="CV Maju Logistik", category="Ekspedisi")
    matched_general = match_portfolio_for_business(b_general, db)
    print(f" Target: '{b_general.business_name}' ({b_general.category}) -> Matched: '{matched_general.title}' [{matched_general.demo_url}]")
    assert matched_general is not None

    print(" [OK] All category matching test cases passed.")

    print("\n=======================================================")
    print(" 3. TESTING DYNAMIC WHATSAPP LINK BUILDER")
    print("=======================================================")
    wa_link = build_personalized_wa_link(
        phone="081234567890",
        business_name="Klinik Gigi Juang Dental",
        template=DEFAULT_WA_TEMPLATE,
        portfolio=matched_clinic,
        company_name="JuangDev Solutions",
        contact_person="Ahmad Sales",
        website_url="https://juangdev.my.id"
    )
    print(f" Generated WA Link:\n {wa_link}")
    assert wa_link is not None
    assert "wa.me/6281234567890" in wa_link
    assert "klinik-dental" in wa_link or "Klinik" in wa_link
    assert "juangdev.my.id" in wa_link
    print(" [OK] Dynamic WA link with demo URL & official website URL verified.")

    from app.auth import create_session_token, SESSION_COOKIE_NAME
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(1))

    print("\n=======================================================")
    print(" 4. TESTING LEAD DETAIL ROUTE WITH OUTREACH STUDIO")
    print("=======================================================")
    # Get first business in DB
    first_biz = db.query(models.Business).first()
    if first_biz:
        res = client.get(f"/leads/{first_biz.id}")
        assert res.status_code == 200
        assert "WhatsApp Outreach Studio" in res.text
        assert "Pilih Portofolio / Demo Web yang Ditawarkan" in res.text
        assert "Mockup Desain Web" in res.text
        print(f" [OK] GET /leads/{first_biz.id} successfully rendered with Outreach Studio & Mockup preview!")

    print("\n=======================================================")
    print(" 5. TESTING PORTFOLIO CRUD WITH IMAGE MOCKUP UPLOAD")
    print("=======================================================")
    import io
    # Test uploading fake PNG image file
    fake_img = io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4")
    
    post_res = client.post(
        "/settings/portfolios",
        data={
            "title": "Website Agensi Properti & Real Estate",
            "category_keywords": "properti, real estate, rumah, apartemen",
            "demo_url": "https://demo-properti.juangdev.my.id",
            "pitch_snippet": "Kami memiliki demo website listing properti.",
            "is_default": False
        },
        files={
            "image_file": ("properti_mockup.png", fake_img, "image/png")
        },
        follow_redirects=False
    )
    assert post_res.status_code == 303
    
    new_p = db.query(models.PortfolioItem).filter(models.PortfolioItem.title == "Website Agensi Properti & Real Estate").first()
    assert new_p is not None
    assert new_p.image_url is not None
    assert "/static/uploads/portfolio/" in new_p.image_url
    print(f" [OK] Added new portfolio ID #{new_p.id} with uploaded mockup: {new_p.image_url}")

    # Test updating image
    update_res = client.post(
        f"/settings/portfolios/{new_p.id}/update-image",
        data={"image_url": "https://images.unsplash.com/photo-1560518883-ce09059eeffa"},
        follow_redirects=False
    )
    assert update_res.status_code == 303
    db.refresh(new_p)
    assert new_p.image_url == "https://images.unsplash.com/photo-1560518883-ce09059eeffa"
    print(f" [OK] Updated portfolio image successfully: {new_p.image_url}")

    # Delete portfolio
    del_res = client.post(f"/settings/portfolios/{new_p.id}/delete", follow_redirects=False)
    assert del_res.status_code == 303
    deleted_check = db.query(models.PortfolioItem).filter(models.PortfolioItem.id == new_p.id).first()
    assert deleted_check is None
    print(f" [OK] Deleted portfolio ID #{new_p.id} successfully.")

    db.close()
    print("\n=======================================================")
    print(" ALL PORTFOLIO & CUSTOM WA TESTS PASSED SUCCESSFULLY! (100% PASS)")
    print("=======================================================")


if __name__ == "__main__":
    test_portfolio_feature()
