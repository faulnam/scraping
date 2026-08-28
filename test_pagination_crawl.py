"""
Test script for Pagination Crawling (Ambil Semua Hingga Habis & Custom Limit).
"""
import asyncio
from sqlalchemy.orm import Session
from app.database import SessionLocal, init_db
from app import models
from app.ingest.pipeline import run_ingest_pipeline
from app.places_api.client import PlacesApiClient


async def test_pagination():
    print("\n=======================================================")
    print(" TESTING PAGINATION & MULTI-PAGE CRAWLING ENGINE")
    print("=======================================================")
    init_db()
    db: Session = SessionLocal()

    # 1. Test Ingestion with Custom Limit (e.g. max_results=5) in Mock/Live Mode
    client = PlacesApiClient(db=db, use_mock=True)
    category = "Sekolah & Pendidikan"
    province = "Jawa Timur"
    city = "Kabupaten Sidoarjo"
    location_query = f"{city}, {province}"

    print(f"1. Menjalankan pipeline dengan target max_results=5 untuk '{category}' di '{location_query}'...")
    crawl_run_limit = await run_ingest_pipeline(
        category_query=category,
        location_query=location_query,
        province=province,
        city=city,
        max_results=5,
        db=db,
        client=client
    )

    print(f"   [Hasil Selesai] Total Businesses: {crawl_run_limit.total_businesses}, Status: {crawl_run_limit.status}")
    assert crawl_run_limit.status == "success"
    assert crawl_run_limit.total_businesses <= 5

    # 2. Test Ingestion with Unlimited Mode (max_results=None)
    print(f"\n2. Menjalankan pipeline mode 'Ambil Semua Hingga Habis' (max_results=None)...")
    crawl_run_unlimited = await run_ingest_pipeline(
        category_query="Klinik Kesehatan",
        location_query=location_query,
        province=province,
        city=city,
        max_results=None,
        db=db,
        client=client
    )

    print(f"   [Hasil Selesai] Total Businesses: {crawl_run_unlimited.total_businesses}, Status: {crawl_run_unlimited.status}")
    assert crawl_run_unlimited.status == "success"
    assert crawl_run_unlimited.total_businesses > 0

    # 3. Verify Database Records
    total_in_db = db.query(models.Business).count()
    print(f"\n3. Total businesses di database MySQL: {total_in_db} data")
    assert crawl_run_unlimited.total_businesses > 0
    assert total_in_db >= crawl_run_unlimited.total_businesses

    db.close()
    print("\n [OK] PAGINATION CRAWLING TESTS PASSED 100%!")


if __name__ == "__main__":
    asyncio.run(test_pagination())
