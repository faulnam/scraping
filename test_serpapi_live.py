"""
Test script to verify live crawling using SerpApi key with MySQL persistence.
"""
import asyncio
from sqlalchemy.orm import Session
from app.database import SessionLocal, init_db
from app.models import CrawlRun, Business, LeadStatus
from app.places_api.client import PlacesApiClient
from app.ingest.pipeline import run_ingest_pipeline


async def test_serpapi_crawl():
    print("\n=======================================================")
    print(" TESTING LIVE SERPAPI GOOGLE MAPS CRAWLING")
    print("=======================================================")
    init_db()
    db: Session = SessionLocal()

    category = "Klinik Gigi & Dental"
    province = "Jawa Barat"
    city = "Kota Bandung"
    location_query = f"{city}, {province}"

    print(f">> Executing Live Search for '{category}' in '{location_query}'...")
    crawl_run = await run_ingest_pipeline(
        category_query=category,
        location_query=location_query,
        province=province,
        city=city,
        db=db
    )

    print(f"\n [Crawl Finished] Sesi #{crawl_run.id}, Status={crawl_run.status}, Total Leads={crawl_run.total_businesses}")

    # Query latest businesses
    businesses = db.query(Business).filter(Business.crawl_run_id == crawl_run.id).all()
    print(f"\n>> Berhasil mengambil {len(businesses)} data USAHA ASLI dari Google Maps via SerpApi:")
    print(f"{'ID':<4} | {'Nama Usaha':<35} | {'No Telepon':<14} | {'Has Web':<8} | {'Rating':<6} | {'Reviews':<7} | {'Priority':<8}")
    print("-" * 105)

    for b in businesses:
        ls = b.lead_status
        prio = ls.priority.value if ls else "N/A"
        phone_display = b.phone or "-"
        print(f"{b.id:<4} | {b.business_name[:34]:<35} | {phone_display:<14} | {str(b.has_website):<8} | {str(b.rating_avg):<6} | {b.total_review:<7} | {prio:<8}")

    assert crawl_run.status == "success"
    assert len(businesses) > 0
    print("\n [OK] SERPAPI LIVE INTEGRATION TEST PASSED 100%!")


if __name__ == "__main__":
    asyncio.run(test_serpapi_crawl())
