from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.get_database_url(),
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db():
    """Create all database tables defined in models and seed defaults."""
    from sqlalchemy import text
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Safe migration: Add website_url column to business_profile if it doesn't exist
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE business_profile ADD COLUMN website_url VARCHAR(255) NULL DEFAULT 'https://juangdev.my.id'"))
            conn.commit()
    except Exception:
        pass

    # Safe migration: Add image_url column to portfolio_items if it doesn't exist
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE portfolio_items ADD COLUMN image_url VARCHAR(500) NULL"))
            conn.commit()
    except Exception:
        pass

    # Safe migration: Add role column to users if it doesn't exist
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'admin'"))
            conn.commit()
    except Exception:
        pass

    # Safe migration: Add next_followup_at and followup_note to lead_status
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE lead_status ADD COLUMN next_followup_at DATETIME NULL"))
            conn.commit()
    except Exception:
        pass
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE lead_status ADD COLUMN followup_note VARCHAR(255) NULL"))
            conn.commit()
    except Exception:
        pass

    # Safe migration: Add user_id column to crawl_runs if it doesn't exist
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE crawl_runs ADD COLUMN user_id BIGINT NULL"))
            conn.commit()
    except Exception:
        pass

    # Safe migration: Add user_id column to businesses if it doesn't exist
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE businesses ADD COLUMN user_id BIGINT NULL"))
            conn.commit()
    except Exception:
        pass

    # Seed default data
    db = SessionLocal()
    try:
        from app.auth import hash_password

        # 1. Seed or Update Admin User
        admin_user = db.query(models.User).filter(models.User.username == "admin").first()
        if not admin_user:
            admin_user = models.User(
                username="admin",
                password_hash=hash_password("qwertyu111"),
                full_name="Administrator LeadMaps",
                is_active=True,
                is_admin=True,
                role="admin"
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print("[Database] Default Admin user created: 'admin' / 'qwertyu111'")
        else:
            # Sync password if updated in seed
            admin_user.password_hash = hash_password("qwertyu111")
            admin_user.role = "admin"
            db.commit()
            print("[Database] Admin user password synced to: 'qwertyu111'")

        # 2. Seed Admin Demo User if not exists
        demo_user = db.query(models.User).filter(models.User.username == "demo").first()
        if not demo_user:
            demo_user = models.User(
                username="demo",
                password_hash=hash_password("demo123"),
                full_name="Admin Demo",
                is_active=True,
                is_admin=False,
                role="admin_demo"
            )
            db.add(demo_user)
            db.commit()
            print("[Database] Admin Demo user created: 'demo' / 'demo123'")

        # 3. Associate any unassigned crawl_runs and businesses to admin
        if admin_user:
            db.query(models.CrawlRun).filter(models.CrawlRun.user_id.is_(None)).update({"user_id": admin_user.id})
            db.query(models.Business).filter(models.Business.user_id.is_(None)).update({"user_id": admin_user.id})
            db.commit()


        # 3. Seed Default API Keys from .env
        api_key_count = db.query(models.ApiKeyConfig).count()
        if api_key_count == 0:
            initial_keys = []
            priority_idx = 1
            if settings.SERPAPI_API_KEY and settings.SERPAPI_API_KEY.strip():
                initial_keys.append(models.ApiKeyConfig(
                    provider="serpapi",
                    label="SerpApi Akun Utama (250 Kuota)",
                    api_key=settings.SERPAPI_API_KEY.strip(),
                    is_active=True,
                    priority=priority_idx,
                    status="active",
                    quota_limit=250
                ))
                priority_idx += 1

            if settings.GOOGLE_MAPS_API_KEY and settings.GOOGLE_MAPS_API_KEY.strip():
                initial_keys.append(models.ApiKeyConfig(
                    provider="google_places",
                    label="Google Places API Resmi",
                    api_key=settings.GOOGLE_MAPS_API_KEY.strip(),
                    is_active=True,
                    priority=priority_idx,
                    status="active",
                    quota_limit=1000
                ))

            if initial_keys:
                db.add_all(initial_keys)
                db.commit()
                print(f"[Database] Seeded {len(initial_keys)} API keys from configuration.")

        # 4. Seed Default Portfolios
        count = db.query(models.PortfolioItem).count()
        if count == 0:
            default_portfolios = [
                models.PortfolioItem(
                    title="Toko Online & E-Commerce",
                    category_keywords="toko, retail, olshop, fashion, baju, pakaian, sepatu, tas, mart, perhiasan, optik, florist, pet shop, elektronik, grosir, distributor, e-commerce",
                    demo_url="https://juangdev.my.id/demo/ecommerce",
                    pitch_snippet="Kami memiliki portfolio & demo website Toko Online dengan fitur katalog produk interaktif, checkout WhatsApp otomatis, dan kalkulator ongkir.",
                    is_default=False
                ),
                models.PortfolioItem(
                    title="Klinik Medis & Praktek Dental/Dokter",
                    category_keywords="klinik, dokter, gigi, dental, kesehatan, rumah sakit, apotek, fisioterapi, laboratorium, medis, optik, spesialis",
                    demo_url="https://juangdev.my.id/demo/klinik-dental",
                    pitch_snippet="Kami memiliki demo sistem website klinik dengan fitur profil dokter, jadwal praktik, dan booking janji temu pasien (appointment) online.",
                    is_default=False
                ),
                models.PortfolioItem(
                    title="Restoran, Kafe & Kuliner",
                    category_keywords="restoran, resto, kafe, cafe, kuliner, coffee, kopi, bakery, catering, warung, rumah makan, food, pastry, bistro, lounge",
                    demo_url="https://juangdev.my.id/demo/resto-cafe",
                    pitch_snippet="Kami memiliki portfolio website Restoran & Kafe dengan fitur buku menu digital interaktif (QR Menu) dan reservasi meja online.",
                    is_default=False
                ),
                models.PortfolioItem(
                    title="Bengkel & Jasa Servis Otomotif",
                    category_keywords="bengkel, motor, mobil, otomotif, servis, service, cuci mobil, car wash, body repair, cat, ac mobil, sparepart, ban, variasi",
                    demo_url="https://juangdev.my.id/demo/bengkel-motor",
                    pitch_snippet="Kami memiliki portfolio website bengkel & layanan servis untuk memudahkan booking antrean servis berkala serta estimasi biaya transparan.",
                    is_default=False
                ),
                models.PortfolioItem(
                    title="Barbershop, Salon & Spa",
                    category_keywords="barbershop, barbers, pangkas rambut, salon, spa, beauty, massage, relaksasi, skincare, eyelash, nail art, potong rambut",
                    demo_url="https://juangdev.my.id/demo/barbershop-salon",
                    pitch_snippet="Kami memiliki demo website barbershop & salon modern dengan katalog gaya/layanan dan booking jadwal capster langsung dari HP.",
                    is_default=False
                ),
                models.PortfolioItem(
                    title="Company Profile & Jasa Profesional (Default)",
                    category_keywords="jasa, konsultan, kontraktor, arsitek, properti, kantor, ekspedisi, logistik, percetakan, legal, training, kursus, bimbel",
                    demo_url="https://juangdev.my.id",
                    pitch_snippet="Kami memiliki portfolio website company profile profesional berkecepatan tinggi yang dioptimasi untuk menjangkau pelanggan baru dari Google.",
                    is_default=True
                )
            ]
            db.add_all(default_portfolios)
            db.commit()
    except Exception as err:
        print(f"[Warning] Failed during db initialization seeding: {err}")
        db.rollback()
    finally:
        db.close()



