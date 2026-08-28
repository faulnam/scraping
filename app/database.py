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

    # Seed default portfolio presets if table is empty
    db = SessionLocal()
    try:
        from app.auth import hash_password

        # 1. Seed Admin User
        user_count = db.query(models.User).count()
        if user_count == 0:
            default_admin = models.User(
                username="admin",
                password_hash=hash_password("admin123"),
                full_name="Administrator LeadMaps",
                is_active=True,
                is_admin=True
            )
            db.add(default_admin)
            db.commit()
            print("[Database] Default Admin user created: 'admin' / 'admin123'")

        # 2. Seed Default API Keys from .env
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

        # 3. Seed Default Portfolios
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


