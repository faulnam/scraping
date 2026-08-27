"""
Comprehensive test script for Sprint 2:
- Tests PlacesApiClient (mock mode with fixtures)
- Tests places_api/mapper.py
- Tests leads/scoring.py
- Tests ingest/pipeline.py (pandas data cleaning, MySQL storage, 30-day cache dedup, and LeadStatus sync)
"""
import asyncio
import sys
from datetime import datetime
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models import CrawlRun, Business, LeadStatus, LeadPriority, ContactStatus
from app.places_api.client import PlacesApiClient
from app.places_api.mapper import map_place_to_business_dict, normalize_phone_number, normalize_phone_to_whatsapp
from app.leads.scoring import calculate_lead_priority
from app.ingest.pipeline import run_ingest_pipeline, clean_businesses_dataframe


def test_mapper_and_scoring():
    print("\n=======================================================")
    print(" 1. UNIT TEST: MAPPER, PHONE NORMALIZATION & SCORING")
    print("=======================================================")

    # Test phone normalization
    phone1 = normalize_phone_number("+62 812-2334-4556")
    assert phone1 == "081223344556", f"Expected 081223344556, got {phone1}"
    wa1 = normalize_phone_to_whatsapp("+62 812-2334-4556")
    assert wa1 == "https://wa.me/6281223344556", f"Expected wa.me/6281223344556, got {wa1}"

    landline = normalize_phone_number("(022) 2012345")
    assert landline == "0222012345", f"Expected 0222012345, got {landline}"
    wa_landline = normalize_phone_to_whatsapp("(022) 2012345")
    assert wa_landline is None, "Landline should not produce a mobile WhatsApp link"
    print(" [OK] Phone normalization & WhatsApp link generation verified.")

    # Test Scoring rules
    p_high = calculate_lead_priority(has_website=False, rating_avg=4.8, total_review=10)
    assert p_high == LeadPriority.HIGH, f"Expected HIGH, got {p_high}"

    p_high2 = calculate_lead_priority(has_website=False, rating_avg=3.5, total_review=25)
    assert p_high2 == LeadPriority.HIGH, f"Expected HIGH, got {p_high2}"

    p_med = calculate_lead_priority(has_website=False, rating_avg=3.8, total_review=5)
    assert p_med == LeadPriority.MEDIUM, f"Expected MEDIUM, got {p_med}"

    p_low = calculate_lead_priority(has_website=True, rating_avg=4.9, total_review=200)
    assert p_low == LeadPriority.LOW, f"Expected LOW, got {p_low}"
    print(" [OK] Lead priority scoring rules verified.")


async def test_places_api_client():
    print("\n=======================================================")
    print(" 2. TEST: PLACES API CLIENT (MOCK FIXTURE MODE)")
    print("=======================================================")
    client = PlacesApiClient(use_mock=True)

    search_resp = await client.search_text(text_query="bengkel motor bandung", page_size=5)
    places = search_resp.get("places", [])
    print(f" [OK] Search returned {len(places)} places from fixture.")
    assert len(places) > 0, "Should return mock places from fixture"

    first_place_id = places[0]["id"]
    details = await client.get_place_details(first_place_id)
    assert details is not None, "Place details should be found in fixture"
    print(f" [OK] Detail returned for '{details.get('displayName', {}).get('text')}': Rating={details.get('rating')}, Phone={details.get('nationalPhoneNumber')}")


async def test_ingest_pipeline_mysql():
    print("\n=======================================================")
    print(" 3. TEST: INGESTION PIPELINE (END-TO-END WITH MYSQL)")
    print("=======================================================")
    init_db()
    db: Session = SessionLocal()

    category = "Bengkel Motor & Usaha Lokal"
    location = "Kota Bandung"
    province = "Jawa Barat"
    city = "Kota Bandung"

    print(f"\n>> Step 3A: Executing First Crawl Run for '{category}' in '{location}'...")
    crawl1 = await run_ingest_pipeline(
        category_query=category,
        location_query=location,
        province=province,
        city=city,
        db=db,
        client=PlacesApiClient(use_mock=True)
    )

    print(f" [Run 1 Finished] ID={crawl1.id}, Status={crawl1.status}, Total={crawl1.total_businesses}, API Requests Used={crawl1.api_requests_used}")
    assert crawl1.status == "success"
    assert crawl1.total_businesses > 0
    assert crawl1.api_requests_used >= 1  # 1 search (+ N details if fresh)

    # Query businesses from database
    businesses = db.query(Business).filter(Business.crawl_run_id == crawl1.id).all()
    print(f"\n>> Retrieved {len(businesses)} businesses from MySQL 'businesses' table:")
    print(f"{'ID':<4} | {'Business Name':<35} | {'Phone':<14} | {'Has Web':<8} | {'Rating':<6} | {'Reviews':<7} | {'Priority':<8} | {'Status':<15}")
    print("-" * 115)

    for b in businesses:
        ls = b.lead_status
        prio = ls.priority.value if ls else "N/A"
        status = ls.contact_status.value if ls else "N/A"
        phone_display = b.phone or "-"
        print(f"{b.id:<4} | {b.business_name[:34]:<35} | {phone_display:<14} | {str(b.has_website):<8} | {str(b.rating_avg):<6} | {b.total_review:<7} | {prio:<8} | {status:<15}")

    # Check 1-to-1 lead_status relation
    lead_statuses = db.query(LeadStatus).all()
    print(f"\n [OK] Total records in 'lead_status' table: {len(lead_statuses)}")
    assert len(lead_statuses) >= len(businesses), "Every business must have a corresponding lead_status"

    print(f"\n>> Step 3B: Testing 30-Day Cache Dedup (Second Crawl Run with same query)...")
    crawl2 = await run_ingest_pipeline(
        category_query=category,
        location_query=location,
        province=province,
        city=city,
        db=db,
        client=PlacesApiClient(use_mock=True)
    )

    print(f" [Run 2 Finished] ID={crawl2.id}, Status={crawl2.status}, Total={crawl2.total_businesses}, API Requests Used={crawl2.api_requests_used}")
    print(" Notice: API Requests Used in Run 2 = 1 (Only search_text was called, all place details were cached!)")
    assert crawl2.api_requests_used == 1, f"Expected 1 API request (search only) due to 30-day cache dedup, got {crawl2.api_requests_used}"

    db.close()
    print("\n=======================================================")
    print(" ALL TESTS PASSED SUCCESSFULLY! SPRINT 2 DELIVERABLES VERIFIED.")
    print("=======================================================\n")


async def main():
    test_mapper_and_scoring()
    await test_places_api_client()
    await test_ingest_pipeline_mysql()


if __name__ == "__main__":
    asyncio.run(main())
